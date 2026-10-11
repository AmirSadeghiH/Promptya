from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.db.models import Count

from account.models import CustomUser, EmailVerificationToken
from core.models import AuditLog, log_admin_action
from credits.services import adjust


@admin.register(EmailVerificationToken)
class EmailVerificationTokenAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at", "expires_at", "used_at", "is_valid")
    list_filter = ("created_at", "expires_at", "used_at")
    search_fields = ("user__username", "user__email", "token")
    readonly_fields = ("user", "token", "created_at", "expires_at", "used_at")
    date_hierarchy = "created_at"

    def is_valid(self, obj):
        return obj.is_valid()

    is_valid.boolean = True
    is_valid.short_description = "Valid"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = (
        "username",
        "email",
        "display_name",
        "is_verified",
        "is_active",
        "is_staff",
        "credit_balance",
        "level",
        "experience",
        "created_at",
    )
    list_filter = ("is_verified", "is_staff", "is_active", "is_superuser")
    search_fields = ("username", "email", "display_name")
    list_editable = ("is_verified", "is_active", "is_staff")
    fieldsets = UserAdmin.fieldsets + (
        ("Profile", {"fields": ("display_name", "biography", "profile_picture", "is_verified")}),
        ("Gamification", {"fields": ("level", "experience")}),
        ("Credits", {"fields": ("credit_balance", "referred_by")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )
    readonly_fields = ("created_at", "updated_at", "last_login", "date_joined", "credit_balance", "referred_by")
    actions = ("activate_users", "deactivate_users", "verify_emails", "unverify_emails", "grant_credits", "revoke_credits")

    def _check_perm(self, request, perm):
        if not request.user.has_perm(f"core.{perm}"):
            self.message_user(request, f"Permission denied: {perm}", messages.ERROR)
            return False
        return True

    @admin.action(description="Activate selected users")
    def activate_users(self, request, queryset):
        if not self._check_perm(request, "can_activate_users"):
            return
        queryset = queryset.exclude(pk=request.user.pk)
        for user in queryset:
            user.is_active = True
            user.save(update_fields=["is_active"])
            log_admin_action(request, AuditLog.Action.USER_ACTIVATE, target_user=user)
        self.message_user(request, f"Activated {queryset.count()} user(s).", messages.SUCCESS)

    @admin.action(description="Deactivate selected users")
    def deactivate_users(self, request, queryset):
        if not self._check_perm(request, "can_deactivate_users"):
            return
        queryset = queryset.exclude(pk=request.user.pk)
        for user in queryset:
            user.is_active = False
            user.save(update_fields=["is_active"])
            log_admin_action(request, AuditLog.Action.USER_DEACTIVATE, target_user=user)
        self.message_user(request, f"Deactivated {queryset.count()} user(s).", messages.SUCCESS)

    @admin.action(description="Verify email for selected users")
    def verify_emails(self, request, queryset):
        if not self._check_perm(request, "can_verify_user_emails"):
            return
        for user in queryset:
            user.is_verified = True
            user.save(update_fields=["is_verified"])
            log_admin_action(request, AuditLog.Action.USER_VERIFY_EMAIL, target_user=user)
        self.message_user(request, f"Verified email for {queryset.count()} user(s).", messages.SUCCESS)

    @admin.action(description="Unverify email for selected users")
    def unverify_emails(self, request, queryset):
        if not self._check_perm(request, "can_unverify_user_emails"):
            return
        for user in queryset:
            user.is_verified = False
            user.save(update_fields=["is_verified"])
            log_admin_action(request, AuditLog.Action.USER_UNVERIFY_EMAIL, target_user=user)
        self.message_user(request, f"Unverified email for {queryset.count()} user(s).", messages.SUCCESS)

    @admin.action(description="Grant 100 credits to selected users")
    def grant_credits(self, request, queryset):
        if not self._check_perm(request, "can_grant_user_credits"):
            return
        users = list(queryset)
        for user in users:
            adjust(user, 100, note=f"Admin grant by {request.user}")
            log_admin_action(request, AuditLog.Action.USER_GRANT_CREDITS, target_user=user, metadata={"amount": 100})
        self.message_user(request, f"Granted 100 credits to {len(users)} user(s).", messages.SUCCESS)

    @admin.action(description="Revoke 100 credits from selected users (clamped to balance)")
    def revoke_credits(self, request, queryset):
        if not self._check_perm(request, "can_revoke_user_credits"):
            return
        users = list(queryset)
        for user in users:
            adjust(user, -100, note=f"Admin revoke by {request.user}")
            log_admin_action(request, AuditLog.Action.USER_REVOKE_CREDITS, target_user=user, metadata={"amount": -100})
        self.message_user(request, f"Revoked up to 100 credits from {len(users)} user(s).", messages.SUCCESS)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(post_count=Count("posts"))
