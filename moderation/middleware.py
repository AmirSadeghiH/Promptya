"""Enforce account-level moderation state on state-changing API calls.

A user whose account is ``restricted``, temporarily ``suspended`` or ``banned``
must not be able to publish, comment, like, generate or otherwise mutate data.
The check runs once per request, before the view, so a new endpoint cannot forget
it.  Reads stay open (a restricted user can still browse), and the few endpoints
needed to manage your own situation — log out, file a report, manage your block
list — stay open as well, so a restriction is never an inescapable trap.

Never ``is_active``: that is Django's login gate and is left to authentication.
This middleware only speaks to accounts that are logged in.
"""

from django.http import JsonResponse

API_PREFIX = "/api/"

#: Non-mutating methods are always allowed through.
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

#: Paths a restricted/suspended (but not banned) user may still POST/DELETE to.
_ALLOWED_WHEN_RESTRICTED = (
    "/api/auth/logout/",
    "/api/auth/me/",
    "/api/reports/",
    "/api/blocks",
)

#: A banned user gets only the escape hatch.
_ALLOWED_WHEN_BANNED = ("/api/auth/logout/",)


class ModerationRestrictionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)

        if (
            user is not None
            and user.is_authenticated
            and request.method not in _SAFE_METHODS
            and request.path.startswith(API_PREFIX)
            and getattr(user, "has_active_restriction", False)
            and not self._allowed(request.path, user)
        ):
            return JsonResponse(
                {
                    "error_code": "moderation_restricted",
                    "error": "Your account is restricted from performing this action.",
                },
                status=403,
            )

        return self.get_response(request)

    @staticmethod
    def _allowed(path, user):
        if getattr(user, "is_banned", False):
            return any(path.startswith(prefix) for prefix in _ALLOWED_WHEN_BANNED)
        return any(path.startswith(prefix) for prefix in _ALLOWED_WHEN_RESTRICTED)
