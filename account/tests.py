import re
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from account.models import EmailVerificationToken
from account.views import issue_verification_code
from interactions.models import Follow, Save
from posts.models import Category, Post


def _make_post(author, title):
    category, _ = Category.objects.get_or_create(name="Writing", slug="writing")
    return Post.objects.create(
        author=author,
        category=category,
        post_type=Post.PostType.PROMPT,
        title=title,
    )


def _code_from_outbox(index=0):
    """The 6-digit code as sent in the plain-text email body."""
    match = re.search(r"\b(\d{6})\b", mail.outbox[index].body)
    assert match, f"no 6-digit code in email {index}: {mail.outbox[index].body!r}"
    return match.group(1)


class AuthApiTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def test_signup_creates_user_sends_code_email(self):
        response = self.client.post(
            reverse("account:signup"),
            {
                "username": "newuser",
                "email": "newuser@example.com",
                "password": "super-secret-123",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        user = get_user_model().objects.get(username="newuser")
        self.assertFalse(user.is_verified)
        # User should NOT be logged in
        me = self.client.get(reverse("account:me"))
        self.assertEqual(me.status_code, 401)
        # A code email (not a link email) should be sent
        self.assertEqual(len(mail.outbox), 1)
        subject = mail.outbox[0].subject
        self.assertEqual(subject, "Your Promptya verification code")
        self.assertNotRegex(subject, r"\d")  # no code digits in the subject
        body = mail.outbox[0].body
        code = _code_from_outbox()
        # The only URL in the email is the bare code-entry page — the code
        # appears in the body, in no URL, and never as a token link.
        for url in re.findall(r"https?://\S+", body):
            self.assertEqual(url, "http://testserver/verify-email/")
            self.assertNotIn(code, url)
        self.assertNotIn("/api/auth/verify-email/", body)
        # Only a salted hash is stored
        token = EmailVerificationToken.objects.get(user=user)
        self.assertTrue(token.code_hash)
        self.assertNotIn(code, token.code_hash)

    def test_signup_rejects_duplicate_username(self):
        get_user_model().objects.create_user(
            username="taken",
            email="taken@example.com",
            password="test-password",
        )

        response = self.client.post(
            reverse("account:signup"),
            {
                "username": "TAKEN",
                "email": "other@example.com",
                "password": "super-secret-123",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("username", response.json()["errors"])

    def test_login_with_username_or_email(self):
        user = get_user_model().objects.create_user(
            username="loginuser",
            email="loginuser@example.com",
            password="super-secret-123",
        )
        user.is_verified = True
        user.save()

        by_username = self.client.post(
            reverse("account:login"),
            {"username": "loginuser", "password": "super-secret-123"},
            content_type="application/json",
        )
        self.assertEqual(by_username.status_code, 200)
        self.assertTrue(by_username.json()["user"]["is_verified"])

        self.client.post(reverse("account:logout"))
        by_email = self.client.post(
            reverse("account:login"),
            {"username": "loginuser@example.com", "password": "super-secret-123"},
            content_type="application/json",
        )
        self.assertEqual(by_email.status_code, 200)

    def test_login_rejects_bad_credentials(self):
        response = self.client.post(
            reverse("account:login"),
            {"username": "ghost", "password": "wrong"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

    def test_me_requires_authentication(self):
        response = self.client.get(reverse("account:me"))

        self.assertEqual(response.status_code, 401)


class EmailVerificationCodeApiTests(TestCase):
    """The JSON code endpoints: /api/auth/verify-email/ and resend."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.user = get_user_model().objects.create_user(
            username="verifyuser",
            email="verifyuser@example.com",
            password="test-password",
        )

    def _issue(self, user=None):
        return issue_verification_code(user or self.user)

    def _wrong_code(self, code):
        return "000000" if code != "000000" else "111111"

    def _backdate_code(self, user=None):
        EmailVerificationToken.objects.filter(user=user or self.user).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )

    def _verify(self, email, code):
        return self.client.post(
            reverse("account:verify-email"),
            {"email": email, "code": code},
            content_type="application/json",
        )

    def test_full_signup_and_verify_flow(self):
        response = self.client.post(
            reverse("account:signup"),
            {
                "username": "mobileuser",
                "email": "mobileuser@example.com",
                "password": "super-secret-123",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        code = _code_from_outbox()

        response = self._verify("mobileuser@example.com", code)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        user = get_user_model().objects.get(email="mobileuser@example.com")
        self.assertTrue(user.is_verified)
        self.assertIsNotNone(
            EmailVerificationToken.objects.get(user=user).used_at
        )

    def test_wrong_code_counts_attempt_and_still_verifiable(self):
        code = self._issue()
        response = self._verify(self.user.email, self._wrong_code(code))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            EmailVerificationToken.objects.get(user=self.user).attempts, 1
        )
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_verified)

        response = self._verify(self.user.email, code)
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_verified)

    def test_five_wrong_codes_kill_the_code(self):
        code = self._issue()
        wrong = self._wrong_code(code)
        for _ in range(5):
            self.assertEqual(self._verify(self.user.email, wrong).status_code, 400)
        self.assertEqual(
            EmailVerificationToken.objects.get(user=self.user).attempts, 5
        )
        # Even the correct code no longer works while the code is locked
        self.assertEqual(self._verify(self.user.email, code).status_code, 400)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_verified)

        # After expiry a resend replaces the dead code with a working one
        self._backdate_code()
        response = self.client.post(
            reverse("account:resend-verification"),
            {"email": self.user.email},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        # The resend reset the attempt counter
        self.assertEqual(
            EmailVerificationToken.objects.get(user=self.user).attempts, 0
        )
        new_code = _code_from_outbox()
        self.assertEqual(self._verify(self.user.email, code).status_code, 400)
        self.assertEqual(self._verify(self.user.email, new_code).status_code, 200)

    def test_expired_code_rejected(self):
        code = self._issue()
        self._backdate_code()
        response = self._verify(self.user.email, code)
        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_verified)

    def test_code_is_one_shot(self):
        code = self._issue()
        self.assertEqual(self._verify(self.user.email, code).status_code, 200)
        # Replaying the same code after use fails
        self.assertEqual(self._verify(self.user.email, code).status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_verified)

    def test_malformed_codes_consume_no_attempt(self):
        self._issue()
        for bad in ("12345", "abcdef", "12a456", ""):
            self.assertEqual(self._verify(self.user.email, bad).status_code, 400)
        self.assertEqual(
            EmailVerificationToken.objects.get(user=self.user).attempts, 0
        )
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_verified)

    def test_all_failure_bodies_are_identical(self):
        code = self._issue()
        wrong = self._wrong_code(code)
        self._backdate_code()
        cases = [
            ("unknown email", self._verify("ghost@example.com", wrong)),
            ("wrong code", self._verify(self.user.email, wrong)),
            ("expired code", self._verify(self.user.email, code)),
            ("malformed", self._verify(self.user.email, "123")),
            ("missing fields", self._verify("", "")),
        ]
        for (label, first), (other_label, other) in zip(cases, cases[1:]):
            with self.subTest(label=label, other=other_label):
                self.assertEqual(other.status_code, 400)
                self.assertEqual(first.content, other.content)

    def test_api_verify_rate_limited_429(self):
        code = self._issue()
        wrong = self._wrong_code(code)
        for _ in range(10):
            self.assertEqual(self._verify(self.user.email, wrong).status_code, 400)
        response = self._verify(self.user.email, code)
        self.assertEqual(response.status_code, 429)
        body = response.json()
        self.assertEqual(body["error_code"], "rate_limited")
        self.assertEqual(body["retry_after"], 300)

    def test_resend_before_expiry_sends_nothing(self):
        code = self._issue()
        response = self.client.post(
            reverse("account:resend-verification"),
            {"email": self.user.email},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)
        # The original code still verifies
        self.assertEqual(self._verify(self.user.email, code).status_code, 200)

    def test_resend_after_expiry_replaces_old_code(self):
        old_code = self._issue()
        self._backdate_code()
        response = self.client.post(
            reverse("account:resend-verification"),
            {"email": self.user.email},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        new_code = _code_from_outbox()
        self.assertEqual(self._verify(self.user.email, old_code).status_code, 400)
        self.assertEqual(self._verify(self.user.email, new_code).status_code, 200)

    def test_resend_unknown_email_sends_nothing(self):
        response = self.client.post(
            reverse("account:resend-verification"),
            {"email": "ghost@example.com"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.assertEqual(len(mail.outbox), 0)

    def test_resend_verified_email_sends_nothing(self):
        self.user.is_verified = True
        self.user.save()
        response = self.client.post(
            reverse("account:resend-verification"),
            {"email": self.user.email},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

    def test_resend_verification_rate_limited(self):
        from account.models import EmailVerificationToken

        # Create user
        self.user = get_user_model().objects.create_user(
            username="resenduser",
            email="resenduser@example.com",
            password="test-password",
        )

        # First resend
        response = self.client.post(
            reverse("account:resend-verification"),
            {"email": "resenduser@example.com"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

        # Second resend (limit is 3/hour)
        response = self.client.post(
            reverse("account:resend-verification"),
            {"email": "resenduser@example.com"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

        # Third resend
        response = self.client.post(
            reverse("account:resend-verification"),
            {"email": "resenduser@example.com"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

        # Fourth resend should be rate limited
        response = self.client.post(
            reverse("account:resend-verification"),
            {"email": "resenduser@example.com"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 429)

    def test_resend_verification_enumeration_resistant(self):
        # Should not reveal if email exists or not
        response = self.client.post(
            reverse("account:resend-verification"),
            {"email": "nonexistent@example.com"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("success", response.json())


class ProfileApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="profileuser",
            email="profileuser@example.com",
            password="test-password",
            display_name="Profile User",
        )
        self.post = _make_post(self.user, "My showcased prompt")

    def test_profile_detail_includes_posts_and_counts(self):
        response = self.client.get(reverse("account:profile-detail", args=["profileuser"]))

        self.assertEqual(response.status_code, 200)
        data = response.json()["user"]
        self.assertEqual(data["username"], "profileuser")
        self.assertEqual(data["post_count"], 1)
        self.assertEqual(data["posts"][0]["title"], "My showcased prompt")

    def test_profile_update_requires_login(self):
        response = self.client.patch(
            reverse("account:profile-update"),
            {"biography": "nope"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)

    def test_owner_can_update_profile(self):
        self.client.force_login(self.user)

        response = self.client.patch(
            reverse("account:profile-update"),
            {"biography": "Prompt collector.", "display_name": "Pro"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.biography, "Prompt collector.")


class SavedPostsApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="saver",
            email="saver@example.com",
            password="test-password",
        )
        self.author = get_user_model().objects.create_user(
            username="saver-author",
            email="saver-author@example.com",
            password="test-password",
        )
        self.post_a = _make_post(self.author, "Saved first")
        self.post_b = _make_post(self.author, "Saved second")

    def test_saved_posts_requires_login(self):
        response = self.client.get(reverse("account:saved-posts"))

        self.assertEqual(response.status_code, 401)

    def test_saved_posts_returns_saved_posts_newest_save_first(self):
        Save.objects.create(user=self.user, post=self.post_a)
        Save.objects.create(user=self.user, post=self.post_b)
        self.client.force_login(self.user)

        response = self.client.get(reverse("account:saved-posts"))

        self.assertEqual(response.status_code, 200)
        titles = [p["title"] for p in response.json()["results"]]
        self.assertEqual(titles, ["Saved second", "Saved first"])


class FollowCountsTests(TestCase):
    def test_profile_shows_follower_and_following_counts(self):
        alice = get_user_model().objects.create_user(
            username="alice", email="alice@example.com", password="test-password",
        )
        bob = get_user_model().objects.create_user(
            username="bob", email="bob@example.com", password="test-password",
        )
        Follow.objects.create(follower=bob, following=alice)

        response = self.client.get(reverse("account:profile-detail", args=["alice"]))
        data = response.json()["user"]

        self.assertEqual(data["follower_count"], 1)
        self.assertEqual(data["following_count"], 0)
