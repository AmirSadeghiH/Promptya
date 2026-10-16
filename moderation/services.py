"""Business logic for reports and blocks.

Views, the admin and the anti-spam layer all go through these functions so the
rules (one target, no self-reports, de-duplication, symmetric blocking) exist in
exactly one place and are testable without HTTP.
"""

from django.core.exceptions import ValidationError
from django.db.models import Q

from moderation.models import Block, Report


class AlreadyReported(Exception):
    """Raised when the same user already has an open report for the target."""


# ---------------------------------------------------------------------------
# Blocks
# ---------------------------------------------------------------------------


def block_user(blocker, target):
    """Create a block. Idempotent; refuses a self-block."""
    if blocker.pk == target.pk:
        raise ValidationError("You cannot block yourself.")
    block, _ = Block.objects.get_or_create(blocker=blocker, blocked=target)
    return block


def unblock_user(blocker, target):
    """Remove the viewer's own block. Returns the number of rows deleted."""
    return Block.objects.filter(blocker=blocker, blocked=target).delete()


def viewer_has_blocked(viewer, target):
    """True when *viewer* has blocked *target* (one direction only)."""
    if not _both_authenticated(viewer, target) or viewer.pk == target.pk:
        return False
    return Block.objects.filter(blocker=viewer, blocked=target).exists()


def is_blocked_between(first, second):
    """True when either user has blocked the other."""
    if not _both_authenticated(first, second) or first.pk == second.pk:
        return False
    return Block.objects.filter(
        Q(blocker=first, blocked=second) | Q(blocker=second, blocked=first)
    ).exists()


def blocked_user_ids(viewer):
    """Ids whose content *viewer* must not see, in either direction.

    Cached on the viewer for the request so serializing a whole feed performs a
    single query instead of one per post.
    """
    if not getattr(viewer, "is_authenticated", False):
        return set()
    cached = getattr(viewer, "_promptya_blocked_ids", None)
    if cached is None:
        initiated = Block.objects.filter(blocker=viewer).values_list(
            "blocked_id", flat=True
        )
        received = Block.objects.filter(blocked=viewer).values_list(
            "blocker_id", flat=True
        )
        cached = set(initiated) | set(received)
        cached.discard(viewer.pk)
        viewer._promptya_blocked_ids = cached
    return cached


def _both_authenticated(first, second):
    return bool(
        first is not None
        and second is not None
        and getattr(first, "is_authenticated", False)
        and getattr(second, "is_authenticated", False)
    )


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


def _resolve_target(*, target_post=None, target_comment=None, target_user=None):
    provided = [t for t in (target_post, target_comment, target_user) if t is not None]
    if len(provided) != 1:
        raise ValidationError("A report must reference exactly one target.")
    return target_post, target_comment, target_user


def _snapshot(target_post, target_comment, target_user):
    if target_post is not None:
        body = (target_post.prompt or target_post.description or "").strip()
        return f"Post #{target_post.pk}: {target_post.title}\n{body[:2000]}".strip()
    if target_comment is not None:
        return f"Comment #{target_comment.pk}: {target_comment.content[:2000]}"
    if target_user is not None:
        return f"User @{target_user.username} (id {target_user.pk})"
    return ""


def create_report(
    *,
    reporter,
    reason,
    details="",
    target_post=None,
    target_comment=None,
    target_user=None,
):
    """Record a report. Raises ``ValidationError`` or ``AlreadyReported``.

    The caller must pass exactly one target.  A user may not report their own
    content, and may not file a second open report for the same target (a
    dismissed report does not block a new one).
    """
    if reason not in Report.Reason.values:
        raise ValidationError("Invalid report reason.")

    target_post, target_comment, target_user = _resolve_target(
        target_post=target_post,
        target_comment=target_comment,
        target_user=target_user,
    )

    owner = (
        target_post.author
        if target_post is not None
        else target_comment.user
        if target_comment is not None
        else target_user
    )
    if owner is not None and owner.pk == reporter.pk:
        raise ValidationError("You cannot report your own content.")

    lookup = {}
    if target_post is not None:
        lookup["target_post"] = target_post
    elif target_comment is not None:
        lookup["target_comment"] = target_comment
    elif target_user is not None:
        lookup["target_user"] = target_user

    if Report.objects.filter(
        reporter=reporter, status__in=Report.OPEN_STATUSES, **lookup
    ).exists():
        raise AlreadyReported()

    return Report.objects.create(
        reporter=reporter,
        reason=reason,
        details=(details or "").strip()[:4000],
        target_post=target_post,
        target_comment=target_comment,
        target_user=target_user,
        content_snapshot=_snapshot(target_post, target_comment, target_user),
    )


def resolve_report(report, *, status, actor=None, note=""):
    """Move a report to a terminal (or reviewing) status and stamp the actor."""
    if status not in Report.Status.values:
        raise ValidationError("Invalid report status.")
    report.status = status
    report.resolved_by = actor
    report.resolution_note = (note or "")[:4000]
    report.save(update_fields=["status", "resolved_by", "resolution_note", "updated_at"])
    return report


def report_target(report):
    """The content object a report points at, or ``None`` if it was deleted."""
    if report.target_post_id:
        return report.target_post
    if report.target_comment_id:
        return report.target_comment
    return report.target_user
