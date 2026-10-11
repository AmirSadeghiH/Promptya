from django.contrib import admin

from core.models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor", "action", "target_user", "target_post", "target_comment")
    list_filter = ("action", "created_at")
    search_fields = ("actor__username", "target_user__username", "metadata")
    readonly_fields = ("actor", "action", "target_user", "target_post", "target_comment",
                       "target_challenge", "target_completion", "metadata", "ip_address",
                       "user_agent", "created_at")
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False