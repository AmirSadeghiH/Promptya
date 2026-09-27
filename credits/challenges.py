"""Reward challenges: the modular half of the credits system.

A challenge is just a row plus a *verifier* — a small function that inspects
evidence and decides yes or no.  Nothing else in the codebase knows how a
challenge is proven, so a new reward (a review, a tutorial, a weekly streak)
is a new function in ``VERIFIERS`` and a new row, with no change to the credit
path at all.
"""

from __future__ import annotations

import re

from django.db import IntegrityError, transaction
from django.utils import timezone

from credits.models import Challenge, ChallengeCompletion
from credits.services import reward

INVITE_FRIEND = "invite_friend"
INSTAGRAM_SHARE = "instagram_share"

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
    invite only pays out after the signup does something real, which is what
    makes this a referral and not a faucet.
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

    made_something = GeneratedImage.objects.filter(
        user=invited, status=GeneratedImage.Status.READY
    ).exists()
    if not made_something:
        return False, "Your friend hasn't generated an image yet."
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


# The whole extension point of the reward system.
VERIFIERS = {
    INVITE_FRIEND: verify_invite_friend,
    INSTAGRAM_SHARE: verify_instagram_share,
}

# Verifiers that need the user to hand in something (a link) before they can
# run.  Everything else is granted by the system when the event happens.
EVIDENCE_VERIFIERS = {INSTAGRAM_SHARE}


def earned_count(user, challenge) -> int:
    return ChallengeCompletion.objects.filter(
        user=user, challenge=challenge, status=ChallengeCompletion.Status.VERIFIED
    ).count()


def active_challenges():
    return list(Challenge.objects.filter(is_active=True))


def challenge_state(user) -> list[dict]:
    """Challenges with this user's progress, ready for the studio panel."""
    if user is None or not getattr(user, "is_authenticated", False):
        return []

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

    state = []
    for challenge in challenges:
        earned = counts.get(challenge.id, 0)
        capped = bool(challenge.max_rewards_per_user) and earned >= challenge.max_rewards_per_user
        state.append(
            {
                "slug": challenge.slug,
                "title": challenge.title,
                "description": challenge.description,
                "reward": challenge.reward_credits,
                "earned": earned,
                "complete": capped,
                "needs_evidence": challenge.verifier in EVIDENCE_VERIFIERS,
            }
        )
    return state


def complete_challenge(user, slug, evidence="", *, now=None):
    """Verify a proof and pay the reward. Returns ``(completion, transaction)``.

    Raises ``ChallengeError`` when the challenge is unavailable, already paid,
    or the evidence does not check out.  The evidence row is written before
    verification so a bad proof is recorded (and cannot be replayed), and the
    reward itself is only granted once the verifier says yes.
    """
    now = now or timezone.now()

    challenge = Challenge.objects.filter(slug=slug, is_active=True).first()
    if challenge is None:
        raise ChallengeError("That challenge isn't available right now.", "unknown_challenge")

    if (
        challenge.max_rewards_per_user
        and earned_count(user, challenge) >= challenge.max_rewards_per_user
    ):
        raise ChallengeError("You've already earned this reward.", "already_earned")

    verifier = VERIFIERS.get(challenge.verifier)
    if verifier is None:
        raise ChallengeError("This challenge can't be verified yet.", "no_verifier")

    evidence = str(evidence or "").strip()[:500]

    try:
        with transaction.atomic():
            completion = ChallengeCompletion.objects.create(
                challenge=challenge, user=user, evidence=evidence
            )
    except IntegrityError:
        raise ChallengeError("You've already submitted that proof.", "duplicate") from None

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

    Rewards the referrer, if there is one.  Deliberately swallow-all: a broken
    referral must never fail the generation the user actually asked for.
    """
    if user is None or not getattr(user, "referred_by_id", None):
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
