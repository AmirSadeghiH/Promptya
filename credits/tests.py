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
)
from credits.models import Challenge, ChallengeCompletion, CreditTransaction, TransactionKind
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


def _user(username):
    return User.objects.create_user(
        username=username, email=f"{username}@example.com", password="test-password"
    )


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
        self.invited = _user("invited")
        self.invited.referred_by = self.referrer
        self.invited.save(update_fields=["referred_by"])
        AIConfig.objects.create(api_key="sk-test", model="gapgpt/z-image")

    def _ready_generation(self, user):
        GeneratedImage.objects.create(
            user=user, prompt="A mountain", status=GeneratedImage.Status.READY
        )

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
        GeneratedImage.objects.create(
            user=self.invited, prompt="first", status=GeneratedImage.Status.READY
        )
        on_first_generation(self.invited)

        self.assertEqual(get_balance(self.referrer), SIGNUP_CREDITS + 100)

        # A second image must not pay again.
        GeneratedImage.objects.create(
            user=self.invited, prompt="second", status=GeneratedImage.Status.READY
        )
        on_first_generation(self.invited)
        self.assertEqual(get_balance(self.referrer), SIGNUP_CREDITS + 100)

    def test_the_hook_ignores_accounts_without_an_inviter(self):
        stranger = _user("stranger")
        GeneratedImage.objects.create(
            user=stranger, prompt="solo", status=GeneratedImage.Status.READY
        )
        self.assertIsNone(on_first_generation(stranger))


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
