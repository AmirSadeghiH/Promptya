from django.contrib import admin, messages

from core.models import AuditLog, log_admin_action
from credits.models import Challenge, ChallengeCompletion, CreditTransaction, ChallengeType
from credits.services import adjust


@admin.register(Challenge)
class ChallengeAdmin(admin.ModelAdmin):
    list_display = (
        "title", "slug", "verifier", "reward_credits", "type", "is_active",
        "starts_at", "ends_at", "max_rewards_per_user", "max_total_rewards",
        "completion_count", "global_rewards_claimed_display"
    )
    list_filter = ("is_active", "verifier", "type")
    search_fields = ("title", "slug", "sponsor")
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ("global_rewards_claimed_display",)
    fieldsets = (
        (None, {"fields": ("slug", "title", "description", "verifier", "reward_credits")}),
        ("Type & Schedule", {"fields": ("type", "is_active", "starts_at", "ends_at")}),
        ("Limits", {"fields": ("max_rewards_per_user", "max_total_rewards", "global_rewards_claimed_display")}),
        ("Sponsor", {"fields": ("sponsor",)}),
    )
    actions = ("activate_challenges", "deactivate_challenges", "reset_completions")

    def _check_perm(self, request, perm):
        if not request.user.has_perm(f"core.{perm}"):
            self.message_user(request, f"Permission denied: {perm}", messages.ERROR)
            return False
        return True

    @admin.display(description="Completions")
    def completion_count(self, obj):
        return obj.completions.count()

    @admin.display(description="Global Claimed")
    def global_rewards_claimed_display(self, obj):
        return obj.global_rewards_claimed()

    @admin.action(description="Activate selected challenges")
    def activate_challenges(self, request, queryset):
        if not self._check_perm(request, "can_activate_challenges"):
            return
        for challenge in queryset:
            challenge.is_active = True
            challenge.save(update_fields=["is_active"])
            log_admin_action(request, AuditLog.Action.CHALLENGE_ACTIVATE, target_challenge=challenge)
        self.message_user(request, f"Activated {queryset.count()} challenge(s).", messages.SUCCESS)

    @admin.action(description="Deactivate selected challenges")
    def deactivate_challenges(self, request, queryset):
        if not self._check_perm(request, "can_deactivate_challenges"):
            return
        for challenge in queryset:
            challenge.is_active = False
            challenge.save(update_fields=["is_active"])
            log_admin_action(request, AuditLog.Action.CHALLENGE_DEACTIVATE, target_challenge=challenge)
        self.message_user(request, f"Deactivated {queryset.count()} challenge(s).", messages.SUCCESS)

    @admin.action(description="Reset all completions for selected challenges")
    def reset_completions(self, request, queryset):
        if not self._check_perm(request, "can_reset_challenges"):
            return
        from credits.models import CreditTransaction, TransactionKind
        count = 0
        for challenge in queryset:
            # Reject pending completions
            challenge.completions.filter(status="pending").update(status="rejected", detail="Reset by admin")
            # Revoke rewards for verified completions
            for completion in challenge.completions.filter(status="verified"):
                if completion.reward_transaction:
                    # Create a refund transaction
                    adjust(completion.user, -completion.reward_transaction.amount, note=f"Challenge reset: {challenge.title}")
                completion.status = "rejected"
                completion.detail = "Reset by admin"
                completion.reward_transaction = None
                completion.verified_at = None
                completion.save(update_fields=["status", "detail", "reward_transaction", "verified_at"])
                log_admin_action(request, AuditLog.Action.CHALLENGE_RESET, target_challenge=challenge, target_completion=completion)
                count += 1
        self.message_user(request, f"Reset {count} verified completion(s) and rejected pending completions.", messages.SUCCESS)


@admin.register(ChallengeCompletion)
class ChallengeCompletionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "challenge", "status", "created_at", "verified_at", "idempotency_key_short")
    list_filter = ("status", "challenge")
    search_fields = ("user__username", "evidence", "detail", "idempotency_key")
    autocomplete_fields = ("user",)
    readonly_fields = ("created_at", "verified_at", "reward_transaction", "idempotency_key")
    actions = ("verify_completions", "reject_completions")

    def _check_perm(self, request, perm):
        if not request.user.has_perm(f"core.{perm}"):
            self.message_user(request, f"Permission denied: {perm}", messages.ERROR)
            return False
        return True

    @admin.display(description="Idempotency Key")
    def idempotency_key_short(self, obj):
        if obj.idempotency_key:
            return f"{obj.idempotency_key[:16]}..."
        return "—"

    @admin.action(description="Verify selected pending completions")
    def verify_completions(self, request, queryset):
        if not self._check_perm(request, "can_verify_completions"):
            return
        from credits.challenges import complete_challenge, ChallengeError
        verified = 0
        for completion in queryset.filter(status="pending"):
            try:
                complete_challenge(completion.user, completion.challenge.slug, evidence=completion.evidence)
                log_admin_action(request, AuditLog.Action.COMPLETION_VERIFY, target_completion=completion)
                verified += 1
            except ChallengeError:
                pass
        self.message_user(request, f"Verified {verified} completion(s).", messages.SUCCESS)

    @admin.action(description="Reject selected completions")
    def reject_completions(self, request, queryset):
        if not self._check_perm(request, "can_reject_completions"):
            return
        for completion in queryset.exclude(status="rejected"):
            completion.status = "rejected"
            completion.detail = "Rejected by admin"
            completion.save(update_fields=["status", "detail"])
            log_admin_action(request, AuditLog.Action.COMPLETION_REJECT, target_completion=completion)
        self.message_user(request, f"Rejected {queryset.exclude(status='rejected').count()} completion(s).", messages.SUCCESS)


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

    def _check_perm(self, request, perm):
        if not request.user.has_perm(f"core.{perm}"):
            self.message_user(request, f"Permission denied: {perm}", messages.ERROR)
            return False
        return True

    def has_add_permission(self, request):
        # Movements belong to the service layer; use an action instead.
        return False

    def _apply_adjustment(self, request, queryset, sign):
        if not self._check_perm(request, "can_adjust_credits"):
            return
        users = {row.user_id: row.user for row in queryset}
        for user in users.values():
            adjust(user, sign * 50, note=f"Admin adjustment by {request.user}")
            log_admin_action(request, AuditLog.Action.CREDIT_ADJUSTMENT, target_user=user, metadata={"amount": sign * 50})
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
