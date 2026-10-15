import json
import re
import secrets

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db.models import Count, F, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from account.models import EmailVerificationToken
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
        # `profile_detail` annotates post_count; reuse it instead of running a
        # second COUNT against the same table.
        post_count = getattr(user, "post_count", None)
        if post_count is None:
            post_count = user.posts.count()
        data.update(
            {
                "biography": user.biography,
                "level": user.level,
                "experience": user.experience,
                "post_count": post_count,
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

    # Issue and email the verification code
    code = issue_verification_code(user)
    send_verification_code_email(request, user, code)

    # Don't log in - user must verify email first
    return JsonResponse(
        {
            "success": True,
            "message": "Account created. We sent a 6-digit verification code to your email. Enter it to verify your address.",
            "email_sent": True,
        },
        status=201,
    )


@rate_limit_ip("login", limit=10, window_seconds=300, error_message="Too many login attempts. Try again in 5 minutes.")
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

    # Ids only — the post rows themselves come from post_list_queryset,
    # which attaches the engagement counts and viewer flags the serializer
    # needs. select_related("post") would load every post twice.
    saved_ids = list(
        Save.objects.filter(user=request.user)
        .order_by("-created_at", "-pk")
        .values_list("post_id", flat=True)
    )
    if not saved_ids:
        return JsonResponse({"results": []})

    posts = {
        post.pk: post
        for post in post_list_queryset(request.user).filter(pk__in=saved_ids)
    }
    ordered = [posts[post_id] for post_id in saved_ids if post_id in posts]
    return JsonResponse(
        {"results": [serialize_post(post, viewer=request.user) for post in ordered]}
    )


# ---------------------------------------------------------------------------
# Email verification (code/OTP)
# ---------------------------------------------------------------------------
#
# A 6-digit code is emailed at signup, valid for exactly
# EMAIL_VERIFICATION_CODE_TTL_SECONDS, and entered on the standalone
# /verify-email/ page. Only the code's salted hash is stored. These
# functions are the single implementation shared by the JSON API and the
# web views (web/auth_views.py).

# A throwaway hash so every failed check runs exactly one check_password:
# response timing must not reveal whether an email, code, or attempt state
# exists.
_DUMMY_CODE_HASH = make_password("000000")

_GENERIC_CODE_FAILURE = "The code is incorrect or has expired. Request a new code if needed."


def _normalize_code(raw):
    """Digits only — everything else in the field is dropped."""
    return "".join(ch for ch in (raw or "") if ch in "0123456789")


def generate_verification_code():
    """A uniform 6-digit code from the CSPRNG (leading zeros kept)."""
    length = settings.EMAIL_VERIFICATION_CODE_LENGTH
    return f"{secrets.randbelow(10 ** length):0{length}d}"


def issue_verification_code(user):
    """Issue (or replace) the user's verification code; return it in clear.

    Supersedes any existing row: the previous code stops working immediately,
    so a "slow mail lands after a resend" situation cannot verify with the old
    code.
    """
    code = generate_verification_code()
    EmailVerificationToken.objects.update_or_create(
        user=user,
        defaults={
            "code_hash": make_password(code),
            "attempts": 0,
            "expires_at": timezone.now()
            + timezone.timedelta(seconds=settings.EMAIL_VERIFICATION_CODE_TTL_SECONDS),
            "used_at": None,
        },
    )
    return code


def can_resend_now(user):
    """Whether a new code may be emailed to this (unverified) user.

    While an issued, unexpired, unused code exists, resending is a
    server-side no-op — the "resend after expiry" rule holds even for a
    client without JS, and there is at most one live code.
    """
    try:
        token = user.verification_token
    except EmailVerificationToken.DoesNotExist:
        return True
    if not token.code_hash or token.used_at is not None:
        return True
    return timezone.now() >= token.expires_at


def send_verification_code_email(request, user, code):
    """Email the code to the user.

    The link goes to the bare /verify-email/ page — the code itself is never
    put in a URL, so it cannot leak through the Referer header or history.
    """
    verify_url = request.build_absolute_uri("/verify-email/")
    context = {
        "user": user,
        "code": code,
        "verify_url": verify_url,
        "site_name": getattr(settings, "SITE_URL", "").rstrip("/")
        or request.get_host(),
    }
    subject = render_to_string("account/verification_email_subject.txt").strip()
    html_message = render_to_string("account/verification_email.html", context)
    plain_message = render_to_string("account/verification_email.txt", context)

    send_mail(
        subject,
        plain_message,
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        html_message=html_message,
        fail_silently=False,
    )


def verify_user_code(user, code):
    """Check ``code`` against the user's issued code; True only on success.

    Exactly one check_password runs on every path (the dummy hash when there
    is no live code), so timing reveals nothing. A wrong 6-digit entry
    increments the row's attempt counter with an F() expression, so the
    per-code cap holds even across rotating IPs. Malformed input (not 6
    digits) consumes no attempt.
    """
    normalized = _normalize_code(code)
    if (
        user is None
        or user.is_verified
        or len(normalized) != settings.EMAIL_VERIFICATION_CODE_LENGTH
    ):
        check_password("000000", _DUMMY_CODE_HASH)
        return False

    try:
        token = user.verification_token
    except EmailVerificationToken.DoesNotExist:
        token = None

    if (
        token is None
        or not token.code_hash
        or token.used_at is not None
        or token.attempts >= settings.EMAIL_VERIFICATION_CODE_MAX_ATTEMPTS
        or timezone.now() >= token.expires_at
    ):
        check_password("000000", _DUMMY_CODE_HASH)
        return False

    if check_password(normalized, token.code_hash):
        user.is_verified = True
        user.save(update_fields=["is_verified"])
        token.mark_used()
        return True

    EmailVerificationToken.objects.filter(pk=token.pk).update(
        attempts=F("attempts") + 1
    )
    return False


@rate_limit_ip("verify_email_code", limit=10, window_seconds=300, error_message="Too many verification attempts. Try again in a few minutes.")
@require_POST
def verify_email_code(request):
    """Verify the email address with the emailed 6-digit code. JSON {email, code}.

    Every failure mode returns the same 400 body, so the response cannot be
    used to tell an unknown email apart from a wrong, expired, or used code.
    """
    data = _parse_body(request)
    email = str(data.get("email", "")).strip().lower() if data else ""
    code = str(data.get("code", "")) if data else ""

    user = None
    if email:
        user = (
            get_user_model()
            .objects.filter(email__iexact=email)
            .select_related("verification_token")
            .first()
        )

    if verify_user_code(user, code):
        return JsonResponse({"success": True, "message": "Your email has been verified."})
    return JsonResponse(
        {"success": False, "message": _GENERIC_CODE_FAILURE}, status=400
    )


@rate_limit_ip("resend_verification", limit=3, window_seconds=3600, error_message="Too many verification codes requested. Try again in an hour.")
@require_POST
def resend_verification(request):
    """Resend a verification code. JSON {email}.

    Always returns the same generic success, so it cannot be used to tell a
    known email from an unknown one. A code is actually sent only when the
    email exists, is unverified, and the previous code has expired or never
    existed.
    """
    data = _parse_body(request)
    email = str(data.get("email", "")).strip().lower() if data else ""

    user = None
    if email:
        user = (
            get_user_model()
            .objects.filter(email__iexact=email)
            .select_related("verification_token")
            .first()
        )

    if user is not None and not user.is_verified and can_resend_now(user):
        code = issue_verification_code(user)
        send_verification_code_email(request, user, code)

    return JsonResponse(
        {
            "success": True,
            "message": "If the email exists and is unverified, a new verification code is on its way.",
        }
    )


@never_cache
@require_GET
def verification_link_retired(request, token):
    """Retired link flow: a standalone notice. Never verifies anything.

    Link emails sent before the switch to codes land here (not on a 404) and
    are pointed at /verify-email/. The token segment is deliberately ignored —
    no lookup, no user row touched.
    """
    return render(request, "account/verification_link_retired.html")
