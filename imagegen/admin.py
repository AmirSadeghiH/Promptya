from django.contrib import admin
from django.utils.html import format_html

from core.models import AuditLog, log_admin_action
from imagegen.models import AIConfig, AIModel, GeneratedImage


@admin.register(AIModel)
class AIModelAdmin(admin.ModelAdmin):
    """The list posters choose from on the create form."""

    list_display = ("name", "is_active", "position", "created_at")
    list_editable = ("is_active", "position")
    list_filter = ("is_active",)
    search_fields = ("name",)
    ordering = ("position", "name")


@admin.register(AIConfig)
class AIConfigAdmin(admin.ModelAdmin):
    """The provider settings screen — the only place a key is entered."""

    list_display = ("model", "base_url", "credit_cost", "premium_credit_cost", "is_enabled", "has_api_key", "updated_at")
    readonly_fields = ("updated_at",)
    fieldsets = (
        (
            "Provider",
            {
                "fields": ("base_url", "api_key", "model"),
                "description": (
                    "Any OpenAI-compatible image endpoint works. For gapgpt use "
                    "https://api.gapgpt.app/v1 with the gapgpt/z-image model."
                ),
            },
        ),
        (
            "Generation",
            {
                "fields": ("image_size", "timeout_seconds", "credit_cost", "premium_credit_cost", "prompt_use_reward", "is_enabled"),
                "description": (
                    "Credits charged per image; raise it for a pricier model. "
                    "Prompt-use reward: credits paid to a prompt's author each time "
                    "someone generates from it (0 = off; capped at the generation price)."
                ),
            },
        ),
        (
            "Watermark",
            {
                "fields": ("watermark_text", "watermark_opacity", "watermark_size_ratio"),
                "description": "Server-side watermark applied to standard (non-premium) generations.",
            },
        ),
        ("Timestamps", {"fields": ("updated_at",)}),
    )

    def _check_perm(self, request, perm):
        if not request.user.has_perm(f"core.{perm}"):
            self.message_user(request, f"Permission denied: {perm}", admin.messages.ERROR)
            return False
        return True

    @admin.display(boolean=True, description="API key set")
    def has_api_key(self, obj):
        return bool(obj.api_key)

    def has_add_permission(self, request):
        # A second row would silently shadow the first — keep it a singleton.
        if AIConfig.objects.exists():
            return False
        return super().has_add_permission(request)

    def save_model(self, request, obj, form, change):
        if not self._check_perm(request, "can_change_ai_config"):
            return
        super().save_model(request, obj, form, change)
        if change:
            log_admin_action(request, AuditLog.Action.AI_CONFIG_CHANGE, metadata={
                "model": obj.model,
                "base_url": obj.base_url,
                "credit_cost": obj.credit_cost,
                "premium_credit_cost": obj.premium_credit_cost,
                "is_enabled": obj.is_enabled,
                "has_api_key": bool(obj.api_key),
            })


@admin.register(GeneratedImage)
class GeneratedImageAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "status", "tier", "provider_model", "credit_cost", "creator_reward", "created_at", "image_preview")
    list_filter = ("status", "tier", "provider_model", "created_at")
    search_fields = ("prompt", "user__username", "error", "idempotency_key")
    autocomplete_fields = ("user", "source_post")
    date_hierarchy = "created_at"
    readonly_fields = ("created_at", "finished_at", "image_preview_large", "source_image_preview")
    list_select_related = ("user", "source_post")

    @admin.display(description="Image")
    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="max-height: 40px; max-width: 60px;" />', obj.image.url)
        return "—"

    @admin.display(description="Generated Image")
    def image_preview_large(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="max-height: 300px; max-width: 400px;" />', obj.image.url)
        return "No image generated"

    @admin.display(description="Source Image")
    def source_image_preview(self, obj):
        if obj.source_image:
            return format_html('<img src="{}" style="max-height: 300px; max-width: 400px;" />', obj.source_image.url)
        return "No source image"
