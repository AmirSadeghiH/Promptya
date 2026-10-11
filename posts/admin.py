from django.contrib import admin, messages

from core.models import AuditLog, log_admin_action
from posts.models import Category, Post, Tag


class TagInline(admin.TabularInline):
    model = Post.tags.through
    extra = 0


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "post_type", "category", "is_hidden", "created_at")
    list_filter = ("post_type", "category", "is_hidden", "created_at")
    search_fields = ("title", "description", "prompt", "ai_model", "author__username")
    autocomplete_fields = ("author", "category")
    filter_horizontal = ("tags",)
    date_hierarchy = "created_at"
    readonly_fields = ("created_at", "updated_at", "slug")
    actions = ("hide_posts", "unhide_posts", "soft_delete_posts")

    def _check_perm(self, request, perm):
        if not request.user.has_perm(f"core.{perm}"):
            self.message_user(request, f"Permission denied: {perm}", messages.ERROR)
            return False
        return True

    @admin.action(description="Hide selected posts (moderation)")
    def hide_posts(self, request, queryset):
        if not self._check_perm(request, "can_hide_posts"):
            return
        for post in queryset:
            post.is_hidden = True
            post.save(update_fields=["is_hidden"])
            log_admin_action(request, AuditLog.Action.POST_HIDE, target_post=post)
        self.message_user(request, f"Hidden {queryset.count()} post(s).", messages.SUCCESS)

    @admin.action(description="Unhide selected posts")
    def unhide_posts(self, request, queryset):
        if not self._check_perm(request, "can_unhide_posts"):
            return
        for post in queryset:
            post.is_hidden = False
            post.save(update_fields=["is_hidden"])
            log_admin_action(request, AuditLog.Action.POST_UNHIDE, target_post=post)
        self.message_user(request, f"Unhidden {queryset.count()} post(s).", messages.SUCCESS)

    @admin.action(description="Soft delete selected posts (sets deleted flag)")
    def soft_delete_posts(self, request, queryset):
        if not self._check_perm(request, "can_soft_delete_posts"):
            return
        for post in queryset:
            post.is_hidden = True
            post.save(update_fields=["is_hidden"])
            log_admin_action(request, AuditLog.Action.POST_SOFT_DELETE, target_post=post)
        self.message_user(request, f"Soft-deleted {queryset.count()} post(s).", messages.SUCCESS)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "post_count", "created_at")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}

    @admin.display(description="Posts")
    def post_count(self, obj):
        return obj.posts.count()


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
