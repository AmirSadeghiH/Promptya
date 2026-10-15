import re

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse

# The address the test client's server uses inside the reset email body.
TESTSERVER = "http://testserver/"


class PasswordResetStandaloneTests(TestCase):
    """Password reset is a focused, chrome-less flow: request, email, set new."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.user = get_user_model().objects.create_user(
            username="reset-user",
            email="reset-user@example.com",
            password="old-password-123",
            is_verified=True,
        )

    def _assert_standalone(self, response, status_code=200):
        self.assertContains(response, 'class="auth-card"', status_code=status_code)
        self.assertNotContains(response, 'class="topbar"', status_code=status_code)
        self.assertNotContains(response, 'class="sidebar"', status_code=status_code)
        self.assertNotContains(response, 'class="bottom-nav"', status_code=status_code)
        self.assertNotContains(response, 'class="site-footer"', status_code=status_code)
        self.assertNotContains(response, 'id="nav-drawer"', status_code=status_code)

    def _request_reset_link(self):
        """Submit the form and return the link from the reset email."""
        response = self.client.post(
            reverse("account:password_reset"), {"email": self.user.email}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("account:password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        match = re.search(re.escape(TESTSERVER) + r"[^\s\r\n]+", mail.outbox[0].body)
        self.assertIsNotNone(match, f"No reset link in email body: {mail.outbox[0].body!r}")
        return match.group(0)

    def _open_reset_link(self, token_url):
        """Follow the emailed link to the set-password page.

        Django stores the token in the session and redirects off the URL that
        carries it, so the token must never end up in the final address.
        """
        response = self.client.get(token_url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="auth-form"')
        token = token_url.rstrip("/").rsplit("/", 1)[1]
        self.assertNotIn(token, response.redirect_chain[-1][0])
        return response.redirect_chain[-1][0]

    def test_reset_form_renders_without_the_app_chrome(self):
        response = self.client.get(reverse("account:password_reset"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="auth-form"')
        self._assert_standalone(response)

    def test_done_page_renders_without_the_app_chrome(self):
        self._request_reset_link()
        response = self.client.get(reverse("account:password_reset_done"))
        self.assertEqual(response.status_code, 200)
        self._assert_standalone(response)

    def test_complete_page_renders_without_the_app_chrome(self):
        response = self.client.get(reverse("account:password_reset_complete"))
        self.assertEqual(response.status_code, 200)
        self._assert_standalone(response)

    def test_reset_pages_are_never_cached(self):
        pages = [
            reverse("account:password_reset"),
            reverse("account:password_reset_done"),
            reverse("account:password_reset_complete"),
            self._open_reset_link(self._request_reset_link()),
        ]
        for url in pages:
            with self.subTest(url=url):
                self.assertIn("no-store", self.client.get(url)["Cache-Control"])

    def test_submit_sends_one_reset_email(self):
        self._request_reset_link()
        self.assertEqual(mail.outbox[0].to, [self.user.email])
        self.assertIn(TESTSERVER, mail.outbox[0].body)

    def test_unknown_email_gets_the_same_success_response(self):
        # Anti-enumeration: no account exists, but the response is identical to
        # a real request and nothing is sent.
        response = self.client.post(
            reverse("account:password_reset"), {"email": "nobody@example.com"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("account:password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)

    def test_full_reset_flow_changes_the_password(self):
        confirm = self.client.get(
            self._open_reset_link(self._request_reset_link())
        )
        self.assertEqual(confirm.status_code, 200)
        self.assertContains(confirm, 'class="auth-form"')
        self._assert_standalone(confirm)
        reset_url = confirm.wsgi_request.path

        response = self.client.post(
            reset_url,
            {"new_password1": "brand-new-pass-1", "new_password2": "brand-new-pass-1"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("account:password_reset_complete"))

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("brand-new-pass-1"))
        self.assertFalse(self.user.check_password("old-password-123"))

        # And the new password actually logs in.
        login = self.client.post(
            reverse("login"), {"username": "reset-user", "password": "brand-new-pass-1"}
        )
        self.assertEqual(login.status_code, 302)

    def test_invalid_token_shows_the_error_and_cannot_reset(self):
        bad_url = reverse(
            "account:password_reset_confirm",
            kwargs={"uidb64": "abcd", "token": "invalid"},
        )
        response = self.client.get(bad_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "invalid or has expired")
        self.assertNotContains(response, 'class="auth-form"')

        self.client.post(
            bad_url, {"new_password1": "brand-new-pass-1", "new_password2": "brand-new-pass-1"}
        )
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("old-password-123"))

    def test_reset_form_is_rate_limited_per_ip(self):
        for _ in range(5):
            self.client.post(reverse("account:password_reset"), {"email": self.user.email})
        response = self.client.post(
            reverse("account:password_reset"), {"email": self.user.email}
        )
        self.assertEqual(response.status_code, 429)
        self.assertContains(response, "Too many password reset requests", status_code=429)
        self._assert_standalone(response, status_code=429)
        self.assertEqual(len(mail.outbox), 5)

    def test_loading_the_reset_form_does_not_use_up_the_limit(self):
        for _ in range(20):
            self.client.get(reverse("account:password_reset"))
        response = self.client.post(
            reverse("account:password_reset"), {"email": self.user.email}
        )
        self.assertEqual(response.status_code, 302)
