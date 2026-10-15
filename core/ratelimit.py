"""Simple rate limiting utilities using Django's cache framework."""

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from functools import wraps


def get_client_ip(request):
    """The client address as seen by the nearest trusted proxy.

    ``X-Forwarded-For`` is a list the *client* can prepend to, so its first
    entry is attacker-controlled. Only the entries appended by proxies we run
    are trustworthy. With ``TRUSTED_PROXY_COUNT`` proxies in front of Django,
    the real client is the entry that the outermost trusted proxy appended:
    the Nth address from the right. With no proxy (the default), the header is
    ignored and ``REMOTE_ADDR`` is used.
    """
    proxy_count = int(getattr(settings, "TRUSTED_PROXY_COUNT", 0) or 0)
    if proxy_count > 0:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
        if len(hops) >= proxy_count:
            return hops[-proxy_count]
    return request.META.get("REMOTE_ADDR", "unknown")


def _hit(cache_key, limit, window_seconds):
    """Count one attempt. Returns True when the caller is still under the limit."""
    current = cache.get(cache_key, 0)
    if current >= limit:
        return False
    cache.set(cache_key, current + 1, window_seconds)
    return True


def rate_limit(key_prefix, limit, window_seconds, key_func=None, error_message=None):
    """Decorator to rate limit a view.

    Args:
        key_prefix: Prefix for cache key (e.g., "signup", "generate")
        limit: Maximum requests allowed in window
        window_seconds: Time window in seconds
        key_func: Optional function(request) -> str to customize key
        error_message: Custom error message
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if key_func:
                key_suffix = key_func(request)
            elif request.user.is_authenticated:
                key_suffix = f"user:{request.user.pk}"
            else:
                key_suffix = f"ip:{get_client_ip(request)}"

            cache_key = f"ratelimit:{key_prefix}:{key_suffix}"

            if not _hit(cache_key, limit, window_seconds):
                return JsonResponse(
                    {
                        "error_code": "rate_limited",
                        "error": error_message or f"Too many requests. Try again later.",
                        "retry_after": window_seconds,
                    },
                    status=429,
                )
            return view_func(request, *args, **kwargs)
        return wrapped
    return decorator


def rate_limit_form(key_prefix, limit, window_seconds, render_limited, error_message=None):
    """Rate limit a browser form by IP, answering with a page instead of JSON.

    Same counter as ``rate_limit_ip``, so a form and the JSON API cannot be used
    as two separate budgets. ``render_limited(request, message)`` builds the page
    shown when the limit is hit, with status 429.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            # Only submissions count. Loading the form must not use up the budget.
            if request.method != "POST":
                return view_func(request, *args, **kwargs)
            cache_key = f"ratelimit:{key_prefix}:ip:{get_client_ip(request)}"
            if not _hit(cache_key, limit, window_seconds):
                message = error_message or "Too many attempts. Try again later."
                return render_limited(request, message)
            return view_func(request, *args, **kwargs)
        return wrapped
    return decorator


def rate_limit_ip(key_prefix, limit, window_seconds, error_message=None):
    """Rate limit by IP only (for unauthenticated endpoints)."""
    return rate_limit(
        key_prefix,
        limit,
        window_seconds,
        key_func=lambda r: f"ip:{get_client_ip(r)}",
        error_message=error_message,
    )


def rate_limit_user(key_prefix, limit, window_seconds, error_message=None):
    """Rate limit by authenticated user."""
    return rate_limit(
        key_prefix,
        limit,
        window_seconds,
        key_func=lambda r: f"user:{r.user.pk}" if r.user.is_authenticated else f"ip:{get_client_ip(r)}",
        error_message=error_message,
    )