"""Credit wallet, ledger and reward challenges.

The balance itself lives on ``account.CustomUser`` (one number, read on every
studio page), while every movement is recorded here as an immutable ledger
row.  A balance you cannot explain is a balance you cannot debug — so the
ledger is the source of truth for *why* a number changed, and the user row is
only the fast path for *what* the number currently is.
"""

from django.conf import settings
from django.db import models


# What a movement means. Every charge/reward/refund/adjustment is one of these.
class TransactionKind(models.TextChoices):
    GENERATION = "generation", "Generation charge"
    REWARD = "reward", "Reward"
    REFUND = "refund", "Refund"
    ADJUSTMENT = "adjustment", "Admin adjustment"


class ChallengeType(models.TextChoices):
    """Whether this is a permanent mission or a time-bounded challenge."""
    MISSION = "mission", "Mission (permanent)"
    CHALLENGE = "challenge", "Challenge (time-bounded)"


class CreditTransaction(models.Model):
    """One immutable line in a user's credit ledger.

    ``amount`` is signed: positive credits the wallet, negative debits it.
    ``balance_after`` snapshots the balance so the history reads top-to-bottom
    without recomputing.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="credit_transactions",
    )

    kind = models.CharField(
        max_length=20,
        choices=TransactionKind.choices,
    )

    amount = models.IntegerField(
        help_text="Signed: positive credits in, negative credits out.",
    )

    balance_after = models.PositiveIntegerField()

    generation = models.ForeignKey(
        "imagegen.GeneratedImage",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="credit_transactions",
        help_text="The generation this movement belongs to, when there is one.",
    )

    challenge = models.ForeignKey(
        "credits.Challenge",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="transactions",
    )

    note = models.CharField(
        max_length=200,
        blank=True,
        default="",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
        ]

    def __str__(self):
        sign = "+" if self.amount >= 0 else ""
        return f"{self.user} {sign}{self.amount} ({self.kind})"


class Challenge(models.Model):
    """A way to earn credits.

    ``verifier`` names a function in ``credits.challenges.VERIFIERS``.  The
    model stays dumb on purpose: adding a challenge means adding a row and a
    verifier, never editing this class or the reward path.
    """

    class Meta:
        ordering = ["reward_credits", "slug"]
        indexes = [
            models.Index(fields=["is_active", "starts_at", "ends_at"]),
        ]

    slug = models.SlugField(max_length=60, unique=True)

    title = models.CharField(max_length=120)

    description = models.TextField(blank=True, default="")

    verifier = models.CharField(
        max_length=60,
        help_text="Key into credits.challenges.VERIFIERS.",
    )

    reward_credits = models.PositiveIntegerField(default=0)

    # Type: mission (permanent) or challenge (time-bounded)
    type = models.CharField(
        max_length=10,
        choices=ChallengeType.choices,
        default=ChallengeType.CHALLENGE,
    )

    # Time window for challenges (ignored for missions)
    starts_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="When this challenge becomes available. Empty = immediately.",
    )
    ends_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="When this challenge expires. Empty = no expiry.",
    )

    is_active = models.BooleanField(default=True)

    # Per-user limit (0 = unlimited)
    max_rewards_per_user = models.PositiveIntegerField(
        default=1,
        help_text="0 means the challenge can be completed without limit per user.",
    )

    # Global limit across all users (0 = unlimited)
    max_total_rewards = models.PositiveIntegerField(
        default=0,
        help_text="0 means no global limit on total rewards for this challenge.",
    )

    # Optional sponsor reference
    sponsor = models.CharField(
        max_length=120,
        blank=True,
        default="",
        help_text="Optional sponsor name for branded challenges.",
    )

    def __str__(self):
        return f"{self.title} (+{self.reward_credits})"

    def is_open(self, now=None):
        """Check if challenge is currently within its time window and active."""
        from django.utils import timezone
        now = now or timezone.now()
        if not self.is_active:
            return False
        if self.type == ChallengeType.MISSION:
            return True
        if self.starts_at and now < self.starts_at:
            return False
        if self.ends_at and now >= self.ends_at:
            return False
        return True

    def global_rewards_claimed(self):
        """Count of verified completions for global cap check."""
        return self.completions.filter(status=ChallengeCompletion.Status.VERIFIED).count()

    def can_claim_globally(self):
        """Check if global reward cap has been reached."""
        if self.max_total_rewards == 0:
            return True
        return self.global_rewards_claimed() < self.max_total_rewards


class ChallengeCompletion(models.Model):
    """One attempt at a challenge, and its proof.

    A completion is created *before* verification so a rejected attempt is
    still auditable (and still blocks the same proof being replayed).  The
    unique constraint is what enforces that: the same user cannot submit the
    same evidence twice.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        VERIFIED = "verified", "Verified"
        REJECTED = "rejected", "Rejected"

    challenge = models.ForeignKey(
        Challenge,
        on_delete=models.CASCADE,
        related_name="completions",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="challenge_completions",
    )

    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )

    evidence = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="The proof a verifier inspects (a user id, a post link, …).",
    )

    detail = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Why a verification was rejected, when it was.",
    )

    reward_transaction = models.OneToOneField(
        CreditTransaction,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="challenge_completion",
    )

    # Idempotency key for duplicate-safe submission (client-generated)
    idempotency_key = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        help_text="Client-provided key to prevent duplicate submissions.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["challenge", "user", "evidence"],
                name="unique_challenge_evidence_per_user",
            ),
            models.UniqueConstraint(
                fields=["idempotency_key"],
                condition=models.Q(idempotency_key__gt=""),
                name="unique_idempotency_key",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "challenge", "status"]),
        ]

    def __str__(self):
        return f"{self.user} · {self.challenge.slug} ({self.status})"
