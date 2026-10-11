import json
import re
import secrets

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from core.ratelimit import rate_limit_ip
from interactions.models import Follow, Save
from posts.services import post_list_queryset, serialize_post
from posts.validation import validate_upload_file

# Usernames: letters, digits and _ . + - @ (mirrors Django's default
# username validator and the client-side pattern), 3–150 chars.
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_@.+-]{3,150}$")

# Handles that would shadow platform routes or impersonate the service.
RESERVED_USERNAMES = {
    "admin", "administrator", "api", "root", "support", "help", "about",
    "login", "logout", "signup", "register", "settings", "explore", "search",
    "create", "saved", "notifications", "category", "categories", "post",
    "posts", "feed", "profile", "offline", "static", "media", "promptya",
    "official", "staff", "mod", "moderator", "system", "null", "undefined",
}

MAX_BIOGRAPHY_LENGTH = 500


def _validate_username(new_username, *, current_user=None):
    """Server-side username rules. Returns an error string or None."""
    if not new_username:
        return "Username cannot be empty."
    if not USERNAME_PATTERN.match(new_username):
        return (
            "Usernames must be 3–150 characters and may only contain "
            "letters, numbers and _ . + - @"
        )
    if new_username.lower() in RESERVED_USERNAMES:
        return "This username is reserved."
    taken = get_user_model().objects.filter(username__iexact=new_username)
    if current_user is not None:
        if new_username.lower() == current_user.username.lower():
            return None
        taken = taken.exclude(pk=current_user.pk)
    if taken.exists():
        return "This username is already taken."
    return None


def _method_not_allowed():
    return JsonResponse({"error": "Method not allowed."}, status=405)


def _parse_body(request):
    try:
        data = json.loads(request.body.decode("utf-8")) if request.body else {}
    except (ValueError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def serialize_user(user, *, viewer=None, detailed=False):
    data = {
        "id": user.pk,
        "username": user.username,
        "display_name": user.display_name or user.username,
        "is_verified": user.is_verified,
        "profile_picture": user.profile_picture.url if user.profile_picture else None,
    }
    if detailed:
        follower_count = Follow.objects.filter(following=user).count()
        following_count = Follow.objects.filter(follower=user).count()
        data.update(
            {
                "biography": user.biography,
                "level": user.level,
                "experience": user.experience,
                "post_count": user.posts.count(),
                "follower_count": follower_count,
                "following_count": following_count,
            }
        )
        if viewer is not None and viewer.is_authenticated and viewer.pk != user.pk:
            data["is_following"] = Follow.objects.filter(
                follower=viewer, following=user
            ).exists()
    return data


@rate_limit_ip("signup", limit=5, window_seconds=3600, error_message="Too many signup attempts from this IP. Try again in an hour.")
@csrf_exempt
@require_POST
def signup(request):
    data = _parse_body(request)
    if data is None:
        return JsonResponse({"error": "Invalid JSON body."}, status=400)

    username = str(data.get("username", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))
    display_name = str(data.get("display_name", "")).strip()
    ref = str(data.get("ref", "")).strip()

    errors = {}
    username_error = _validate_username(username)
    if username_error:
        errors["username"] = username_error
    if "@" not in email:
        errors["email"] = "A valid email is required."
    if len(password) < 8:
        errors["password"] = "Password must be at least 8 characters."

    User = get_user_model()
    if not errors and User.objects.filter(email__iexact=email).exists():
        errors["email"] = "This email is already registered."
    if errors:
        return JsonResponse({"errors": errors}, status=400)

    user = User.objects.create_user(
        username=username,
        email=email,
        password=password,
        display_name=display_name or username,
    )
    if ref:
        # Stored as a *candidate* referral; the inviter is rewarded only after
        # this user completes a real generation AND verifies their email
        # (see credits.challenges).
        referrer = User.objects.filter(username__iexact=ref).exclude(pk=user.pk).first()
        if referrer is not None:
            user.referred_by = referrer
            user.save(update_fields=["referred_by"])

    # Create and send verification token
    token = _create_verification_token(user)
    _send_verification_email(request, user, token)

    # Don't log in - user must verify email first
    return JsonResponse(
        {
            "success": True,
            "message": "Account created. Please check your email to verify your address.",
            "email_sent": True,
        },
        status=201,
    )


@rate_limit_ip("login", limit=10, window_seconds=300, error_message="Too many login attempts. Try again in 5 minutes.")
@csrf_exempt
@require_POST
def api_login(request):
    data = _parse_body(request)
    if data is None:
        return JsonResponse({"error": "Invalid JSON body."}, status=400)

    identifier = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))

    User = get_user_model()
    user = None
    lookup = Q(username__iexact=identifier) | Q(email__iexact=identifier)
    found = User.objects.filter(lookup).first()
    if found:
        user = authenticate(request, username=found.username, password=password)

    if user is None:
        return JsonResponse({"error": "Invalid credentials."}, status=400)

    login(request, user)
    return JsonResponse({"user": serialize_user(user, detailed=True)})


@require_POST
def api_logout(request):
    logout(request)
    return JsonResponse({"logged_out": True})


def me(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required."}, status=401)
    return JsonResponse(
        {"user": serialize_user(request.user, viewer=request.user, detailed=True)}
    )


def profile_detail(request, username):
    if request.method != "GET":
        return _method_not_allowed()

    user = get_object_or_404(
        get_user_model().objects.annotate(post_count=Count("posts")),
        username=username,
    )
    viewer = request.user if request.user.is_authenticated else None
    data = serialize_user(user, viewer=viewer, detailed=True)
    data["posts"] = [
        serialize_post(post, viewer=viewer)
        for post in post_list_queryset(viewer).filter(author=user)[:12]
    ]
    return JsonResponse({"user": data})


@login_required
def profile_update(request):
    if request.method not in ("PUT", "PATCH"):
        return _method_not_allowed()

    data = _parse_body(request)
    if data is None:
        return JsonResponse({"error": "Invalid JSON body."}, status=400)

    user = request.user
    if "display_name" in data:
        user.display_name = str(data["display_name"]).strip()[:100]
    if "biography" in data:
        user.biography = str(data["biography"]).strip()[:MAX_BIOGRAPHY_LENGTH]
    if "username" in data:
        new_username = str(data["username"]).strip()
        username_error = _validate_username(new_username, current_user=user)
        if username_error:
            return JsonResponse({"errors": {"username": username_error}}, status=400)
        user.username = new_username
    user.save()
    return JsonResponse({"user": serialize_user(user, detailed=True)})


@login_required
def profile_update_multipart(request):
    """Profile edit via multipart/form-data — display name, bio, username, avatar."""
    if request.method not in ("POST", "PUT", "PATCH"):
        return _method_not_allowed()

    user = request.user
    errors = {}

    if "display_name" in request.POST:
        user.display_name = request.POST.get("display_name", "").strip()[:100]

    if "biography" in request.POST:
        user.biography = request.POST.get("biography", "").strip()[:MAX_BIOGRAPHY_LENGTH]

    if "username" in request.POST:
        new_username = request.POST.get("username", "").strip()
        username_error = _validate_username(new_username, current_user=user)
        if username_error:
            errors["username"] = username_error
        else:
            user.username = new_username

    remove_picture = request.POST.get("remove_picture") == "1"

    picture = request.FILES.get("profile_picture")
    if picture:
        try:
            validate_upload_file(picture, "image")
        except ValidationError as exc:
            errors["profile_picture"] = "; ".join(exc.messages)

    # Bail out before touching any files on disk — otherwise a rejected
    # update could still delete the old avatar, leaving a dangling reference.
    if errors:
        return JsonResponse({"errors": errors}, status=400)

    old_picture = user.profile_picture if (picture or remove_picture) else None
    if remove_picture:
        user.profile_picture = None
    if picture:
        user.profile_picture = picture

    user.save()

    # Only delete the previous file once the new state is safely persisted.
    if old_picture:
        old_picture.delete(save=False)

    return JsonResponse({"user": serialize_user(user, viewer=user, detailed=True)})


@login_required
def change_password(request):
    """Change password: verifies the current one before applying the new."""
    if request.method != "POST":
        return _method_not_allowed()

    data = _parse_body(request)
    if data is None:
        return JsonResponse({"error": "Invalid JSON body."}, status=400)

    current = str(data.get("current_password", ""))
    new_password = str(data.get("new_password", ""))

    if not request.user.check_password(current):
        return JsonResponse({"errors": {"current_password": "Current password is incorrect."}}, status=400)

    try:
        from django.contrib.auth.password_validation import validate_password
        validate_password(new_password, user=request.user)
    except ValidationError as exc:
        return JsonResponse({"errors": {"new_password": "; ".join(exc.messages)}}, status=400)

    request.user.set_password(new_password)
    request.user.save()
    # set_password invalidates the session hash — keep the user logged in.
    from django.contrib.auth import update_session_auth_hash
    update_session_auth_hash(request, request.user)
    return JsonResponse({"success": True})


@login_required
def saved_posts(request):
    if request.method != "GET":
        return _method_not_allowed()

    save_rows = list(
        Save.objects.filter(user=request.user)
        .select_related("post")
        .order_by("-created_at", "-pk")
    )
    if not save_rows:
        return JsonResponse({"results": []})

    posts = {
        post.pk: post
        for post in post_list_queryset(request.user).filter(
            pk__in=[row.post_id for row in save_rows]
        )
    }
    ordered = [posts[row.post_id] for row in save_rows if row.post_id in posts]
    return JsonResponse(
        {"results": [serialize_post(post, viewer=request.user) for post in ordered]}
    )


# ---------------------------------------------------------------------------
# Email Verification
# ---------------------------------------------------------------------------


def _create_verification_token(user):
    """Create or replace a verification token for the user."""
    from account.models import EmailVerificationToken

    token = secrets.token_urlsafe(32)
    expires_at = timezone.now() + timezone.timedelta(seconds=120) #2 minutes

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


@rate_limit_ip("resend_verification", limit=3, window_seconds=3600, error_message="Too many verification emails sent. Try again in an hour.")
@csrf_exempt
@require_POST
def resend_verification(request):
    """Resend verification email to the user."""
    data = _parse_body(request)
    if data is None:
        return JsonResponse({"error": "Invalid JSON body."}, status=400)

    email = str(data.get("email", "")).strip().lower()
    if not email:
        return JsonResponse({"error": "Email is required."}, status=400)

    User = get_user_model()
    user = User.objects.filter(email__iexact=email).first()

    # Always return success to prevent email enumeration
    if user is None or user.is_verified:
        return JsonResponse({"success": True, "message": "If the email exists and is unverified, a verification link has been sent."})

    token = _create_verification_token(user)
    _send_verification_email(request, user, token)

    return JsonResponse({"success": True, "message": "If the email exists and is unverified, a verification link has been sent."})


def verify_email(request, token):
    """Verify email using token from email link."""
    from account.models import EmailVerificationToken

    try:
        verification = EmailVerificationToken.objects.select_related("user").get(token=token)
    except EmailVerificationToken.DoesNotExist:
        return render(request, "account/verification_failed.html", {"error": "invalid_token"})

    if not verification.is_valid():
        if verification.used_at:
            return render(request, "account/verification_failed.html", {"error": "already_used"})
        return render(request, "account/verification_failed.html", {"error": "expired"})

    user = verification.user
    if user.is_verified:
        verification.mark_used()
        return render(request, "account/verification_failed.html", {"error": "already_verified"})

    # Mark user as verified and token as used
    user.is_verified = True
    user.save(update_fields=["is_verified"])
    verification.mark_used()

    return render(request, "account/verification_success.html", {"user": user})


@rate_limit_ip("resend_verification_page", limit=3, window_seconds=3600, error_message="Too many requests. Try again in an hour.")
def resend_verification_page(request):
    """Page to resend verification email."""
    if request.method == "POST":
        email = request.POST.get("email", "").strip().lower()
        if not email:
            return render(request, "account/resend_verification.html", {"error": "Email is required."})

        User = get_user_model()
        user = User.objects.filter(email__iexact=email).first()

        # Always return success to prevent email enumeration
        if user is None or user.is_verified:
            return render(request, "account/resend_verification.html", {"success": "If the email exists and is unverified, a verification link has been sent."})

        token = _create_verification_token(user)
        _send_verification_email(request, user, token)

        return render(request, "account/resend_verification.html", {"success": "If the email exists and is unverified, a verification link has been sent."})

    return render(request, "account/resend_verification.html")
