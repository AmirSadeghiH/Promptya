"""Reward challenges: the modular half of the credits system.

A challenge is just a row plus a *verifier* — a small function that inspects
evidence and decides yes or no.  Nothing else in the codebase knows how a
challenge is proven, so a new reward (a review, a tutorial, a weekly streak)
is a new function in ``VERIFIERS`` and a new row, with no change to the credit
path at all.
"""

from __future__ import annotations

import re
from datetime import timedelta

from django.db import IntegrityError, models, transaction
from django.db.models import Count
from django.utils import timezone

from credits.models import Challenge, ChallengeCompletion, ChallengeType
from credits.services import reward

INVITE_FRIEND = "invite_friend"
INSTAGRAM_SHARE = "instagram_share"
COMPLETE_PROFILE = "complete_profile"
FIRST_GENERATION = "first_generation"
FIRST_POST = "first_post"

# Referral protection settings
MAX_REFERRALS_PER_MONTH = 5  # Max referral rewards a user can earn per 30 days

# An Instagram post/reel/tv permalink.  We can only check the shape of the
# link, not that the account is the user's — so sharing also requires a real
# generation, and abuse is reviewable in the admin.
_INSTAGRAM_URL = re.compile(
    r"^https?://(www\.)?instagram\.com/(p|reel|reels|tv)/[A-Za-z0-9_-]{5,}/?$",
    re.IGNORECASE,
)


class ChallengeError(RuntimeError):
    """A challenge could not be completed. ``code`` is machine-readable."""

    def __init__(self, message, code="challenge_error"):
        self.code = code
        super().__init__(message)


def verify_invite_friend(user, challenge, evidence):
    """Reward a referrer once the friend they invited has generated an image.

    ``user`` is the referrer; ``evidence`` is the invited account's id.  The
    invite only pays out after the signup does something real *and spends their
    own credits*, which is what makes this a referral and not a faucet.
    """
    from django.contrib.auth import get_user_model

    from imagegen.models import GeneratedImage

    try:
        invited_id = int(str(evidence).strip())
    except (TypeError, ValueError):
        return False, "We couldn't tell which friend you invited."

    invited = get_user_model().objects.filter(pk=invited_id, referred_by=user).first()
    if invited is None:
        return False, "We couldn't match that invite to your account."

    # Invited user must have verified their email
    if not invited.is_verified:
        return False, "Your friend hasn't verified their email address yet."

    # The invited user must have a READY generation. A GENERATION charge row
    # alone is not proof: the charge is written before the provider runs and is
    # refunded when the attempt fails, so a failed attempt would otherwise count.
    has_real_generation = GeneratedImage.objects.filter(
        user=invited,
        status=GeneratedImage.Status.READY,
        credit_cost__gt=0,
    ).exists()

    if not has_real_generation:
        return False, "Your friend hasn't generated an image using their own credits yet."

    # Check monthly referral cap for the referrer
    month_ago = timezone.now() - timedelta(days=30)
    recent_referrals = ChallengeCompletion.objects.filter(
        user=user,
        challenge__slug=INVITE_FRIEND,
        status=ChallengeCompletion.Status.VERIFIED,
        verified_at__gte=month_ago,
    ).count()

    if recent_referrals >= MAX_REFERRALS_PER_MONTH:
        return False, f"Monthly referral limit reached ({MAX_REFERRALS_PER_MONTH}/month)."

    return True, ""


def verify_instagram_share(user, challenge, evidence):
    """Reward a share once the user links the Instagram post they published."""
    from imagegen.models import GeneratedImage

    url = str(evidence or "").strip()
    if not _INSTAGRAM_URL.match(url):
        return False, "Paste the Instagram post link (instagram.com/p/…)."
    if not GeneratedImage.objects.filter(
        user=user, status=GeneratedImage.Status.READY
    ).exists():
        return False, "Generate an image first, then share it."
    return True, ""


def verify_complete_profile(user, challenge, evidence):
    """Reward for completing profile (display_name, biography, profile_picture)."""
    if not user.display_name or user.display_name.strip() == user.username:
        return False, "Set a display name different from your username."
    if not user.biography or not user.biography.strip():
        return False, "Add a biography to your profile."
    if not user.profile_picture:
        return False, "Upload a profile picture."
    return True, ""


def verify_first_generation(user, challenge, evidence):
    """Reward for first successful AI generation."""
    from imagegen.models import GeneratedImage
    if not GeneratedImage.objects.filter(
        user=user, status=GeneratedImage.Status.READY
    ).exists():
        return False, "Generate your first image to earn this reward."
    return True, ""


def verify_first_post(user, challenge, evidence):
    """Reward for first published post."""
    if not user.posts.exists():
        return False, "Publish your first prompt to earn this reward."
    return True, ""


# The whole extension point of the reward system.
VERIFIERS = {
    INVITE_FRIEND: verify_invite_friend,
    INSTAGRAM_SHARE: verify_instagram_share,
    COMPLETE_PROFILE: verify_complete_profile,
    FIRST_GENERATION: verify_first_generation,
    FIRST_POST: verify_first_post,
}

# Verifiers that need the user to hand in something (a link) before they can
# run.  Everything else is granted by the system when the event happens.
EVIDENCE_VERIFIERS = {INSTAGRAM_SHARE}

# Verifiers that require evidence but are not in EVIDENCE_VERIFIERS (e.g., invite_friend)
EVIDENCE_REQUIRED_VERIFIERS = {INVITE_FRIEND}


def earned_count(user, challenge) -> int:
    return ChallengeCompletion.objects.filter(
        user=user, challenge=challenge, status=ChallengeCompletion.Status.VERIFIED
    ).count()


def active_challenges():
    """Return challenges that are currently active and within their time window."""
    now = timezone.now()
    return list(
        Challenge.objects.filter(
            is_active=True
        ).filter(
            models.Q(type=ChallengeType.MISSION) |
            models.Q(starts_at__isnull=True, ends_at__isnull=True) |
            models.Q(starts_at__lte=now, ends_at__isnull=True) |
            models.Q(starts_at__isnull=True, ends_at__gte=now) |
            models.Q(starts_at__lte=now, ends_at__gte=now)
        )
    )


def challenge_state(user) -> list[dict]:
    """Challenges with this user's progress, ready for the studio panel."""
    if user is None or not getattr(user, "is_authenticated", False):
        return []

    now = timezone.now()
    challenges = active_challenges()
    if not challenges:
        return []

    verified = (
        ChallengeCompletion.objects.filter(
            user=user,
            challenge__in=challenges,
            status=ChallengeCompletion.Status.VERIFIED,
        )
        .values("challenge_id")
        .order_by()
    )
    counts = {}
    for row in verified:
        counts[row["challenge_id"]] = counts.get(row["challenge_id"], 0) + 1

    # One aggregate for every challenge that has a global cap, instead of one
    # COUNT per challenge inside the loop below.
    capped_ids = set()
    if any(challenge.max_total_rewards for challenge in challenges):
        global_rows = (
            ChallengeCompletion.objects.filter(
                challenge__in=challenges,
                status=ChallengeCompletion.Status.VERIFIED,
                challenge__max_total_rewards__gt=0,
            )
            .values("challenge_id")
            .annotate(n=Count("id"))
        )
        cap_by_id = {ch.id: ch.max_total_rewards for ch in challenges if ch.max_total_rewards}
        for row in global_rows:
            if row["n"] >= cap_by_id[row["challenge_id"]]:
                capped_ids.add(row["challenge_id"])

    state = []
    for challenge in challenges:
        earned = counts.get(challenge.id, 0)
        capped = bool(challenge.max_rewards_per_user) and earned >= challenge.max_rewards_per_user
        
        # Check if challenge is currently open (time window)
        is_open = challenge.is_open(now)
        
        # Check global cap (precomputed above; == not challenge.can_claim_globally())
        global_capped = challenge.id in capped_ids
        
        state.append(
            {
                "slug": challenge.slug,
                "title": challenge.title,
                "description": challenge.description,
                "reward": challenge.reward_credits,
                "earned": earned,
                "complete": capped or global_capped or not is_open,
                "needs_evidence": challenge.verifier in EVIDENCE_VERIFIERS,
                "type": challenge.type,
                "starts_at": challenge.starts_at.isoformat() if challenge.starts_at else None,
                "ends_at": challenge.ends_at.isoformat() if challenge.ends_at else None,
                "is_open": is_open,
                "global_capped": global_capped,
            }
        )
    return state


def complete_challenge(user, slug, evidence="", *, now=None, idempotency_key=""):
    """Verify a proof and pay the reward. Returns ``(completion, transaction)``.

    Raises ``ChallengeError`` when the challenge is unavailable, already paid,
    or the evidence does not check out.  The evidence row is written before
    verification so a bad proof is recorded (and cannot be replayed), and the
    reward itself is only granted once the verifier says yes.
    """
    now = now or timezone.now()

    challenge = Challenge.objects.filter(slug=slug).first()
    if challenge is None or not challenge.is_active:
        raise ChallengeError("That challenge isn't available right now.", "unknown_challenge")

    # Check time window (only for challenges, not missions)
    if challenge.type == ChallengeType.CHALLENGE:
        if challenge.starts_at and now < challenge.starts_at:
            raise ChallengeError("This challenge hasn't started yet.", "not_started")
        if challenge.ends_at and now >= challenge.ends_at:
            raise ChallengeError("This challenge has ended.", "ended")

    # Check global cap
    if not challenge.can_claim_globally():
        raise ChallengeError("This challenge has reached its global reward limit.", "global_cap_reached")

    if (
        challenge.max_rewards_per_user
        and earned_count(user, challenge) >= challenge.max_rewards_per_user
    ):
        raise ChallengeError("You've already earned this reward.", "already_earned")

    verifier = VERIFIERS.get(challenge.verifier)
    if verifier is None:
        raise ChallengeError("This challenge can't be verified yet.", "no_verifier")

    evidence = str(evidence or "").strip()[:500]
    idempotency_key = str(idempotency_key or "").strip()[:64]

    # Handle idempotency key if provided
    if idempotency_key:
        try:
            with transaction.atomic():
                completion = ChallengeCompletion.objects.create(
                    challenge=challenge,
                    user=user,
                    evidence=evidence,
                    idempotency_key=idempotency_key,
                )
        except IntegrityError:
            # Check if existing completion has same key
            existing = ChallengeCompletion.objects.filter(
                idempotency_key=idempotency_key
            ).first()
            if existing:
                if existing.status == ChallengeCompletion.Status.VERIFIED:
                    return existing, existing.reward_transaction
                raise ChallengeError("You've already submitted that proof.", "duplicate") from None
            raise ChallengeError("You've already submitted that proof.", "duplicate") from None
    elif challenge.verifier in EVIDENCE_VERIFIERS | EVIDENCE_REQUIRED_VERIFIERS and evidence:
        # For evidence-based challenges, enforce uniqueness on evidence
        try:
            with transaction.atomic():
                completion = ChallengeCompletion.objects.create(
                    challenge=challenge, user=user, evidence=evidence
                )
        except IntegrityError:
            raise ChallengeError("You've already submitted that proof.", "duplicate") from None
    else:
        # For missions without evidence (or empty evidence), just create or get existing pending/rejected
        completion = ChallengeCompletion.objects.filter(
            challenge=challenge, user=user, evidence=evidence
        ).first()
        if not completion:
            completion = ChallengeCompletion.objects.create(
                challenge=challenge, user=user, evidence=evidence
            )
        elif completion.status == ChallengeCompletion.Status.VERIFIED:
            # Already verified - this is the "already_earned" case but handled earlier
            pass
        elif completion.status == ChallengeCompletion.Status.REJECTED:
            # Allow retry - reset to pending
            completion.status = ChallengeCompletion.Status.PENDING
            completion.detail = ""
            completion.save(update_fields=["status", "detail"])

    try:
        ok, reason = verifier(user, challenge, evidence)
    except Exception:  # a verifier bug must not pay out, or 500
        ok, reason = False, "We couldn't verify that right now."

    if not ok:
        completion.status = ChallengeCompletion.Status.REJECTED
        completion.detail = (reason or "")[:200]
        completion.save(update_fields=["status", "detail"])
        raise ChallengeError(reason or "We couldn't verify that yet.", "not_verified")

    transaction_row = reward(
        user,
        challenge.reward_credits,
        challenge=challenge,
        note=f"Reward: {challenge.title}",
    )
    completion.status = ChallengeCompletion.Status.VERIFIED
    completion.reward_transaction = transaction_row
    completion.verified_at = now
    completion.save(update_fields=["status", "reward_transaction", "verified_at"])
    return completion, transaction_row


def on_first_generation(user):
    """Hook the generation flow calls after a user's first successful image.

    Rewards the referrer, if there is one, provided the new user has spent
    their own credits on a generation AND verified their email.
    Deliberately swallow-all: a broken referral must never fail the generation
    the user actually asked for.
    """
    if user is None or not getattr(user, "referred_by_id", None):
        return None

    # Invited user must have verified their email before referrer gets reward
    if not user.is_verified:
        return None

    from imagegen.models import GeneratedImage

    # Only the first successful image counts.
    if (
        GeneratedImage.objects.filter(
            user=user, status=GeneratedImage.Status.READY
        ).count()
        != 1
    ):
        return None

    referrer = user.referred_by
    if referrer is None or referrer.pk == user.pk:
        return None

    evidence = str(user.pk)
    if ChallengeCompletion.objects.filter(
        challenge__slug=INVITE_FRIEND, user=referrer, evidence=evidence
    ).exists():
        return None

    try:
        completion, _ = complete_challenge(referrer, INVITE_FRIEND, evidence=evidence)
        return completion
    except ChallengeError:
        return None
    except Exception:
        return None
