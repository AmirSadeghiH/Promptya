"""Browser flow for the emailed 6-digit verification code.

The JSON API contract is covered in account/tests.py; these tests exercise
the standalone web pages: signup -> code entry -> success, the fallback
email+code form, server-side resend gating, shared rate-limit budgets,
anti-enumeration in fallback mode, and the retired link stub.
"""
import re
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from account.models import EmailVerificationToken
from account.views import issue_verification_code
from web.auth_views import EMAIL_VERIFICATION_SESSION_KEY

SIGNUP_PASSWORD = "super-secret-123"


def _code_from_outbox(index=0):
    """The 6-digit code as sent in the plain-text email body."""
    match = re.search(r"\b(\d{6})\b", mail.outbox[index].body)
    assert match, f"no 6-digit code in email {index}: {mail.outbox[index].body!r}"
    return match.group(1)


def _signup(client, username, email):
    return client.post(
        reverse("signup"),
        {"username": username, "email": email, "password": SIGNUP_PASSWORD},
    )


def _backdate(user):
    EmailVerificationToken.objects.filter(user=user).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )


def _wrong(code):
    return "000000" if code != "000000" else "111111"


class VerifyEmailPageTests(TestCase):
    """The standalone code-entry page reached after web signup."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def test_signup_redirects_to_code_page_and_sends_code_email(self):
        response = _signup(self.client, "verifyweb", "verifyweb@example.com")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("verify-email"))
        user = get_user_model().objects.get(email="verifyweb@example.com")
        self.assertFalse(user.is_verified)
        # The session pins the pending user; the user is NOT logged in
        self.assertEqual(
            self.client.session[EMAIL_VERIFICATION_SESSION_KEY], str(user.pk)
        )
        me = self.client.get(reverse("account:me"))
        self.assertEqual(me.status_code, 401)
        # Email invariants: code in the body, in no URL, nothing in the subject
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "Your Promptya verification code")
        self.assertNotRegex(mail.outbox[0].subject, r"\d")
        body = mail.outbox[0].body
        code = _code_from_outbox()
        self.assertIn(code, body)
        for url in re.findall(r"https?://\S+", body):
            self.assertEqual(url, "http://testserver/verify-email/")
            self.assertNotIn(code, url)

    def test_code_page_renders_standalone_in_session_mode(self):
        _signup(self.client, "verifyweb", "verifyweb@example.com")
        response = self.client.get(reverse("verify-email"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('class="auth-form"', content)
        self.assertIn('class="auth-email" dir="ltr"', content)
        self.assertIn("verifyweb@example.com", content)
        # Code entry input: numeric, LTR, one-time-code autofill
        self.assertIn('id="verify-code"', content)
        self.assertIn('inputmode="numeric"', content)
        self.assertIn('autocomplete="one-time-code"', content)
        # No app chrome
        self.assertNotContains(response, 'class="topbar"')
        self.assertNotContains(response, 'class="sidebar"')
        self.assertNotContains(response, 'class="bottom-nav"')
        self.assertNotContains(response, 'class="site-footer"')
        self.assertNotContains(response, 'id="nav-drawer"')
        # Fresh code: inbox note + server-anchored resend countdown
        self.assertIn("Check your inbox", content)
        self.assertIn("data-resend-at=", content)
        # Never cached
        self.assertIn("no-store", response["Cache-Control"])

    def test_code_page_fallback_without_session(self):
        user = get_user_model().objects.create_user(
            username="fallback", email="fallback@example.com", password="test-password",
        )
        issue_verification_code(user)

        # A different browser: no session key, so the page asks for email+code
        response = self.client.get(reverse("verify-email"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('id="verify-email-address"', content)
        self.assertIn('id="verify-code"', content)
        # No token state is leaked: no countdown, no email, no per-state note
        self.assertNotIn("data-resend-at=", content)
        self.assertNotIn("fallback@example.com", content)
        self.assertNotContains(response, 'class="topbar"')
        self.assertIn("no-store", response["Cache-Control"])

    def test_correct_code_verifies_and_shows_success(self):
        _signup(self.client, "verifyweb", "verifyweb@example.com")
        code = _code_from_outbox()

        response = self.client.post(reverse("verify-email"), {"code": code})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("verify-email-success"))
        user = get_user_model().objects.get(email="verifyweb@example.com")
        self.assertTrue(user.is_verified)
        self.assertIsNotNone(user.verification_token.used_at)

        response = self.client.get(reverse("verify-email-success"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Email verified!")
        self.assertContains(response, reverse("login"))
        self.assertNotContains(response, 'class="topbar"')
        self.assertIn("no-store", response["Cache-Control"])
        # The session key was consumed by the success page
        self.assertNotIn(EMAIL_VERIFICATION_SESSION_KEY, self.client.session)
        # Verify does not log in; the user logs in next
        self.assertEqual(self.client.get(reverse("account:me")).status_code, 401)

        # Replaying the consumed code fails with the generic message
        response = self.client.post(reverse("verify-email"), {"code": code})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Check the code in your email")
        self.assertTrue(user.is_verified)  # still verified, nothing un-done

    def test_wrong_code_counts_attempt_but_still_verifiable(self):
        _signup(self.client, "verifyweb", "verifyweb@example.com")
        code = _code_from_outbox()

        response = self.client.post(reverse("verify-email"), {"code": _wrong(code)})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Check the code in your email")
        user = get_user_model().objects.get(email="verifyweb@example.com")
        self.assertEqual(user.verification_token.attempts, 1)
        self.assertFalse(user.is_verified)

        response = self.client.post(reverse("verify-email"), {"code": code})
        self.assertEqual(response.status_code, 302)

    def test_five_wrong_codes_lock_the_code(self):
        _signup(self.client, "verifyweb", "verifyweb@example.com")
        code = _code_from_outbox()
        user = get_user_model().objects.get(email="verifyweb@example.com")

        for _ in range(5):
            self.client.post(reverse("verify-email"), {"code": _wrong(code)})
        self.assertEqual(user.verification_token.attempts, 5)
        # The page shows the locked state
        response = self.client.get(reverse("verify-email"))
        self.assertContains(response, "This code is no longer valid.")
        # Even the correct code fails while the code is locked
        self.assertEqual(
            self.client.post(reverse("verify-email"), {"code": code}).status_code, 200
        )

        # After expiry a resend issues a fresh, working code
        _backdate(user)
        response = self.client.post(reverse("verify-email-resend"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("verify-email") + "?resent=1")
        # The resend reset the attempt counter
        self.assertEqual(EmailVerificationToken.objects.get(user=user).attempts, 0)
        new_code = _code_from_outbox(index=1)
        self.assertEqual(
            self.client.post(reverse("verify-email"), {"code": code}).status_code, 200
        )
        response = self.client.post(reverse("verify-email"), {"code": new_code})
        self.assertEqual(response.status_code, 302)

    def test_expired_code_is_rejected_and_state_is_shown(self):
        _signup(self.client, "verifyweb", "verifyweb@example.com")
        code = _code_from_outbox()
        user = get_user_model().objects.get(email="verifyweb@example.com")
        _backdate(user)

        response = self.client.post(reverse("verify-email"), {"code": code})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Check the code in your email")
        self.assertFalse(user.is_verified)

        # GET shows the expired note; the resend is already available
        # (no countdown once the code is past its 2-minute life)
        response = self.client.get(reverse("verify-email"))
        self.assertContains(response, "This code has expired. Request a new one below.")
        self.assertNotIn("data-resend-at=", response.content.decode())

        # A resend now issues a working code
        response = self.client.post(reverse("verify-email-resend"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("verify-email") + "?resent=1")
        new_code = _code_from_outbox(index=1)
        self.assertEqual(
            self.client.post(reverse("verify-email"), {"code": new_code}).status_code,
            302,
        )

    def test_resend_before_expiry_is_a_noop(self):
        _signup(self.client, "verifyweb", "verifyweb@example.com")
        code = _code_from_outbox()
        self.assertEqual(len(mail.outbox), 1)

        response = self.client.post(reverse("verify-email-resend"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("verify-email") + "?wait=1")
        self.assertEqual(len(mail.outbox), 1)  # nothing new sent
        # The follow-up page explains the wait
        response = self.client.get(reverse("verify-email") + "?wait=1")
        self.assertContains(response, "Your current code is still valid.")

        # The original code still verifies
        self.assertEqual(
            self.client.post(reverse("verify-email"), {"code": code}).status_code, 302
        )

    def test_resend_after_expiry_sends_a_new_code(self):
        _signup(self.client, "verifyweb", "verifyweb@example.com")
        old_code = _code_from_outbox()
        user = get_user_model().objects.get(email="verifyweb@example.com")
        _backdate(user)

        response = self.client.post(reverse("verify-email-resend"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("verify-email") + "?resent=1")
        self.assertEqual(len(mail.outbox), 2)
        new_code = _code_from_outbox(index=1)

        self.assertEqual(
            self.client.post(reverse("verify-email"), {"code": old_code}).status_code, 200
        )
        response = self.client.post(reverse("verify-email"), {"code": new_code})
        self.assertEqual(response.status_code, 302)

    def test_resend_is_rate_limited_web(self):
        _signup(self.client, "verifyweb", "verifyweb@example.com")
        user = get_user_model().objects.get(email="verifyweb@example.com")
        for _ in range(3):
            _backdate(user)
            response = self.client.post(reverse("verify-email-resend"))
            self.assertEqual(response.status_code, 302)
        response = self.client.post(reverse("verify-email-resend"))
        self.assertEqual(response.status_code, 429)
        self.assertContains(
            response, "Too many verification codes requested", status_code=429
        )
        self.assertIn("no-store", response["Cache-Control"])

    def test_verify_is_rate_limited_web(self):
        _signup(self.client, "verifyweb", "verifyweb@example.com")
        code = _code_from_outbox()
        wrong = _wrong(code)
        for _ in range(10):
            self.assertEqual(
                self.client.post(reverse("verify-email"), {"code": wrong}).status_code,
                200,
            )
        response = self.client.post(reverse("verify-email"), {"code": code})
        self.assertEqual(response.status_code, 429)
        self.assertContains(
            response, "Too many verification attempts", status_code=429
        )
        self.assertIn("no-store", response["Cache-Control"])

    def test_gets_do_not_consume_the_verify_budget(self):
        _signup(self.client, "verifyweb", "verifyweb@example.com")
        for _ in range(20):
            self.client.get(reverse("verify-email"))
        code = _code_from_outbox()
        response = self.client.post(reverse("verify-email"), {"code": code})
        self.assertEqual(response.status_code, 302)

    def test_verify_web_and_api_share_one_budget(self):
        _signup(self.client, "verifyweb", "verifyweb@example.com")
        code = _code_from_outbox()
        wrong = _wrong(code)
        # 6 attempts through the JSON API, 4 through the web form...
        for _ in range(6):
            self.client.post(
                reverse("account:verify-email"),
                {"email": "verifyweb@example.com", "code": wrong},
                content_type="application/json",
            )
        for _ in range(4):
            self.assertEqual(
                self.client.post(reverse("verify-email"), {"code": wrong}).status_code,
                200,
            )
        # ...the 11th overall attempt is limited on either surface
        response = self.client.post(reverse("verify-email"), {"code": wrong})
        self.assertEqual(response.status_code, 429)
        response = self.client.post(
            reverse("account:verify-email"),
            {"email": "verifyweb@example.com", "code": wrong},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 429)
        body = response.json()
        self.assertEqual(body["error_code"], "rate_limited")
        self.assertEqual(body["retry_after"], 300)

    def test_resend_web_and_api_share_one_budget(self):
        _signup(self.client, "verifyweb", "verifyweb@example.com")
        user = get_user_model().objects.get(email="verifyweb@example.com")
        # 2 web resends + 1 JSON resend...
        for _ in range(2):
            _backdate(user)
            self.assertEqual(self.client.post(reverse("verify-email-resend")).status_code, 302)
        _backdate(user)
        self.assertEqual(
            self.client.post(
                reverse("account:resend-verification"),
                {"email": "verifyweb@example.com"},
                content_type="application/json",
            ).status_code,
            200,
        )
        # ...the 4th overall is limited
        response = self.client.post(reverse("verify-email-resend"))
        self.assertEqual(response.status_code, 429)

    def test_fallback_mode_does_not_reveal_account_state(self):
        user = get_user_model().objects.create_user(
            username="probe", email="probe@example.com", password="test-password",
        )
        code = issue_verification_code(user)
        wrong = _wrong(code)
        known = self.client.post(
            reverse("verify-email"), {"email": "probe@example.com", "code": wrong}
        )
        unknown = self.client.post(
            reverse("verify-email"), {"email": "ghost@example.com", "code": wrong}
        )
        self.assertEqual(known.status_code, 200)
        self.assertEqual(unknown.status_code, 200)
        # Identical apart from the rotating CSRF secret in the hidden input
        def strip_csrf(content):
            return re.sub(
                rb'name="csrfmiddlewaretoken" value="[^"]*"', b'X', content
            )

        self.assertEqual(strip_csrf(known.content), strip_csrf(unknown.content))

    def test_fallback_resend_is_generic_for_unknown_email(self):
        response = self.client.post(
            reverse("verify-email-resend"), {"email": "ghost@example.com"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("verify-email") + "?resent=1")
        self.assertEqual(len(mail.outbox), 0)
        # The follow-up page shows the generic note, not a real outcome
        response = self.client.get(reverse("verify-email") + "?resent=1")
        self.assertContains(
            response, "If the email exists and is unverified, a new code is on its way."
        )

    def test_retired_link_stub_renders_and_never_verifies(self):
        user = get_user_model().objects.create_user(
            username="retired", email="retired@example.com", password="test-password",
        )
        issue_verification_code(user)

        response = self.client.get(
            reverse("account:verify-email-link", args=["deadbeef"])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This verification link is no longer valid")
        self.assertContains(response, reverse("verify-email"))
        self.assertNotContains(response, 'class="topbar"')
        self.assertIn("no-store", response["Cache-Control"])
        # The stub never verifies
        user.refresh_from_db()
        self.assertFalse(user.is_verified)

    def test_stale_session_key_falls_back_to_email_form(self):
        verified = get_user_model().objects.create_user(
            username="stale",
            email="stale@example.com",
            password="test-password",
            is_verified=True,
        )
        self.client.session[EMAIL_VERIFICATION_SESSION_KEY] = str(verified.pk)
        self.client.session.save()
        response = self.client.get(reverse("verify-email"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="verify-email-address"')
        self.assertNotIn(EMAIL_VERIFICATION_SESSION_KEY, self.client.session)

        self.client.session[EMAIL_VERIFICATION_SESSION_KEY] = "999999"
        self.client.session.save()
        response = self.client.get(reverse("verify-email"))
        self.assertContains(response, 'id="verify-email-address"')
        self.assertNotIn(EMAIL_VERIFICATION_SESSION_KEY, self.client.session)

    def test_success_page_without_pending_verification_redirects(self):
        response = self.client.get(reverse("verify-email-success"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("verify-email"))
