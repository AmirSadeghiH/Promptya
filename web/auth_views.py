from django.contrib.auth import authenticate, get_user_model, login, logout
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
import secrets


def _create_verification_token(user):
    """Create or replace a verification token for the user."""
    from account.models import EmailVerificationToken

    token = secrets.token_urlsafe(32)
    expires_at = timezone.now() + timezone.timedelta(hours=24)

    EmailVerificationToken.objects.update_or_create(
        user=user,
        defaults={
            "token": token,
            "expires_at": expires_at,
            "used_at": None,
        },
    )
    return token


def _send_verification_email(request, user, token):
    """Send verification email to the user."""
    verify_url = request.build_absolute_uri(
        f"/api/auth/verify-email/{token}/"
    )

    subject = render_to_string("account/verification_email_subject.txt").strip()
    html_message = render_to_string(
        "account/verification_email.html",
        {
            "user": user,
            "verify_url": verify_url,
            "site_name": getattr(settings, "SITE_URL", "").rstrip("/")
            or request.get_host(),
        },
    )
    plain_message = render_to_string(
        "account/verification_email.txt",
        {
            "user": user,
            "verify_url": verify_url,
            "site_name": getattr(settings, "SITE_URL", "").rstrip("/")
            or request.get_host(),
        },
    )

    send_mail(
        subject,
        plain_message,
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        html_message=html_message,
        fail_silently=False,
    )


def login_page(request):
    if request.user.is_authenticated:
        return redirect("web:home")

    error = None
    if request.method == "POST":
        identifier = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        User = get_user_model()
        found = User.objects.filter(
            username__iexact=identifier
        ).first() or User.objects.filter(email__iexact=identifier).first()
        user = authenticate(request, username=found.username, password=password) if found else None
        if user:
            login(request, user)
            return redirect("web:home")
        error = "Invalid username or password."

    return render(request, "web/login.html", {"error": error})


def signup_page(request):
    if request.user.is_authenticated:
        return redirect("web:home")

    # A ?ref=username link carries the inviter through the form.  The referral
    # is only *recorded* here; the reward waits for the friend's first image.
    ref = (request.POST.get("ref") or request.GET.get("ref") or "").strip()
    error = None
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip().lower()
        password = request.POST.get("password", "")
        User = get_user_model()

        if len(password) < 8:
            error = "Password must be at least 8 characters."
        elif User.objects.filter(username__iexact=username).exists():
            error = "This username is already taken."
        elif User.objects.filter(email__iexact=email).exists():
            error = "This email is already registered."
        else:
            user = User.objects.create_user(
                username=username, email=email, password=password, display_name=username
            )
            referrer = User.objects.filter(username__iexact=ref).exclude(pk=user.pk).first()
            if referrer is not None:
                user.referred_by = referrer
                user.save(update_fields=["referred_by"])

            # Create and send verification token
            token = _create_verification_token(user)
            _send_verification_email(request, user, token)

            # Don't log in - user must verify email first
            return render(request, "web/verification_sent.html", {"email": email})

    return render(request, "web/signup.html", {"error": error, "ref": ref})


def logout_view(request):
    logout(request)
    return redirect("web:home")
