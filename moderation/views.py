"""JSON API for reporting content and blocking users."""

import json

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from core.ratelimit import rate_limit_user
from interactions.models import Comment
from posts.models import Post

# Call these under the `moderation` namespace so ids passed to this module are
# explicit and the call looks like ``moderation.services.create_report``.
from moderation import services
from moderation.models import Block, Report


def _parse_body(request):
    try:
        data = json.loads(request.body.decode("utf-8")) if request.body else {}
    except (ValueError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _method_not_allowed():
    return JsonResponse({"error": "Method not allowed."}, status=405)


def _resolve_target(target_type, target_id):
    """Return ``(target_post, target_comment, target_user)`` or raise ValueError."""
    if target_type == "post":
        post = Post.objects.visible().filter(pk=target_id).first()
        if post is None:
            raise ValueError("not_found")
        return post, None, None
    if target_type == "comment":
        comment = Comment.objects.select_related("user").filter(pk=target_id).first()
        if comment is None:
            raise ValueError("not_found")
        return None, comment, None
    if target_type == "user":
        user = get_user_model().objects.filter(pk=target_id).first()
        if user is None:
            raise ValueError("not_found")
        return None, None, user
    raise ValueError("invalid_target")


@login_required
@rate_limit_user(
    "create_report",
    limit=20,
    window_seconds=3600,
    error_message="Too many reports. Try again later.",
)
@require_http_methods(["POST"])
def create_report(request):
    data = _parse_body(request)
    if data is None:
        return JsonResponse({"error": "Invalid JSON body."}, status=400)

    target_type = str(data.get("target_type", "")).strip()
    reason = str(data.get("reason", "")).strip()
    details = str(data.get("details", "") or "")

    try:
        target_id = int(data.get("target_id"))
    except (TypeError, ValueError):
        return JsonResponse({"errors": {"target_id": "A target id is required."}}, status=400)

    if reason not in Report.Reason.values:
        return JsonResponse({"errors": {"reason": "Choose a valid reason."}}, status=400)

    try:
        target_post, target_comment, target_user = _resolve_target(target_type, target_id)
    except ValueError as exc:
        if str(exc) == "not_found":
            return JsonResponse({"error": "That content no longer exists."}, status=404)
        return JsonResponse(
            {"errors": {"target_type": "Unknown report target."}}, status=400
        )

    try:
        report = services.create_report(
            reporter=request.user,
            reason=reason,
            details=details,
            target_post=target_post,
            target_comment=target_comment,
            target_user=target_user,
        )
    except services.AlreadyReported:
        return JsonResponse(
            {
                "error_code": "already_reported",
                "error": "You have already reported this.",
            },
            status=400,
        )
    except ValidationError as exc:
        return JsonResponse({"error": "; ".join(exc.messages)}, status=400)

    return JsonResponse(
        {
            "report": {
                "id": report.pk,
                "status": report.status,
                "reason": report.reason,
                "target_kind": report.target_kind,
            }
        },
        status=201,
    )


@login_required
@rate_limit_user(
    "block_user",
    limit=60,
    window_seconds=3600,
    error_message="Too many block requests. Try again later.",
)
@require_http_methods(["POST", "DELETE"])
def block_toggle(request, username):
    target = get_object_or_404(
        get_user_model().objects.exclude(pk=request.user.pk),
        username=username,
    )

    if request.method == "DELETE":
        services.unblock_user(request.user, target)
        return JsonResponse({"blocked": False, "username": target.username})

    try:
        services.block_user(request.user, target)
    except ValidationError as exc:
        return JsonResponse({"error": "; ".join(exc.messages)}, status=400)
    return JsonResponse({"blocked": True, "username": target.username}, status=201)


@login_required
@require_http_methods(["GET"])
def list_blocks(request):
    blocks = (
        Block.objects.filter(blocker=request.user)
        .select_related("blocked")
        .order_by("-created_at")
    )
    return JsonResponse(
        {
            "results": [
                {
                    "username": block.blocked.username,
                    "display_name": block.blocked.display_label,
                    "created_at": block.created_at.isoformat(),
                }
                for block in blocks
            ]
        }
    )
