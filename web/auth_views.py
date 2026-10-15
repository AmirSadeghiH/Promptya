from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from account.views import (
    _validate_username,
    can_resend_now,
    issue_verification_code,
    send_verification_code_email,
    verify_user_code,
)
from core.ratelimit import rate_limit_form

# Session key holding the PK of the user whose email is awaiting verification,
# set at web signup. It is an unguessable Django session — the pending user is
# never identified by anything the client sends.
EMAIL_VERIFICATION_SESSION_KEY = "email_verification_user_id"


def _auth_context(extra=None):
    """Context shared by every standalone auth page: it hides the app chrome."""
    return {"standalone": True, **(extra or {})}


def _render_limited(request, template, message):
    """The limited response: the same page the user was on, with a clear message."""
    response = render(request, template, _auth_context({"error": message}), status=429)
    return response


def _login_limited(request, message):
    return _render_limited(request, "web/login_new.html", message)


def _signup_limited(request, message):
    return _render_limited(request, "web/signup_new.html", message)


def _pending_verification_user(request):
    """Resolve the session's pending-verification user, or None.

    Returns None (and drops the key) when the key is missing, unparseable,
    or points at a deleted or already-verified user — in all of those cases
    the page falls back to the email+code form.
    """
    raw = request.session.get(EMAIL_VERIFICATION_SESSION_KEY)
    if not raw:
        return None
    try:
        user_id = int(raw)
    except (TypeError, ValueError):
        user_id = None
    user = (
        get_user_model()
        .objects.select_related("verification_token")
        .filter(pk=user_id)
        .first()
    ) if user_id is not None else None
    if user is None or user.is_verified:
        del request.session[EMAIL_VERIFICATION_SESSION_KEY]
        return None
    return user


def _verify_email_page_context(request, user, notice=None, error=None):
    """Context for the code-entry page: mode, token state, and resend anchor.

    ``resend_at`` (unix seconds, server-anchored) is only present while a live
    unexpired code exists — that is when the JS countdown gates the resend
    button. Fallback mode carries no state at all: it renders one generic
    alert for every failure, so it cannot be used to probe account or token
    state.
    """
    mode = "session" if user is not None else "fallback"
    state = None
    resend_at = None
    if user is not None:
        token = user.verification_token
        if token is None or not token.code_hash or token.used_at is not None:
            state = "no_code"
        elif timezone.now() >= token.expires_at:
            state = "expired"
        else:
            # While the issued code is unexpired — even attempt-locked — the
            # resend stays gated until it expires (the countdown keeps
            # running in the locked state).
            state = (
                "locked"
                if token.attempts >= settings.EMAIL_VERIFICATION_CODE_MAX_ATTEMPTS
                else "fresh"
            )
            resend_at = int(token.expires_at.timestamp())
    return _auth_context(
        {
            "mode": mode,
            "state": state,
            "email": user.email if user is not None else None,
            "resend_at": resend_at,
            "notice": notice,
            "error": error,
        }
    )


def _verify_email_limited(request, message):
    """The limited response: the code page with its full current state."""
    user = _pending_verification_user(request)
    return render(
        request,
        "web/verify_email.html",
        _verify_email_page_context(request, user, error=message),
        status=429,
    )


@never_cache
@rate_limit_form("login", limit=10, window_seconds=300, render_limited=_login_limited,
                 error_message="Too many login attempts. Try again in 5 minutes.")
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

    return render(request, "web/login_new.html", _auth_context({"error": error}))


@never_cache
@rate_limit_form("signup", limit=5, window_seconds=3600, render_limited=_signup_limited,
                 error_message="Too many signup attempts from this network. Try again in an hour.")
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

        # The browser's required/minlength/type=email attributes are hints only;
        # every rule is enforced here, with the same username rules as the API.
        username_error = _validate_username(username)
        if username_error:
            error = username_error
        elif "@" not in email or len(email) > 254:
            error = "A valid email is required."
        elif len(password) < 8:
            error = "Password must be at least 8 characters."
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

            # Issue and email the verification code, then go straight to the
            # code-entry page (no "check your email" interstitial — that page
            # is where the user waits for the code anyway).
            code = issue_verification_code(user)
            send_verification_code_email(request, user, code)
            request.session[EMAIL_VERIFICATION_SESSION_KEY] = str(user.pk)

            # Don't log in - user must verify email first
            return redirect("verify-email")

    return render(request, "web/signup_new.html", _auth_context({"error": error, "ref": ref}))


def logout_view(request):
    logout(request)
    return redirect("web:home")


@never_cache
@rate_limit_form("verify_email_code", limit=10, window_seconds=300, render_limited=_verify_email_limited,
                 error_message="Too many verification attempts. Try again in a few minutes.")
def verify_email_page(request):
    """Standalone code-entry page for the emailed 6-digit verification code.

    Session mode (the key set at signup) trusts only the session: any
    client-supplied email is ignored. Fallback mode (different device,
    cleared browser, or the emailed link's landing page) takes email + code;
    every failure there renders one identical generic alert.
    """
    user = _pending_verification_user(request)

    if request.method == "POST":
        if user is None:
            email = request.POST.get("email", "").strip().lower()
            target = (
                get_user_model()
                .objects.filter(email__iexact=email)
                .select_related("verification_token")
                .first()
            ) if email else None
        else:
            target = user

        if verify_user_code(target, request.POST.get("code", "")):
            return redirect("verify-email-success")

        # One generic message for every failure — a fallback POST with an
        # unknown email is indistinguishable from a wrong code.
        return render(
            request,
            "web/verify_email.html",
            _verify_email_page_context(
                request,
                _pending_verification_user(request),
                error="That code isn't valid. Check the code in your email, or request a new one below.",
            ),
        )

    notice = None
    if request.GET.get("resent") == "1":
        notice = "resent"
    elif request.GET.get("wait") == "1":
        notice = "wait"

    return render(
        request,
        "web/verify_email.html",
        _verify_email_page_context(request, user, notice=notice),
    )


@never_cache
@rate_limit_form("resend_verification", limit=3, window_seconds=3600, render_limited=_verify_email_limited,
                 error_message="Too many verification codes requested. Try again in an hour.")
@require_POST
def resend_code_page(request):
    """Resend the verification code (PRG: always answers with a redirect).

    The server re-issues only when the current code is absent, used, or
    expired — while it is still valid the request is a no-op, so the
    "resend after expiry" rule holds without trusting the client countdown.
    """
    user = _pending_verification_user(request)

    if user is None:
        email = request.POST.get("email", "").strip().lower()
        target = (
            get_user_model()
            .objects.filter(email__iexact=email)
            .select_related("verification_token")
            .first()
        ) if email else None
    else:
        target = user

    issued = False
    if target is not None and not target.is_verified and can_resend_now(target):
        code = issue_verification_code(target)
        send_verification_code_email(request, target, code)
        issued = True

    if user is not None:
        # Owner of the pending session: they may see the real outcome.
        # (resolve_url cannot take "name?query" — the path is reversed first.)
        notice = "resent" if issued else "wait"
        return redirect(f"{reverse('verify-email')}?{notice}=1")
    # Fallback mode: one generic outcome, indistinguishable in every case.
    return redirect(f"{reverse('verify-email')}?resent=1")


@never_cache
def verification_success_page(request):
    """PRG target of a successful code submission. No auto-login: the user
    logs in next, exactly as with the previous verify-then-login flow."""
    raw = request.session.get(EMAIL_VERIFICATION_SESSION_KEY)
    user = None
    if raw:
        try:
            user_id = int(raw)
        except (TypeError, ValueError):
            user_id = None
        if user_id is not None:
            user = get_user_model().objects.filter(pk=user_id).first()

    if user is not None and user.is_verified:
        del request.session[EMAIL_VERIFICATION_SESSION_KEY]
        return render(request, "web/verify_email_success.html", _auth_context({}))

    if raw:
        del request.session[EMAIL_VERIFICATION_SESSION_KEY]
    return redirect("verify-email")
