"""Health check endpoints for Promptya.

Provides /health/ for basic liveness and /health/db/ for database readiness.
These are designed for container orchestration (Docker, Kubernetes, etc.)
and load balancer health checks.
"""

from django.db import connection
from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator


@method_decorator(csrf_exempt, name="dispatch")
class HealthCheckView(View):
    """Basic liveness check - returns 200 if the application is running."""

    def get(self, request):
        return JsonResponse({"status": "ok"})


@method_decorator(csrf_exempt, name="dispatch")
class DatabaseHealthCheckView(View):
    """Readiness check - returns 200 if database is reachable."""

    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            return JsonResponse({"status": "ok", "database": "connected"})
        except Exception as exc:
            return JsonResponse(
                {"status": "error", "database": "disconnected", "error": str(exc)},
                status=503,
            )


@method_decorator(csrf_exempt, name="dispatch")
class DetailedHealthCheckView(View):
    """Detailed health check with dependency status (for monitoring dashboards)."""

    def get(self, request):
        checks = {
            "application": "ok",
            "database": "unknown",
            "cache": "unknown",
        }
        status_code = 200

        # Database check
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            checks["database"] = "ok"
        except Exception as exc:
            checks["database"] = f"error: {exc}"
            status_code = 503

        # Cache check (only if Redis is configured)
        from django.conf import settings
        from django.core.cache import cache

        try:
            cache.set("health_check", "ok", 10)
            if cache.get("health_check") == "ok":
                checks["cache"] = "ok"
            else:
                checks["cache"] = "error: cache miss"
                status_code = 503
        except Exception as exc:
            checks["cache"] = f"error: {exc}"
            # Cache failure is not necessarily a hard failure
            if status_code == 200:
                status_code = 200

        return JsonResponse(checks, status=status_code)