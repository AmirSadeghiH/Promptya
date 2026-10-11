from django.contrib import admin, messages

from core.models import AuditLog, log_admin_action
from interactions.models import Comment, Follow, Like, PostCopy, PostView, Save


@admin.register(PostView)
class PostViewAdmin(admin.ModelAdmin):
    list_display = ("post", "user", "created_at")
    list_select_related = ("post", "user")
    ordering = ("-created_at",)


@admin.register(PostCopy)
class PostCopyAdmin(admin.ModelAdmin):
    list_display = ("post", "user", "created_at")
    list_select_related = ("post", "user")
    ordering = ("-created_at",)


@admin.register(Like)
class LikeAdmin(admin.ModelAdmin):
    list_display = ("user", "post", "created_at")
    list_select_related = ("user", "post")
    search_fields = ("user__username", "post__title")
    ordering = ("-created_at",)


@admin.register(Save)
class SaveAdmin(admin.ModelAdmin):
    list_display = ("user", "post", "created_at")
    list_select_related = ("user", "post")
    search_fields = ("user__username", "post__title")
    ordering = ("-created_at",)


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("user", "post", "short_content", "is_hidden", "created_at")
    list_filter = ("is_hidden", "created_at")
    list_editable = ("is_hidden",)
    search_fields = ("user__username", "post__title", "content")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "updated_at")
    actions = ("hide_comments", "unhide_comments")

    def _check_perm(self, request, perm):
        if not request.user.has_perm(f"core.{perm}"):
            self.message_user(request, f"Permission denied: {perm}", messages.ERROR)
            return False
        return True

    @admin.display(description="Content")
    def short_content(self, obj):
        return obj.content[:60]

    @admin.action(description="Hide selected comments (moderation)")
    def hide_comments(self, request, queryset):
        if not self._check_perm(request, "can_hide_comments"):
            return
        for comment in queryset:
            comment.is_hidden = True
            comment.save(update_fields=["is_hidden"])
            log_admin_action(request, AuditLog.Action.COMMENT_HIDE, target_comment=comment)
        self.message_user(request, f"Hidden {queryset.count()} comment(s).", messages.SUCCESS)

    @admin.action(description="Unhide selected comments")
    def unhide_comments(self, request, queryset):
        if not self._check_perm(request, "can_unhide_comments"):
            return
        for comment in queryset:
            comment.is_hidden = False
            comment.save(update_fields=["is_hidden"])
            log_admin_action(request, AuditLog.Action.COMMENT_UNHIDE, target_comment=comment)
        self.message_user(request, f"Unhidden {queryset.count()} comment(s).", messages.SUCCESS)


@admin.register(Follow)
class FollowAdmin(admin.ModelAdmin):
    list_display = ("follower", "following", "created_at")
    list_select_related = ("follower", "following")
    search_fields = ("follower__username", "following__username")
    ordering = ("-created_at",)
