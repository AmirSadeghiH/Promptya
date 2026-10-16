"""Moderation domain: user reports and user-to-user blocks.

These models only hold the *intent* (who reported what, who blocked whom).
Every consequence — hiding content, restricting an account — is performed by a
moderator through the admin, on models that already exist (``Post.is_hidden``,
``Comment.is_hidden``, ``CustomUser.is_active``/``moderation_status``).  This
keeps the enforcement in one place instead of scattering "is this allowed?"
checks across the codebase, and it keeps a report from silently acting as a
punishment.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Report(models.Model):
    """A single piece of user-generated content (or account) reported by a user.

    A report targets exactly one of a post, a comment or a user account.  The
    target is stored as a nullable FK per kind rather than a generic relation so
    that a moderator can filter and join the queue against real tables, and so
    the field can be validated at the database boundary when the target is
    deleted (``SET_NULL`` leaves the report — and its snapshot — intact).
    """

    class Reason(models.TextChoices):
        SPAM = "spam", "Spam or misleading"
        HARASSMENT = "harassment", "Harassment or bullying"
        HATE = "hate", "Hate speech"
        NUDITY = "nudity", "Nudity or sexual content"
        VIOLENCE = "violence", "Violence or dangerous content"
        MISINFORMATION = "misinformation", "Misinformation"
        COPYRIGHT = "copyright", "Copyright violation"
        OTHER = "other", "Something else"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        REVIEWING = "reviewing", "Reviewing"
        ACTIONED = "actioned", "Actioned"
        DISMISSED = "dismissed", "Dismissed"

    #: Statuses that count as "an open report" for de-duplication.
    OPEN_STATUSES = (Status.PENDING, Status.REVIEWING)

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="reports_made",
        help_text="User who filed the report. Null if the account was deleted.",
    )

    reason = models.CharField(max_length=20, choices=Reason.choices)

    details = models.TextField(
        blank=True,
        default="",
        help_text="Optional free-text detail supplied by the reporter.",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    target_post = models.ForeignKey(
        "posts.Post",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="reports",
    )

    target_comment = models.ForeignKey(
        "interactions.Comment",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="reports",
    )

    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="reports_received",
    )

    # The offending text, captured at report time. A moderator keeps the
    # evidence even if the author later edits or deletes the content.
    content_snapshot = models.TextField(blank=True, default="")

    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="reports_resolved",
    )

    resolution_note = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["target_post"]),
            models.Index(fields=["target_comment"]),
            models.Index(fields=["target_user"]),
        ]

    def __str__(self):
        return f"Report #{self.pk} ({self.reason})"

    def clean(self):
        targets = [self.target_post, self.target_comment, self.target_user]
        if sum(target is not None for target in targets) != 1:
            raise ValidationError(
                "A report must reference exactly one of a post, a comment or a user."
            )

    @property
    def target_kind(self):
        if self.target_post_id:
            return "post"
        if self.target_comment_id:
            return "comment"
        if self.target_user_id:
            return "user"
        return "unknown"

    @property
    def target_owner(self):
        if self.target_post_id:
            return self.target_post.author
        if self.target_comment_id:
            return self.target_comment.user
        return self.target_user

    @property
    def target_label(self):
        """A short human label for the admin list and the audit metadata."""
        if self.target_post_id:
            return f"post:{self.target_post_id}"
        if self.target_comment_id:
            return f"comment:{self.target_comment_id}"
        if self.target_user_id:
            return f"user:{self.target_user_id}"
        return "unknown"


class Block(models.Model):
    """One user blocking another.

    A block is directional (``blocker`` blocked ``blocked``) but is enforced
    symmetrically: neither user sees the other's posts or comments, and neither
    can comment on or follow the other.  The direction is kept so an unblock
    removes only the block the viewer created.
    """

    blocker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="blocks_initiated",
    )

    blocked = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="blocks_received",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["blocker", "blocked"],
                name="unique_user_block",
            ),
        ]
        indexes = [
            models.Index(fields=["blocker", "-created_at"]),
            models.Index(fields=["blocked", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.blocker} blocked {self.blocked}"

    def clean(self):
        if self.blocker_id and self.blocker_id == self.blocked_id:
            raise ValidationError("Users cannot block themselves.")
