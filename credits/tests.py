"""Tests for the credit ledger and the reward challenges.

The interesting cases are the unhappy ones: a charge that cannot be paid, a
generation that fails, two requests racing for the same balance, and a reward
that must not be granted for a click.
"""

import json
import threading

from django.contrib.auth import get_user_model
from django.db import OperationalError, connection
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from credits.challenges import (
    ChallengeError,
    challenge_state,
    complete_challenge,
    on_first_generation,
    ChallengeType,
)
from credits.models import Challenge, ChallengeCompletion, CreditTransaction, TransactionKind, ChallengeType as ChallengeTypeModel
from credits.services import (
    SIGNUP_CREDITS,
    InsufficientCredits,
    adjust,
    charge,
    get_balance,
    history,
    refund,
)
from imagegen.models import AIConfig, GeneratedImage

User = get_user_model()


def _user(username, is_verified=True):
    user = User.objects.create_user(
        username=username, email=f"{username}@example.com", password="test-password"
    )
    user.is_verified = is_verified
    user.save(update_fields=["is_verified"])
    return user


class SignupBonusTests(TestCase):
    def test_a_new_account_starts_with_two_hundred_credits(self):
        user = _user("newcomer")
        self.assertEqual(get_balance(user), SIGNUP_CREDITS)

        bonus = CreditTransaction.objects.get(user=user)
        self.assertEqual(bonus.kind, TransactionKind.REWARD)
        self.assertEqual(bonus.amount, SIGNUP_CREDITS)
        self.assertEqual(bonus.balance_after, SIGNUP_CREDITS)

    def test_a_prefunded_account_keeps_its_balance(self):
        user = User.objects.create_user(
            username="fixture",
            email="fixture@example.com",
            password="test-password",
            credit_balance=1234,
        )
        self.assertEqual(get_balance(user), 1234)
        self.assertFalse(CreditTransaction.objects.filter(user=user).exists())


class LedgerTests(TestCase):
    def setUp(self):
        self.user = _user("spender")

    def test_a_charge_debits_the_wallet_and_writes_a_line(self):
        row = charge(self.user, 80, note="AI generation")
        self.assertEqual(row.amount, -80)
        self.assertEqual(row.balance_after, SIGNUP_CREDITS - 80)
        self.assertEqual(get_balance(self.user), SIGNUP_CREDITS - 80)

    def test_a_charge_beyond_the_balance_is_refused_and_writes_nothing(self):
        with self.assertRaises(InsufficientCredits) as caught:
            charge(self.user, SIGNUP_CREDITS + 1)

        self.assertEqual(caught.exception.shortfall, 1)
        self.assertEqual(get_balance(self.user), SIGNUP_CREDITS)
        self.assertFalse(
            CreditTransaction.objects.filter(kind=TransactionKind.GENERATION).exists()
        )

    def test_the_balance_can_reach_exactly_zero(self):
        charge(self.user, SIGNUP_CREDITS)
        self.assertEqual(get_balance(self.user), 0)

        with self.assertRaises(InsufficientCredits):
            charge(self.user, 1)

    def test_a_refund_restores_the_charge(self):
        charge(self.user, 80)
        refund(self.user, 80, note="failed generation")
        self.assertEqual(get_balance(self.user), SIGNUP_CREDITS)

        kinds = list(
            CreditTransaction.objects.filter(user=self.user).values_list("kind", flat=True)
        )
        self.assertEqual(
            kinds,
            [TransactionKind.REFUND, TransactionKind.GENERATION, TransactionKind.REWARD],
        )

    def test_an_admin_adjustment_can_grant_and_claw_back(self):
        adjust(self.user, 500, note="goodwill")
        self.assertEqual(get_balance(self.user), SIGNUP_CREDITS + 500)

        adjust(self.user, -10_000, note="clawback")
        self.assertEqual(get_balance(self.user), 0)

    def test_history_is_newest_first(self):
        charge(self.user, 80)
        rows = history(self.user)
        self.assertEqual(rows[0].kind, TransactionKind.GENERATION)
        self.assertEqual(rows[-1].kind, TransactionKind.REWARD)


class ConcurrentChargeTests(TransactionTestCase):
    """The wallet cannot be overdrawn by requests racing each other."""

    reset_sequences = True

    def test_six_simultaneous_charges_only_pay_for_two(self):
        user = _user("racer")
        User.objects.filter(pk=user.pk).update(credit_balance=200)
        user.refresh_from_db()

        outcomes = []
        lock = threading.Lock()

        def attempt():
            try:
                for _ in range(5):  # a lost write lock is a retry, not a charge
                    try:
                        charge(user, 80)
                    except InsufficientCredits:
                        result = "refused"
                        break
                    except OperationalError:
                        continue
                    else:
                        result = "charged"
                        break
                else:
                    result = "refused"
            finally:
                connection.close()

            with lock:
                outcomes.append(result)

        threads = [threading.Thread(target=attempt) for _ in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        charged = outcomes.count("charged")
        balance = get_balance(user)

        self.assertEqual(charged, 2)  # 200 credits buy exactly two 80s
        self.assertEqual(balance, 200 - charged * 80)
        self.assertGreaterEqual(balance, 0)
        self.assertEqual(
            CreditTransaction.objects.filter(
                user=user, kind=TransactionKind.GENERATION
            ).count(),
            charged,
        )


class InviteChallengeTests(TestCase):
    def setUp(self):
        self.referrer = _user("referrer")
        self.invited = _user("invited", is_verified=True)
        self.invited.referred_by = self.referrer
        self.invited.save(update_fields=["referred_by"])
        AIConfig.objects.create(api_key="sk-test", model="gapgpt/z-image")

    def _ready_generation(self, user):
        """Create a generation with a charge transaction (simulating real generation)."""
        from credits.services import charge
        from imagegen.models import GeneratedImage

        record = GeneratedImage.objects.create(
            user=user, prompt="A mountain", status=GeneratedImage.Status.READY, credit_cost=80
        )
        charge(user, 80, generation=record, note="AI generation")

    def test_a_friend_that_never_generates_earns_the_referrer_nothing(self):
        with self.assertRaises(ChallengeError) as caught:
            complete_challenge(self.referrer, "invite_friend", evidence=str(self.invited.pk))
        self.assertEqual(caught.exception.code, "not_verified")
        self.assertEqual(get_balance(self.referrer), SIGNUP_CREDITS)

    def test_the_reward_lands_after_the_friends_first_generation(self):
        self._ready_generation(self.invited)

        completion, transaction_row = complete_challenge(
            self.referrer, "invite_friend", evidence=str(self.invited.pk)
        )

        self.assertEqual(completion.status, ChallengeCompletion.Status.VERIFIED)
        self.assertEqual(transaction_row.amount, 100)
        self.assertEqual(get_balance(self.referrer), SIGNUP_CREDITS + 100)

    def test_the_same_proof_is_only_paid_once(self):
        self._ready_generation(self.invited)
        complete_challenge(self.referrer, "invite_friend", evidence=str(self.invited.pk))

        with self.assertRaises(ChallengeError) as caught:
            complete_challenge(
                self.referrer, "invite_friend", evidence=str(self.invited.pk)
            )
        self.assertEqual(caught.exception.code, "duplicate")
        self.assertEqual(get_balance(self.referrer), SIGNUP_CREDITS + 100)

    def test_a_stranger_cannot_claim_someone_elses_invite(self):
        self._ready_generation(self.invited)
        other = _user("other")
        with self.assertRaises(ChallengeError):
            complete_challenge(other, "invite_friend", evidence=str(self.invited.pk))

    def test_the_first_generation_hook_rewards_the_referrer(self):
        self._ready_generation(self.invited)
        on_first_generation(self.invited)

        self.assertEqual(get_balance(self.referrer), SIGNUP_CREDITS + 100)

        # A second image must not pay again.
        self._ready_generation(self.invited)
        on_first_generation(self.invited)
        self.assertEqual(get_balance(self.referrer), SIGNUP_CREDITS + 100)

    def test_the_hook_ignores_accounts_without_an_inviter(self):
        stranger = _user("stranger")
        self._ready_generation(stranger)
        self.assertIsNone(on_first_generation(stranger))

    def test_unverified_friend_does_not_earn_referrer_reward(self):
        """Referrer should not be rewarded if invited user hasn't verified email."""
        unverified_invited = _user("unverified", is_verified=False)
        unverified_invited.referred_by = self.referrer
        unverified_invited.save(update_fields=["referred_by"])
        self._ready_generation(unverified_invited)

        with self.assertRaises(ChallengeError) as caught:
            complete_challenge(self.referrer, "invite_friend", evidence=str(unverified_invited.pk))
        self.assertEqual(caught.exception.code, "not_verified")
        self.assertEqual(get_balance(self.referrer), SIGNUP_CREDITS)

    def test_hook_ignores_unverified_friend(self):
        """on_first_generation should not reward referrer if invited user is unverified."""
        unverified_invited = _user("unverified2", is_verified=False)
        unverified_invited.referred_by = self.referrer
        unverified_invited.save(update_fields=["referred_by"])
        self._ready_generation(unverified_invited)

        result = on_first_generation(unverified_invited)
        self.assertIsNone(result)
        self.assertEqual(get_balance(self.referrer), SIGNUP_CREDITS)


class InstagramChallengeTests(TestCase):
    def setUp(self):
        self.user = _user("sharer")
        AIConfig.objects.create(api_key="sk-test", model="gapgpt/z-image")
        GeneratedImage.objects.create(
            user=self.user, prompt="A mountain", status=GeneratedImage.Status.READY
        )

    def test_a_real_post_link_is_rewarded(self):
        completion, row = complete_challenge(
            self.user, "instagram_share", evidence="https://instagram.com/p/Cab12dEfGh/"
        )
        self.assertEqual(row.amount, 40)
        self.assertEqual(completion.status, ChallengeCompletion.Status.VERIFIED)

    def test_a_random_link_is_rejected(self):
        with self.assertRaises(ChallengeError) as caught:
            complete_challenge(self.user, "instagram_share", evidence="https://example.com/p/x")
        self.assertEqual(caught.exception.code, "not_verified")
        self.assertEqual(get_balance(self.user), SIGNUP_CREDITS)

    def test_the_challenge_is_awarded_once_per_user(self):
        complete_challenge(
            self.user, "instagram_share", evidence="https://instagram.com/p/Cab12dEfGh/"
        )
        with self.assertRaises(ChallengeError) as caught:
            complete_challenge(
                self.user, "instagram_share", evidence="https://instagram.com/p/Zyx98wVuTs/"
            )
        self.assertEqual(caught.exception.code, "already_earned")

    def test_sharing_without_a_generation_is_refused(self):
        GeneratedImage.objects.all().delete()
        with self.assertRaises(ChallengeError):
            complete_challenge(
                self.user, "instagram_share", evidence="https://instagram.com/p/Xyz12AbCd3/"
            )

    def test_state_marks_a_finished_challenge(self):
        complete_challenge(
            self.user, "instagram_share", evidence="https://instagram.com/p/Cab12dEfGh/"
        )
        by_slug = {row["slug"]: row for row in challenge_state(self.user)}
        self.assertTrue(by_slug["instagram_share"]["complete"])
        self.assertTrue(by_slug["instagram_share"]["needs_evidence"])
        self.assertFalse(by_slug["invite_friend"]["needs_evidence"])


class ClaimEndpointTests(TestCase):
    def setUp(self):
        self.user = _user("claimer")
        AIConfig.objects.create(api_key="sk-test", model="gapgpt/z-image")
        GeneratedImage.objects.create(
            user=self.user, prompt="A mountain", status=GeneratedImage.Status.READY
        )
        self.url = reverse("credits:claim-challenge", args=["instagram_share"])

    def test_anonymous_visitors_get_a_401_json_response(self):
        # /api/ routes answer unauthenticated calls with 401, not a redirect.
        response = self.client.post(
            self.url,
            data=json.dumps({"evidence": "https://instagram.com/p/Xyz12AbCd3/"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)

    def test_a_valid_claim_returns_the_new_balance(self):
        self.client.force_login(self.user)
        response = self.client.post(
            self.url,
            data=json.dumps({"evidence": "https://instagram.com/p/Xyz12AbCd3/"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["reward"], 40)
        self.assertEqual(body["credits"]["balance"], SIGNUP_CREDITS + 40)
        by_slug = {row["slug"]: row for row in body["challenges"]}
        self.assertTrue(by_slug["instagram_share"]["complete"])

    def test_a_rejected_claim_explains_itself(self):
        self.client.force_login(self.user)
        response = self.client.post(
            self.url,
            data=json.dumps({"evidence": "nonsense"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error_code"], "not_verified")
        self.assertTrue(response.json()["error"])

    def test_an_unknown_challenge_is_a_400(self):
        self.client.force_login(self.user)
        url = reverse("credits:claim-challenge", args=["does_not_exist"])
        response = self.client.post(url, data="{}", content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error_code"], "unknown_challenge")


class ChallengeAdminTests(TestCase):
    def test_a_challenge_can_be_disabled(self):
        Challenge.objects.filter(slug="instagram_share").update(is_active=False)
        user = _user("paused")
        with self.assertRaises(ChallengeError) as caught:
            complete_challenge(
                user, "instagram_share", evidence="https://instagram.com/p/Cab12dEfGh/"
            )
        self.assertEqual(caught.exception.code, "unknown_challenge")


class TimeWindowTests(TestCase):
    """Tests for challenge time window enforcement."""

    def setUp(self):
        self.user = _user("timer")
        AIConfig.objects.create(api_key="sk-test", model="gapgpt/z-image")
        GeneratedImage.objects.create(
            user=self.user, prompt="A mountain", status=GeneratedImage.Status.READY
        )
        self.challenge = Challenge.objects.get(slug="instagram_share")

    def test_challenge_not_started_rejects_claim(self):
        """A challenge with future starts_at should reject claims."""
        from django.utils import timezone
        from datetime import timedelta

        self.challenge.starts_at = timezone.now() + timedelta(hours=1)
        self.challenge.save()

        with self.assertRaises(ChallengeError) as caught:
            complete_challenge(
                self.user, "instagram_share", evidence="https://instagram.com/p/Cab12dEfGh/"
            )
        self.assertEqual(caught.exception.code, "not_started")

    def test_challenge_ended_rejects_claim(self):
        """A challenge with past ends_at should reject claims."""
        from django.utils import timezone
        from datetime import timedelta

        self.challenge.ends_at = timezone.now() - timedelta(hours=1)
        self.challenge.save()

        with self.assertRaises(ChallengeError) as caught:
            complete_challenge(
                self.user, "instagram_share", evidence="https://instagram.com/p/Cab12dEfGh/"
            )
        self.assertEqual(caught.exception.code, "ended")

    def test_challenge_within_window_allows_claim(self):
        """A challenge within its time window should allow claims."""
        from django.utils import timezone
        from datetime import timedelta

        self.challenge.starts_at = timezone.now() - timedelta(hours=1)
        self.challenge.ends_at = timezone.now() + timedelta(hours=1)
        self.challenge.save()

        completion, row = complete_challenge(
            self.user, "instagram_share", evidence="https://instagram.com/p/Cab12dEfGh/"
        )
        self.assertEqual(completion.status, ChallengeCompletion.Status.VERIFIED)

    def test_mission_ignores_time_window(self):
        """Missions should ignore starts_at/ends_at and always be available if active."""
        from django.utils import timezone
        from datetime import timedelta

        self.challenge.type = ChallengeType.MISSION
        self.challenge.starts_at = timezone.now() + timedelta(days=365)  # Far future
        self.challenge.ends_at = timezone.now() - timedelta(days=365)    # Far past
        self.challenge.save()

        completion, row = complete_challenge(
            self.user, "instagram_share", evidence="https://instagram.com/p/Cab12dEfGh/"
        )
        self.assertEqual(completion.status, ChallengeCompletion.Status.VERIFIED)


class GlobalCapTests(TestCase):
    """Tests for global reward cap enforcement."""

    def setUp(self):
        AIConfig.objects.create(api_key="sk-test", model="gapgpt/z-image")

    def test_global_cap_blocks_additional_claims(self):
        """Once max_total_rewards is reached, no more rewards should be granted."""
        challenge = Challenge.objects.get(slug="instagram_share")
        challenge.max_total_rewards = 2
        challenge.save()

        user1 = _user("capuser1")
        GeneratedImage.objects.create(user=user1, prompt="A", status=GeneratedImage.Status.READY)
        user2 = _user("capuser2")
        GeneratedImage.objects.create(user=user2, prompt="B", status=GeneratedImage.Status.READY)
        user3 = _user("capuser3")
        GeneratedImage.objects.create(user=user3, prompt="C", status=GeneratedImage.Status.READY)

        # First two should succeed
        complete_challenge(user1, "instagram_share", evidence="https://instagram.com/p/OneLong/")
        complete_challenge(user2, "instagram_share", evidence="https://instagram.com/p/TwoLong/")

        # Third should fail
        with self.assertRaises(ChallengeError) as caught:
            complete_challenge(user3, "instagram_share", evidence="https://instagram.com/p/ThreeL/")
        self.assertEqual(caught.exception.code, "global_cap_reached")


class MissionVerifierTests(TestCase):
    """Tests for mission verifiers (complete_profile, first_generation, first_post)."""

    def test_complete_profile_rewards_when_done(self):
        """User with complete profile should earn the reward."""
        user = _user("profiler")
        user.display_name = "Real Name"
        user.biography = "I like prompts"
        user.profile_picture = "profile_pictures/test.jpg"  # Just a string for test
        user.save()

        Challenge.objects.create(
            slug="complete_profile",
            title="Complete Profile",
            verifier="complete_profile",
            reward_credits=50,
            type=ChallengeType.MISSION,
        )

        completion, row = complete_challenge(user, "complete_profile")
        self.assertEqual(completion.status, ChallengeCompletion.Status.VERIFIED)
        self.assertEqual(row.amount, 50)

    def test_complete_profile_rejects_incomplete(self):
        """User with incomplete profile should be rejected."""
        user = _user("incomplete")

        Challenge.objects.create(
            slug="complete_profile",
            title="Complete Profile",
            verifier="complete_profile",
            reward_credits=50,
            type=ChallengeType.MISSION,
        )

        with self.assertRaises(ChallengeError) as caught:
            complete_challenge(user, "complete_profile")
        self.assertEqual(caught.exception.code, "not_verified")
        self.assertIn("display name", str(caught.exception).lower())

    def test_first_generation_rewards_on_first_ready(self):
        """User should earn reward on first successful generation."""
        user = _user("genuser")
        AIConfig.objects.create(api_key="sk-test", model="gapgpt/z-image")

        Challenge.objects.create(
            slug="first_generation",
            title="First Generation",
            verifier="first_generation",
            reward_credits=30,
            type=ChallengeType.MISSION,
        )

        # Before generation - should fail
        with self.assertRaises(ChallengeError) as caught:
            complete_challenge(user, "first_generation")
        self.assertEqual(caught.exception.code, "not_verified")

        # After first generation - should succeed
        GeneratedImage.objects.create(
            user=user, prompt="A mountain", status=GeneratedImage.Status.READY
        )
        completion, row = complete_challenge(user, "first_generation")
        self.assertEqual(completion.status, ChallengeCompletion.Status.VERIFIED)
        self.assertEqual(row.amount, 30)

        # Second generation - should fail (already earned)
        GeneratedImage.objects.create(
            user=user, prompt="Another", status=GeneratedImage.Status.READY
        )
        with self.assertRaises(ChallengeError) as caught:
            complete_challenge(user, "first_generation")
        self.assertEqual(caught.exception.code, "already_earned")

    def test_first_post_rewards_on_first_post(self):
        """User should earn reward on first published post."""
        from posts.models import Category, Post

        user = _user("poster")
        category = Category.objects.create(name="Test", slug="test")

        Challenge.objects.create(
            slug="first_post",
            title="First Post",
            verifier="first_post",
            reward_credits=25,
            type=ChallengeType.MISSION,
        )

        # Before post - should fail
        with self.assertRaises(ChallengeError) as caught:
            complete_challenge(user, "first_post")
        self.assertEqual(caught.exception.code, "not_verified")

        # After first post - should succeed
        Post.objects.create(
            author=user, category=category, post_type=Post.PostType.PROMPT, title="My Prompt"
        )
        completion, row = complete_challenge(user, "first_post")
        self.assertEqual(completion.status, ChallengeCompletion.Status.VERIFIED)
        self.assertEqual(row.amount, 25)

        # Second post - should fail (already earned)
        Post.objects.create(
            author=user, category=category, post_type=Post.PostType.PROMPT, title="Another"
        )
        with self.assertRaises(ChallengeError) as caught:
            complete_challenge(user, "first_post")
        self.assertEqual(caught.exception.code, "already_earned")


class IdempotencyKeyTests(TestCase):
    """Tests for idempotency key duplicate protection."""

    def setUp(self):
        self.user = _user("idempotent")
        AIConfig.objects.create(api_key="sk-test", model="gapgpt/z-image")
        # Create a friend who generated an image for invite_friend challenge
        self.friend = _user("friendgen", is_verified=True)
        self.friend.referred_by = self.user
        self.friend.save(update_fields=["referred_by"])
        GeneratedImage.objects.create(
            user=self.friend, prompt="A mountain", status=GeneratedImage.Status.READY
        )
        from credits.services import charge
        charge(self.friend, 80, note="AI generation")

    def test_idempotency_key_prevents_duplicate_submission(self):
        """Same idempotency key should return existing completion."""
        key = "idem-key-12345"

        # First submission
        completion1, row1 = complete_challenge(
            self.user, "invite_friend",
            evidence=str(self.friend.pk),
            idempotency_key=key
        )
        self.assertEqual(completion1.status, ChallengeCompletion.Status.VERIFIED)

        # Second submission with same key - should return existing
        completion2, row2 = complete_challenge(
            self.user, "invite_friend",
            evidence=str(self.friend.pk),
            idempotency_key=key
        )
        self.assertEqual(completion1.id, completion2.id)
        self.assertEqual(row1.id, row2.id)

    def test_different_idempotency_key_allows_new_submission(self):
        """Different idempotency key should create new completion (but fail due to already_earned for invite_friend)."""
        # First submission
        complete_challenge(
            self.user, "invite_friend",
            evidence=str(self.friend.pk),
            idempotency_key="key-1"
        )

        # Second submission with different key - should fail due to duplicate evidence
        with self.assertRaises(ChallengeError) as caught:
            complete_challenge(
                self.user, "invite_friend",
                evidence=str(self.friend.pk),
                idempotency_key="key-2"
            )
        self.assertEqual(caught.exception.code, "duplicate")

    def test_empty_idempotency_key_uses_evidence_uniqueness(self):
        """Empty idempotency key should fall back to evidence-based uniqueness."""
        # First submission
        complete_challenge(
            self.user, "invite_friend",
            evidence=str(self.friend.pk),
            idempotency_key=""
        )

        # Second submission with same evidence, empty key - should fail
        with self.assertRaises(ChallengeError) as caught:
            complete_challenge(
                self.user, "invite_friend",
                evidence=str(self.friend.pk),
                idempotency_key=""
            )
        self.assertEqual(caught.exception.code, "duplicate")


class ConcurrentChallengeTests(TransactionTestCase):
    """Tests for race conditions in challenge completion."""

    reset_sequences = True

    def test_concurrent_claims_only_reward_once(self):
        """Concurrent claims for same challenge should only reward once per user."""
        import threading

        AIConfig.objects.create(api_key="sk-test", model="gapgpt/z-image")

        challenge = Challenge.objects.get(slug="instagram_share")
        challenge.max_rewards_per_user = 1
        challenge.save()

        user = _user("racer2")
        GeneratedImage.objects.create(
            user=user, prompt="A mountain", status=GeneratedImage.Status.READY
        )

        outcomes = []
        lock = threading.Lock()

        def attempt():
            try:
                complete_challenge(user, "instagram_share", evidence="https://instagram.com/p/Cab12dEfGh/")
                result = "success"
            except ChallengeError as e:
                result = e.code
            except Exception:
                result = "error"
            finally:
                connection.close()

            with lock:
                outcomes.append(result)

        # Fire 5 concurrent attempts
        threads = [threading.Thread(target=attempt) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # Exactly one should succeed, rest should be "already_earned" or "duplicate"
        success_count = outcomes.count("success")
        self.assertEqual(success_count, 1)

        # Balance should only increase by one reward
        self.assertEqual(get_balance(user), SIGNUP_CREDITS + 40)


class ChallengeStateTests(TestCase):
    """Tests for challenge_state output with new fields."""

    def setUp(self):
        self.user = _user("stateuser")
        AIConfig.objects.create(api_key="sk-test", model="gapgpt/z-image")
        GeneratedImage.objects.create(
            user=self.user, prompt="A mountain", status=GeneratedImage.Status.READY
        )

    def test_challenge_state_includes_new_fields(self):
        """challenge_state should include type, starts_at, ends_at, is_open, global_capped."""
        state = challenge_state(self.user)
        by_slug = {row["slug"]: row for row in state}

        # Check instagram_share (challenge type)
        ig = by_slug["instagram_share"]
        self.assertEqual(ig["type"], "challenge")
        self.assertIn("starts_at", ig)
        self.assertIn("ends_at", ig)
        self.assertIn("is_open", ig)
        self.assertIn("global_capped", ig)

        # Check invite_friend (also challenge type by default)
        inv = by_slug["invite_friend"]
        self.assertEqual(inv["type"], "challenge")
        self.assertFalse(inv["needs_evidence"])  # invite_friend is not in EVIDENCE_VERIFIERS
