from django.contrib import admin, messages

from credits.models import Challenge, ChallengeCompletion, CreditTransaction
from credits.services import adjust


@admin.register(Challenge)
class ChallengeAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "verifier", "reward_credits", "is_active", "max_rewards_per_user")
    list_filter = ("is_active", "verifier")
    search_fields = ("title", "slug")
    prepopulated_fields = {"slug": ("title",)}


@admin.register(ChallengeCompletion)
class ChallengeCompletionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "challenge", "status", "created_at", "verified_at")
    list_filter = ("status", "challenge")
    search_fields = ("user__username", "evidence", "detail")
    autocomplete_fields = ("user",)
    readonly_fields = ("created_at", "verified_at", "reward_transaction")


@admin.register(CreditTransaction)
class CreditTransactionAdmin(admin.ModelAdmin):
    """Read-only ledger, plus a bulk adjustment so ops never edits a balance
    by hand (which would desync the ledger from the wallet)."""

    list_display = ("id", "user", "kind", "amount", "balance_after", "note", "created_at")
    list_filter = ("kind", "created_at")
    search_fields = ("user__username", "note")
    autocomplete_fields = ("user", "generation", "challenge")
    date_hierarchy = "created_at"
    readonly_fields = ("user", "kind", "amount", "balance_after", "generation", "challenge", "note", "created_at")
    actions = ("add_credits", "remove_credits")

    def has_add_permission(self, request):
        # Movements belong to the service layer; use an action instead.
        return False

    def _apply_adjustment(self, request, queryset, sign):
        users = {row.user_id: row.user for row in queryset}
        for user in users.values():
            adjust(user, sign * 50, note=f"Admin adjustment by {request.user}")
        self.message_user(
            request,
            f"{'Added' if sign > 0 else 'Removed'} 50 credits for {len(users)} account(s).",
            messages.SUCCESS,
        )

    @admin.action(description="Add 50 credits")
    def add_credits(self, request, queryset):
        self._apply_adjustment(request, queryset, 1)

    @admin.action(description="Remove 50 credits")
    def remove_credits(self, request, queryset):
        self._apply_adjustment(request, queryset, -1)
