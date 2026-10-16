"""Core models for cross-cutting concerns like audit logging."""

from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """Immutable log of sensitive administrative actions.

    Every operation that could affect user data, credits, moderation state,
    or system configuration should create an entry here.
    """

    class Action(models.TextChoices):
        # User management
        USER_ACTIVATE = "user_activate", "User activated"
        USER_DEACTIVATE = "user_deactivate", "User deactivated"
        USER_VERIFY_EMAIL = "user_verify_email", "User email verified"
        USER_UNVERIFY_EMAIL = "user_unverify_email", "User email unverified"
        USER_GRANT_CREDITS = "user_grant_credits", "Credits granted to user"
        USER_REVOKE_CREDITS = "user_revoke_credits", "Credits revoked from user"
        USER_CHANGE_STAFF = "user_change_staff", "User staff status changed"
        USER_CHANGE_SUPERUSER = "user_change_superuser", "User superuser status changed"

        # Post moderation
        POST_HIDE = "post_hide", "Post hidden"
        POST_UNHIDE = "post_unhide", "Post unhidden"
        POST_SOFT_DELETE = "post_soft_delete", "Post soft deleted"

        # Comment moderation
        COMMENT_HIDE = "comment_hide", "Comment hidden"
        COMMENT_UNHIDE = "comment_unhide", "Comment unhidden"

        # Challenge management
        CHALLENGE_ACTIVATE = "challenge_activate", "Challenge activated"
        CHALLENGE_DEACTIVATE = "challenge_deactivate", "Challenge deactivated"
        CHALLENGE_RESET = "challenge_reset", "Challenge completions reset"
        COMPLETION_VERIFY = "completion_verify", "Completion verified"
        COMPLETION_REJECT = "completion_reject", "Completion rejected"

        # Credit operations
        CREDIT_ADJUSTMENT = "credit_adjustment", "Credit adjustment via admin"

        # Configuration
        AI_CONFIG_CHANGE = "ai_config_change", "AI config changed"

        # Moderation
        REPORT_RESOLVE = "report_resolve", "Report resolved with action"
        REPORT_DISMISS = "report_dismiss", "Report dismissed"
        USER_RESTRICT = "user_restrict", "User restricted"
        USER_SUSPEND = "user_suspend", "User suspended"
        USER_BAN = "user_ban", "User banned"
        USER_UNRESTRICT = "user_unrestrict", "User restriction lifted"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="audit_logs",
        help_text="Staff user who performed the action",
    )

    action = models.CharField(max_length=50, choices=Action.choices)

    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="audit_logs_target",
        help_text="User affected by the action (if applicable)",
    )

    target_post = models.ForeignKey(
        "posts.Post",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="audit_logs",
        help_text="Post affected by the action (if applicable)",
    )

    target_comment = models.ForeignKey(
        "interactions.Comment",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="audit_logs",
        help_text="Comment affected by the action (if applicable)",
    )

    target_challenge = models.ForeignKey(
        "credits.Challenge",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="audit_logs",
        help_text="Challenge affected by the action (if applicable)",
    )

    target_completion = models.ForeignKey(
        "credits.ChallengeCompletion",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="audit_logs",
        help_text="Challenge completion affected by the action (if applicable)",
    )

    target_report = models.ForeignKey(
        "moderation.Report",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="audit_logs",
        help_text="Report affected by the action (if applicable)",
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional context (e.g., credit amounts, reason, etc.)",
    )

    ip_address = models.GenericIPAddressField(
        blank=True,
        null=True,
        help_text="IP address of the actor",
    )

    user_agent = models.TextField(
        blank=True,
        default="",
        help_text="User agent of the actor",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["actor", "-created_at"]),
            models.Index(fields=["action", "-created_at"]),
            models.Index(fields=["target_user", "-created_at"]),
            models.Index(fields=["target_post", "-created_at"]),
        ]

    def __str__(self):
        actor = self.actor.username if self.actor else "system"
        target = ""
        if self.target_user:
            target = f" -> {self.target_user.username}"
        elif self.target_post:
            target = f" -> Post({self.target_post.pk})"
        elif self.target_comment:
            target = f" -> Comment({self.target_comment.pk})"
        elif self.target_report:
            target = f" -> Report({self.target_report.pk})"
        return f"{actor}: {self.action}{target}"


def log_admin_action(
    request,
    action,
    *,
    target_user=None,
    target_post=None,
    target_comment=None,
    target_challenge=None,
    target_completion=None,
    target_report=None,
    metadata=None,
):
    """Convenience function to create an audit log entry from an admin request."""
    from django.contrib.auth import get_user_model

    if target_user is not None and not isinstance(target_user, get_user_model()):
        target_user = None

    ip = None
    if request:
        from core.ratelimit import get_client_ip

        ip = get_client_ip(request)

    AuditLog.objects.create(
        actor=request.user if request and request.user.is_authenticated else None,
        action=action,
        target_user=target_user,
        target_post=target_post,
        target_comment=target_comment,
        target_challenge=target_challenge,
        target_completion=target_completion,
        target_report=target_report,
        metadata=metadata or {},
        ip_address=ip,
        user_agent=request.META.get("HTTP_USER_AGENT", "") if request else "",
    )
