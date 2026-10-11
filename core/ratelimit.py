"""Simple rate limiting utilities using Django's cache framework."""

from django.core.cache import cache
from django.http import JsonResponse
from functools import wraps


def get_client_ip(request):
    """Extract client IP from request."""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0].strip()
    else:
        ip = request.META.get("REMOTE_ADDR", "unknown")
    return ip


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

            current = cache.get(cache_key, 0)
            if current >= limit:
                return JsonResponse(
                    {
                        "error_code": "rate_limited",
                        "error": error_message or f"Too many requests. Try again later.",
                        "retry_after": window_seconds,
                    },
                    status=429,
                )

            cache.set(cache_key, current + 1, window_seconds)
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