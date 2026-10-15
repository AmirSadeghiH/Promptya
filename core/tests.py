"""Regression tests for request-level security: CSRF and client IP detection."""

import json

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from core.ratelimit import get_client_ip


class ClientIpTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _request(self, *, remote="10.0.0.5", forwarded=None):
        headers = {"REMOTE_ADDR": remote}
        if forwarded is not None:
            headers["HTTP_X_FORWARDED_FOR"] = forwarded
        return self.factory.get("/", **headers)

    @override_settings(TRUSTED_PROXY_COUNT=0)
    def test_without_a_proxy_the_forwarded_header_is_ignored(self):
        request = self._request(forwarded="1.2.3.4")
        self.assertEqual(get_client_ip(request), "10.0.0.5")

    @override_settings(TRUSTED_PROXY_COUNT=1)
    def test_a_client_cannot_spoof_its_address_by_prepending_to_the_header(self):
        # The attacker sends a fake first hop; nginx appends the real address.
        request = self._request(forwarded="9.9.9.9, 203.0.113.7")
        self.assertEqual(get_client_ip(request), "203.0.113.7")

    @override_settings(TRUSTED_PROXY_COUNT=1)
    def test_a_single_proxy_hop_reports_the_real_client(self):
        request = self._request(forwarded="203.0.113.7")
        self.assertEqual(get_client_ip(request), "203.0.113.7")

    @override_settings(TRUSTED_PROXY_COUNT=1)
    def test_a_missing_header_falls_back_to_the_socket_address(self):
        request = self._request(forwarded=None)
        self.assertEqual(get_client_ip(request), "10.0.0.5")

    @override_settings(TRUSTED_PROXY_COUNT=2)
    def test_a_header_shorter_than_the_proxy_count_is_not_trusted(self):
        request = self._request(forwarded="203.0.113.7")
        self.assertEqual(get_client_ip(request), "10.0.0.5")


class RateLimitIpSpoofingTests(TestCase):
    """The login limiter must count the real client, not a rotated header."""

    def setUp(self):
        cache.clear()

    @override_settings(TRUSTED_PROXY_COUNT=1)
    def test_rotating_the_forwarded_header_does_not_reset_the_login_limit(self):
        url = "/api/auth/login/"
        for attempt in range(10):
            # Each attempt claims a different first hop. The real client
            # address (appended last) is the same for all of them.
            self.client.post(
                url,
                data='{"username":"x","password":"y"}',
                content_type="application/json",
                HTTP_X_FORWARDED_FOR=f"198.51.100.{attempt}, 203.0.113.7",
                REMOTE_ADDR="127.0.0.1",
            )
        response = self.client.post(
            url,
            data='{"username":"x","password":"y"}',
            content_type="application/json",
            HTTP_X_FORWARDED_FOR="198.51.100.99, 203.0.113.7",
            REMOTE_ADDR="127.0.0.1",
        )
        self.assertEqual(response.status_code, 429)

    @override_settings(TRUSTED_PROXY_COUNT=1)
    def test_rotating_the_forwarded_header_does_not_reset_the_verify_limit(self):
        url = "/api/auth/verify-email/"
        for attempt in range(10):
            # Each attempt claims a different first hop. The real client
            # address (appended last) is the same for all of them.
            self.client.post(
                url,
                data='{"email":"x@example.com","code":"123456"}',
                content_type="application/json",
                HTTP_X_FORWARDED_FOR=f"198.51.100.{attempt}, 203.0.113.7",
                REMOTE_ADDR="127.0.0.1",
            )
        response = self.client.post(
            url,
            data='{"email":"x@example.com","code":"123456"}',
            content_type="application/json",
            HTTP_X_FORWARDED_FOR="198.51.100.99, 203.0.113.7",
            REMOTE_ADDR="127.0.0.1",
        )
        self.assertEqual(response.status_code, 429)


class CsrfProtectionTests(TestCase):
    """State-changing endpoints that spend credits must reject missing CSRF tokens."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="csrf-user", email="csrf-user@example.com", password="test-password",
        )
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.user)

    def test_generate_rejects_a_post_without_a_csrf_token(self):
        response = self.client.post(
            reverse("imagegen:generate"),
            data='{"prompt":"A mountain"}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_claim_challenge_rejects_a_post_without_a_csrf_token(self):
        response = self.client.post(
            reverse("credits:claim-challenge", args=["invite_friend"]),
            data='{"evidence":"1"}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)


class StateChangingEndpointCsrfTests(TestCase):
    """Every JSON endpoint that changes state must enforce CSRF.

    Each endpoint is hit twice: without a token (must be refused, 403) and with
    the token a real browser sends (must succeed). Without the second half, a
    fix that simply breaks the endpoint would look like a security win.
    """

    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.user = get_user_model().objects.create_user(
            username="csrf-check", email="csrf-check@example.com", password="test-password",
        )

    def _token(self):
        # A GET of the HTML login page renders {% csrf_token %} and sets the
        # csrftoken cookie, exactly as a browser receives it.
        self.client.get("/login/")
        return self.client.cookies["csrftoken"].value

    def _json(self, url, payload, token=None):
        headers = {"HTTP_X_CSRFTOKEN": token} if token else {}
        return self.client.post(
            url, data=json.dumps(payload), content_type="application/json", **headers,
        )

    def test_signup_requires_a_csrf_token(self):
        url = reverse("account:signup")
        payload = {"username": "newperson", "email": "newperson@example.com", "password": "long-enough-pw"}
        self.assertEqual(self._json(url, payload).status_code, 403)
        self.assertEqual(self._json(url, payload, self._token()).status_code, 201)

    def test_login_requires_a_csrf_token(self):
        url = reverse("account:login")
        payload = {"username": "csrf-check", "password": "test-password"}
        self.assertEqual(self._json(url, payload).status_code, 403)
        self.assertEqual(self._json(url, payload, self._token()).status_code, 200)

    def test_resend_verification_requires_a_csrf_token(self):
        url = reverse("account:resend-verification")
        payload = {"email": "csrf-check@example.com"}
        self.assertEqual(self._json(url, payload).status_code, 403)
        self.assertNotEqual(self._json(url, payload, self._token()).status_code, 403)

    def test_verify_email_code_requires_a_csrf_token(self):
        url = reverse("account:verify-email")
        payload = {"email": "csrf-check@example.com", "code": "123456"}
        self.assertEqual(self._json(url, payload).status_code, 403)
        self.assertNotEqual(self._json(url, payload, self._token()).status_code, 403)

    def test_post_create_requires_a_csrf_token(self):
        self.client.force_login(self.user)
        url = reverse("posts:post-create")
        payload = {"title": "A prompt", "post_type": "prompt", "prompt": "A quiet harbour at dawn"}
        self.assertEqual(self._json(url, payload).status_code, 403)
