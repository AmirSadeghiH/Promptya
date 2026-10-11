from django.urls import path
from django.contrib.auth import views as auth_views

from account import views

app_name = "account"

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

    # Email verification
    path("auth/verify-email/<str:token>/", views.verify_email, name="verify-email"),
    path("auth/resend-verification/", views.resend_verification, name="resend-verification"),
    path("resend-verification/", views.resend_verification_page, name="resend-verification-page"),

    # Password reset (uses Django's built-in views with custom templates)
    path(
        "auth/password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name="account/password_reset_form.html",
            email_template_name="account/password_reset_email.html",
            subject_template_name="account/password_reset_subject.txt",
            success_url="/password-reset/done/",
        ),
        name="password_reset",
    ),
    path(
        "auth/password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="account/password_reset_done.html"
        ),
        name="password_reset_done",
    ),
    path(
        "auth/password-reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="account/password_reset_confirm.html",
            success_url="/password-reset/complete/",
        ),
        name="password_reset_confirm",
    ),
    path(
        "auth/password-reset/complete/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="account/password_reset_complete.html"
        ),
        name="password_reset_complete",
    ),
]
