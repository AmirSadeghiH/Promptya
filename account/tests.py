from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse

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


class AuthApiTests(TestCase):
    def test_signup_creates_user_sends_verification_email(self):
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
        self.assertTrue(
            get_user_model().objects.filter(username="newuser").exists()
        )
        user = get_user_model().objects.get(username="newuser")
        self.assertFalse(user.is_verified)
        # User should NOT be logged in
        me = self.client.get(reverse("account:me"))
        self.assertEqual(me.status_code, 401)
        # Verification email should be sent
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Verify your email", mail.outbox[0].subject)

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


class EmailVerificationTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.user = get_user_model().objects.create_user(
            username="verifyuser",
            email="verifyuser@example.com",
            password="test-password",
        )

    def test_verification_success(self):
        from account.models import EmailVerificationToken
        import secrets

        token = secrets.token_urlsafe(32)
        token_obj = EmailVerificationToken.objects.create(user=self.user, token=token)

        response = self.client.get(reverse("account:verify-email", args=[token]))
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_verified)
        token_obj.refresh_from_db()
        self.assertIsNotNone(token_obj.used_at)

    def test_verification_invalid_token(self):
        response = self.client.get(reverse("account:verify-email", args=["invalid-token"]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "invalid")

    def test_verification_expired_token(self):
        from account.models import EmailVerificationToken
        from django.utils import timezone
        from datetime import timedelta
        import secrets

        token = secrets.token_urlsafe(32)
        token_obj = EmailVerificationToken.objects.create(
            user=self.user, token=token, expires_at=timezone.now() - timedelta(hours=1)
        )

        response = self.client.get(reverse("account:verify-email", args=[token]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "expired")

    def test_verification_already_used_token(self):
        from account.models import EmailVerificationToken
        from django.utils import timezone
        import secrets

        token = secrets.token_urlsafe(32)
        token_obj = EmailVerificationToken.objects.create(user=self.user, token=token, used_at=timezone.now())

        response = self.client.get(reverse("account:verify-email", args=[token]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already been used")

    def test_verification_already_verified_user(self):
        from account.models import EmailVerificationToken
        import secrets

        self.user.is_verified = True
        self.user.save()
        token = secrets.token_urlsafe(32)
        token_obj = EmailVerificationToken.objects.create(user=self.user, token=token)

        response = self.client.get(reverse("account:verify-email", args=[token]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already verified")

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
