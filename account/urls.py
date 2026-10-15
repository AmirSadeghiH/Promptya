from django.contrib.auth import views as auth_views
from django.shortcuts import render
from django.urls import path, reverse_lazy
from django.views.decorators.cache import never_cache

from core.ratelimit import rate_limit_form

from account import views

app_name = "account"


def _password_reset_limited(request, message):
    """The limited response: the standalone reset form with a clear message."""
    return render(request, "account/password_reset_form.html", {"error": message}, status=429)


# Sending a reset email is an abuse vector (email bombing), so submissions are
# rate-limited per IP, like signup and the verification resend.
password_reset_view = never_cache(
    rate_limit_form(
        "password_reset",
        limit=5,
        window_seconds=3600,
        render_limited=_password_reset_limited,
        error_message="Too many password reset requests. Try again in an hour.",
    )(
        auth_views.PasswordResetView.as_view(
            template_name="account/password_reset_form.html",
            email_template_name="account/password_reset_email.html",
            subject_template_name="account/password_reset_subject.txt",
            success_url=reverse_lazy("account:password_reset_done"),
        )
    )
)


urlpatterns = [
    path("auth/signup/", views.signup, name="signup"),
    path("auth/login/", views.api_login, name="login"),
    path("auth/logout/", views.api_logout, name="logout"),
    path("auth/me/", views.me, name="me"),
    path("me/update/", views.profile_update, name="profile-update"),
    path("me/profile/", views.profile_update_multipart, name="profile-multipart"),
    path("me/password/", views.change_password, name="change-password"),
    path("me/saved/", views.saved_posts, name="saved-posts"),
    path("users/<str:username>/", views.profile_detail, name="profile-detail"),

    # Email verification (6-digit code)
    path("auth/verify-email/", views.verify_email_code, name="verify-email"),
    # Retired link flow: notice page only, never verifies.
    path("auth/verify-email/<str:token>/", views.verification_link_retired, name="verify-email-link"),
    path("auth/resend-verification/", views.resend_verification, name="resend-verification"),

    # Password reset (Django's built-in views with standalone templates)
    path("auth/password-reset/", password_reset_view, name="password_reset"),
    path(
        "auth/password-reset/done/",
        never_cache(auth_views.PasswordResetDoneView.as_view(
            template_name="account/password_reset_done.html"
        )),
        name="password_reset_done",
    ),
    path(
        "auth/password-reset/<uidb64>/<token>/",
        never_cache(auth_views.PasswordResetConfirmView.as_view(
            template_name="account/password_reset_confirm.html",
            success_url=reverse_lazy("account:password_reset_complete"),
        )),
        name="password_reset_confirm",
    ),
    path(
        "auth/password-reset/complete/",
        never_cache(auth_views.PasswordResetCompleteView.as_view(
            template_name="account/password_reset_complete.html"
        )),
        name="password_reset_complete",
    ),
]
