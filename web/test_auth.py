from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class StandaloneAuthPageTests(TestCase):
    """Login and signup are focused pages: no app chrome, but a real form."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.user = get_user_model().objects.create_user(
            username="standalone-user",
            email="standalone-user@example.com",
            password="correct-horse-battery",
            is_verified=True,
        )

    def test_login_renders_a_form_without_the_app_chrome(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="auth-form"')
        self.assertNotContains(response, 'class="topbar"')
        self.assertNotContains(response, 'class="sidebar"')
        self.assertNotContains(response, 'class="bottom-nav"')
        self.assertNotContains(response, 'class="site-footer"')
        self.assertNotContains(response, 'id="nav-drawer"')

    def test_signup_renders_a_form_without_the_app_chrome(self):
        response = self.client.get(reverse("signup"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="auth-form"')
        self.assertNotContains(response, 'class="topbar"')
        self.assertNotContains(response, 'class="site-footer"')

    def test_other_pages_still_render_the_app_chrome(self):
        response = self.client.get(reverse("web:home"))
        self.assertContains(response, 'class="topbar"')
        self.assertContains(response, 'class="site-footer"')

    def test_auth_pages_are_never_cached(self):
        for name in ("login", "signup", "verify-email", "verify-email-success"):
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertIn("no-store", response["Cache-Control"])

    def test_wrong_password_does_not_log_in(self):
        response = self.client.post(
            reverse("login"), {"username": "standalone-user", "password": "wrong"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid username or password.")
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_correct_password_logs_in_and_redirects(self):
        response = self.client.post(
            reverse("login"),
            {"username": "standalone-user", "password": "correct-horse-battery"},
        )
        self.assertEqual(response.status_code, 302)

    def test_login_is_rate_limited_per_ip(self):
        for _ in range(10):
            self.client.post(reverse("login"), {"username": "x", "password": "y"})
        response = self.client.post(reverse("login"), {"username": "x", "password": "y"})
        self.assertEqual(response.status_code, 429)
        self.assertContains(response, "Too many login attempts", status_code=429)

    def test_loading_the_login_form_does_not_use_up_the_limit(self):
        for _ in range(20):
            self.client.get(reverse("login"))
        response = self.client.post(reverse("login"), {"username": "x", "password": "y"})
        self.assertEqual(response.status_code, 200)

    def test_signup_rejects_a_reserved_username_on_the_server(self):
        response = self.client.post(
            reverse("signup"),
            {"username": "admin", "email": "new@example.com", "password": "long-enough-pw"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(get_user_model().objects.filter(email="new@example.com").exists())

    def test_signup_rejects_a_malformed_email_on_the_server(self):
        response = self.client.post(
            reverse("signup"),
            {"username": "newperson", "email": "not-an-email", "password": "long-enough-pw"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A valid email is required.")
        self.assertFalse(get_user_model().objects.filter(username="newperson").exists())

    def test_signup_rejects_a_short_password(self):
        response = self.client.post(
            reverse("signup"),
            {"username": "newperson", "email": "new@example.com", "password": "short"},
        )
        self.assertContains(response, "Password must be at least 8 characters.")

    def test_signup_is_rate_limited_per_ip(self):
        for index in range(5):
            self.client.post(
                reverse("signup"),
                {"username": f"bad{index}!", "email": "x@example.com", "password": "long-enough-pw"},
            )
        response = self.client.post(
            reverse("signup"),
            {"username": "fine_name", "email": "fine@example.com", "password": "long-enough-pw"},
        )
        self.assertEqual(response.status_code, 429)
