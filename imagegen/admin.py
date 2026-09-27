from django.contrib import admin

from imagegen.models import AIConfig, GeneratedImage


@admin.register(AIConfig)
class AIConfigAdmin(admin.ModelAdmin):
    """The provider settings screen — the only place a key is entered."""

    list_display = ("model", "base_url", "credit_cost", "is_enabled", "has_api_key", "updated_at")
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
                "fields": ("image_size", "timeout_seconds", "credit_cost", "is_enabled"),
                "description": "credits charged per image; raise it for a pricier model.",
            },
        ),
        ("Timestamps", {"fields": ("updated_at",)}),
    )

    @admin.display(boolean=True, description="API key set")
    def has_api_key(self, obj):
        return bool(obj.api_key)

    def has_add_permission(self, request):
        # A second row would silently shadow the first — keep it a singleton.
        if AIConfig.objects.exists():
            return False
        return super().has_add_permission(request)


@admin.register(GeneratedImage)
class GeneratedImageAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "status", "provider_model", "credit_cost", "created_at")
    list_filter = ("status", "provider_model", "created_at")
    search_fields = ("prompt", "user__username", "error")
    autocomplete_fields = ("user", "source_post")
    date_hierarchy = "created_at"
    readonly_fields = ("created_at", "finished_at")
