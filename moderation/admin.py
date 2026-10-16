"""Admin surface for the moderation queue.

Every action is permission-gated (``core.can_review_reports`` /
``core.can_action_reports``) and audited through ``core.models.log_admin_action``.
Animating a report into a punishment is always a deliberate staff action here;
nothing in the product auto-hides content or disables an account from a report.
"""

from django.contrib import admin, messages
from django.utils import timezone

from core.models import AuditLog, log_admin_action
from moderation.models import Block, Report
from moderation.services import resolve_report


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "created_at",
        "reason",
        "status",
        "target_kind",
        "target_owner",
        "reporter",
        "resolved_by",
    )
    list_filter = ("status", "reason", "created_at")
    search_fields = (
        "reporter__username",
        "target_user__username",
        "target_post__title",
        "details",
    )
    date_hierarchy = "created_at"
    readonly_fields = (
        "reporter",
        "reason",
        "details",
        "target_post",
        "target_comment",
        "target_user",
        "content_snapshot",
        "resolved_by",
        "resolution_note",
        "created_at",
        "updated_at",
    )
    actions = (
        "mark_reviewing",
        "action_hide_content",
        "action_deactivate_user",
        "dismiss_reports",
    )

    def _check_perm(self, request, perm):
        if not request.user.has_perm(f"core.{perm}"):
            self.message_user(request, f"Permission denied: {perm}", messages.ERROR)
            return False
        return True

    def has_add_permission(self, request):
        # Reports are filed by users, never invented in the admin.
        return False

    @admin.display(description="Target")
    def target_owner(self, obj):
        owner = obj.target_owner
        return owner.username if owner is not None else "—"

    @admin.action(description="Mark selected reports as reviewing")
    def mark_reviewing(self, request, queryset):
        if not self._check_perm(request, "can_review_reports"):
            return
        updated = queryset.exclude(status=Report.Status.REVIEWING).update(
            status=Report.Status.REVIEWING, updated_at=timezone.now()
        )
        self.message_user(request, f"{updated} report(s) marked reviewing.", messages.SUCCESS)

    @admin.action(description="Action: hide the reported content")
    def action_hide_content(self, request, queryset):
        if not self._check_perm(request, "can_action_reports"):
            return
        handled = 0
        for report in queryset.select_related("target_post", "target_comment"):
            if report.target_post_id and not report.target_post.is_hidden:
                report.target_post.is_hidden = True
                report.target_post.save(update_fields=["is_hidden"])
                log_admin_action(
                    request,
                    AuditLog.Action.POST_HIDE,
                    target_post=report.target_post,
                    metadata={"report_id": report.pk},
                )
            elif report.target_comment_id and not report.target_comment.is_hidden:
                report.target_comment.is_hidden = True
                report.target_comment.save(update_fields=["is_hidden"])
                log_admin_action(
                    request,
                    AuditLog.Action.COMMENT_HIDE,
                    target_comment=report.target_comment,
                    metadata={"report_id": report.pk},
                )
            else:
                # A user-target report cannot be "hidden"; skip it so the
                # moderator chooses the account action explicitly.
                continue
            resolve_report(report, status=Report.Status.ACTIONED, actor=request.user)
            log_admin_action(
                request,
                AuditLog.Action.REPORT_RESOLVE,
                target_user=report.target_owner,
                metadata={"report_id": report.pk, "decision": "hide"},
            )
            handled += 1
        self.message_user(request, f"Actioned {handled} report(s).", messages.SUCCESS)

    @admin.action(description="Action: deactivate the reported account")
    def action_deactivate_user(self, request, queryset):
        if not self._check_perm(request, "can_moderate_users"):
            return
        handled = 0
        for report in queryset.select_related("target_post", "target_comment", "target_user"):
            owner = report.target_owner
            if owner is None or owner.pk == request.user.pk:
                continue
            owner.is_active = False
            owner.save(update_fields=["is_active"])
            log_admin_action(
                request, AuditLog.Action.USER_DEACTIVATE, target_user=owner,
                metadata={"report_id": report.pk},
            )
            resolve_report(report, status=Report.Status.ACTIONED, actor=request.user)
            log_admin_action(
                request,
                AuditLog.Action.REPORT_RESOLVE,
                target_user=owner,
                metadata={"report_id": report.pk, "decision": "deactivate"},
            )
            handled += 1
        self.message_user(request, f"Deactivated account for {handled} report(s).", messages.SUCCESS)

    @admin.action(description="Dismiss selected reports")
    def dismiss_reports(self, request, queryset):
        if not self._check_perm(request, "can_action_reports"):
            return
        for report in queryset:
            resolve_report(report, status=Report.Status.DISMISSED, actor=request.user)
            log_admin_action(
                request,
                AuditLog.Action.REPORT_DISMISS,
                target_user=report.target_owner,
                metadata={"report_id": report.pk},
            )
        self.message_user(request, f"Dismissed {queryset.count()} report(s).", messages.SUCCESS)


@admin.register(Block)
class BlockAdmin(admin.ModelAdmin):
    list_display = ("id", "blocker", "blocked", "created_at")
    list_filter = ("created_at",)
    search_fields = ("blocker__username", "blocked__username")
    date_hierarchy = "created_at"
    readonly_fields = ("blocker", "blocked", "created_at")

    def has_add_permission(self, request):
        return False
