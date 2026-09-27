from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from account.models import CustomUser


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = (
        "username",
        "email",
        "display_name",
        "is_verified",
        "level",
        "experience",
        "created_at",
    )
    list_filter = ("is_verified", "is_staff", "is_active")
    search_fields = ("username", "email", "display_name")
    fieldsets = UserAdmin.fieldsets + (
        ("Profile", {"fields": ("display_name", "biography", "profile_picture", "is_verified")}),
        ("Gamification", {"fields": ("level", "experience")}),
        ("Credits", {"fields": ("credit_balance", "referred_by")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )
    readonly_fields = ("created_at", "updated_at", "last_login", "date_joined")
