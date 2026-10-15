"""Models for the AI image studio.

Two tables, two responsibilities:

* ``AIConfig`` — the model provider credentials and model name.  One row,
  created and edited in the Django admin, so an operator can switch provider
  or rotate the API key without a code change or a deploy.
* ``GeneratedImage`` — one row per generation attempt.  It is the user's
  gallery, the record of what was charged and (for image-to-image) the
  reference image the result came from.  A failed attempt is recorded too:
  the user should see what went wrong, and the charge is refunded.
"""

from django.conf import settings
from django.db import models

DEFAULT_BASE_URL = "https://api.gapgpt.app/v1"
DEFAULT_MODEL = "gapgpt/z-image"
DEFAULT_SIZE = "1024x1024"
DEFAULT_CREDIT_COST = 80
DEFAULT_PREMIUM_CREDIT_COST = 160

# Watermark defaults
DEFAULT_WATERMARK_TEXT = "Promptya"
DEFAULT_WATERMARK_OPACITY = 30  # 0-255
DEFAULT_WATERMARK_SIZE_RATIO = 0.08  # Fraction of image width


class AIConfig(models.Model):
    """Provider settings for image generation (a single, admin-edited row)."""

    base_url = models.URLField(
        max_length=200,
        default=DEFAULT_BASE_URL,
        help_text="OpenAI-compatible API root, e.g. https://api.gapgpt.app/v1",
    )

    api_key = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Bearer token for the provider. Leave empty to keep generation disabled.",
    )

    model = models.CharField(
        max_length=100,
        default=DEFAULT_MODEL,
        help_text="Model id sent to the provider, e.g. gapgpt/z-image",
    )

    image_size = models.CharField(
        max_length=20,
        default=DEFAULT_SIZE,
        help_text="Size requested from the provider, e.g. 1024x1024",
    )

    timeout_seconds = models.PositiveIntegerField(
        default=120,
        help_text="How long to wait for the provider before giving up.",
    )

    credit_cost = models.PositiveIntegerField(
        default=DEFAULT_CREDIT_COST,
        help_text=("Credits charged per generation. Configurable per "
                   "model/provider by editing this row."),
    )

    premium_credit_cost = models.PositiveIntegerField(
        default=DEFAULT_PREMIUM_CREDIT_COST,
        help_text=("Credits charged for premium (no-watermark) generation. "
                   "Must be >= credit_cost."),
    )

    prompt_use_reward = models.PositiveIntegerField(
        default=0,
        help_text=("Credits paid to a prompt's author each time someone generates "
                   "an image from it. 0 turns the creator reward off. Capped at the "
                   "generation's own price, and paid only for a successful generation."),
    )

    # Watermark configuration
    watermark_text = models.CharField(
        max_length=50,
        default=DEFAULT_WATERMARK_TEXT,
        help_text="Text to render as watermark on standard generations.",
    )

    watermark_opacity = models.PositiveIntegerField(
        default=DEFAULT_WATERMARK_OPACITY,
        help_text="Watermark opacity 0-255 (0=invisible, 255=opaque).",
    )

    watermark_size_ratio = models.FloatField(
        default=DEFAULT_WATERMARK_SIZE_RATIO,
        help_text="Watermark font size as fraction of image width (e.g., 0.08 = 8%).",
    )

    is_enabled = models.BooleanField(
        default=True,
        help_text="Turn the studio's generate button off without deleting the key.",
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "AI provider settings"
        verbose_name_plural = "AI provider settings"

    def __str__(self):
        return f"{self.model} @ {self.base_url}"

    @classmethod
    def load(cls):
        """The active configuration, or an unsaved default if none exists."""
        return cls.objects.order_by("pk").first() or cls()

    @property
    def is_ready(self):
        return bool(self.is_enabled and self.api_key)


class GeneratedImage(models.Model):
    """One AI generation attempt, successful or not."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    class Tier(models.TextChoices):
        STANDARD = "standard", "Standard (Watermarked)"
        PREMIUM = "premium", "Premium (No Watermark)"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="generated_images",
    )

    source_post = models.ForeignKey(
        "posts.Post",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="generations",
        help_text="The prompt post this image was remixed from, if any.",
    )

    prompt = models.TextField()

    image = models.ImageField(
        upload_to="generated_images/%Y/%m/",
        blank=True,
        null=True,
    )

    source_image = models.ImageField(
        upload_to="generated_sources/%Y/%m/",
        blank=True,
        null=True,
        help_text="The reference image this generation was remixed from (image-to-image).",
    )

    tier = models.CharField(
        max_length=10,
        choices=Tier.choices,
        default=Tier.STANDARD,
        help_text="Output tier: standard (watermarked) or premium (no watermark).",
    )

    credit_cost = models.PositiveIntegerField(
        default=0,
        help_text="Credits charged for this generation, for refunds and audits.",
    )

    creator_reward = models.PositiveIntegerField(
        default=0,
        help_text="Credits paid to the source prompt's author for this generation.",
    )

    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )

    error = models.TextField(
        blank=True,
        default="",
    )

    provider_model = models.CharField(
        max_length=100,
        blank=True,
        default="",
    )

    # Idempotency key to prevent duplicate charges on retry.
    # Client generates a unique key per generation attempt and sends it in
    # the Idempotency-Key header. If a request with the same key is received
    # within 24 hours, the existing result is returned.
    idempotency_key = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        help_text="Client-provided idempotency key for duplicate prevention.",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    finished_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.user} · {self.prompt[:40]}"
