"""Studio rules: what may be generated, what it costs, and where it is stored.

The view layer stays thin — it parses input, calls one of these functions and
turns the outcome into JSON.  Everything a second caller would need to agree
with (the prompt limits, the credit price, how a download becomes a stored
file) lives here.

A generation is a two-sided ledger event: credits are charged up front, the
provider is called, and a failure refunds the charge.  The charge/refund pair
is what makes a provider outage cost the user nothing.
"""

from __future__ import annotations

import logging
import secrets
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from credits.services import InsufficientCredits, charge, get_balance, refund, reward
from posts.models import Post
from posts.validation import validate_upload_file

from imagegen.client import (
    GenerationError,
    ImageProvider,
    ProviderSettings,
    SourceImage,
)
from imagegen.models import AIConfig, GeneratedImage

logger = logging.getLogger(__name__)

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover - Pillow is a hard dependency
    Image = ImageDraw = ImageFont = None

# Generous on purpose: real community prompts run long (over a thousand
# characters is common), and the provider has its own limits.
MAX_PROMPT_LENGTH = 2000

# Formats the provider may hand back, mapped to a safe file extension.
_EXTENSIONS_BY_FORMAT = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp", "GIF": "gif"}

LIBRARY_LIMIT = 12


class PromptRejected(ValueError):
    """The prompt itself cannot be sent (empty, or too long)."""


class SourceImageRejected(ValueError):
    """The uploaded reference image is not usable."""


class TierError(ValueError):
    """Invalid tier requested (e.g., premium without sufficient credits)."""


# ---------------------------------------------------------------------------
# Prompt / wallet
# ---------------------------------------------------------------------------


def check_prompt(prompt) -> str:
    """Return the cleaned prompt, or raise ``PromptRejected``."""
    cleaned = " ".join(str(prompt or "").split())
    if not cleaned:
        raise PromptRejected("Write a prompt first.")
    if len(cleaned) > MAX_PROMPT_LENGTH:
        raise PromptRejected(f"Prompts are limited to {MAX_PROMPT_LENGTH} characters.")
    return cleaned


def get_tier_cost(config: AIConfig, tier: str) -> int:
    """Return the authoritative server-side credit cost for a tier."""
    if tier == GeneratedImage.Tier.PREMIUM:
        return int(config.premium_credit_cost or config.credit_cost * 2)
    return int(config.credit_cost or 0)


def credit_payload(user, config=None) -> dict | None:
    """The wallet shape every studio response carries (balance + price)."""
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    config = config or AIConfig.load()
    balance = get_balance(user)
    standard_cost = int(config.credit_cost or 0)
    premium_cost = int(config.premium_credit_cost or standard_cost * 2)
    return {
        "balance": balance,
        "cost": standard_cost,
        "premium_cost": premium_cost,
        "can_afford": balance >= standard_cost,
        "can_afford_premium": balance >= premium_cost,
        "shortfall": max(0, standard_cost - balance),
        "premium_shortfall": max(0, premium_cost - balance),
    }


# ---------------------------------------------------------------------------
# Watermarking
# ---------------------------------------------------------------------------


def _apply_watermark(image_bytes: bytes, config: AIConfig) -> bytes:
    """Apply server-side watermark to image bytes. Returns watermarked bytes."""
    if Image is None:
        raise GenerationError("Pillow not available for watermarking.")

    try:
        with Image.open(BytesIO(image_bytes)) as img:
            img = img.convert("RGBA")
            width, height = img.size

            # Create transparent overlay for watermark
            overlay = Image.new("RGBA", img.size, (255, 255, 255, 0))
            draw = ImageDraw.Draw(overlay)

            # Calculate font size based on image width
            font_size = max(12, int(width * (config.watermark_size_ratio or 0.08)))

            # Try to load a default font, fall back to built-in
            font = None
            try:
                font = ImageFont.truetype("arial.ttf", font_size)
            except Exception:
                try:
                    font = ImageFont.load_default()
                except Exception:
                    pass

            # Watermark text
            text = config.watermark_text or "Promptya"
            opacity = max(0, min(255, config.watermark_opacity or 30))

            # Calculate text position (bottom-right with padding)
            padding = max(10, int(width * 0.02))
            if font:
                bbox = draw.textbbox((0, 0), text, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
            else:
                text_width = len(text) * font_size // 2
                text_height = font_size

            x = width - text_width - padding
            y = height - text_height - padding

            # Draw watermark with opacity
            draw.text(
                (x, y),
                text,
                font=font,
                fill=(255, 255, 255, opacity),
                stroke_width=max(1, font_size // 20),
                stroke_fill=(0, 0, 0, opacity),
            )

            # Composite watermark onto original
            watermarked = Image.alpha_composite(img, overlay)

            # Convert back to RGB for JPEG compatibility
            if watermarked.mode == "RGBA":
                rgb_img = Image.new("RGB", watermarked.size, (255, 255, 255))
                rgb_img.paste(watermarked, mask=watermarked.split()[3])
                watermarked = rgb_img

            # Save to bytes
            output = BytesIO()
            watermarked.save(output, format="PNG")
            return output.getvalue()
    except Exception as exc:
        raise GenerationError("Failed to apply watermark.") from exc


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


def generate_image(
    user,
    prompt,
    *,
    size=None,
    source_post=None,
    source_image=None,
    provider_factory=None,
    idempotency_key=None,
    tier=None,
):
    """Generate one image for *user* and store it.

    Raises ``PromptRejected``, ``SourceImageRejected``, ``InsufficientCredits``
    or ``GenerationError``.  Credits are charged before the provider is
    contacted and refunded if it fails, so the wallet always matches reality.

    If ``idempotency_key`` is provided, checks for an existing generation with
    the same key from the same user within the last 24 hours and returns it
    instead of creating a new one.

    ``tier`` must be one of GeneratedImage.Tier values. Defaults to STANDARD.
    Server-side credit cost is determined by tier from AIConfig.
    """
    cleaned = check_prompt(prompt)

    config = AIConfig.load()
    if not config.is_ready:
        raise GenerationError(
            "Image generation is turned off right now. Try again once an admin enables it."
        )

    # Validate and normalize tier
    tier = tier or GeneratedImage.Tier.STANDARD
    if tier not in GeneratedImage.Tier.values:
        raise TierError(f"Invalid tier: {tier}")

    # Get authoritative server-side cost for the tier
    cost = get_tier_cost(config, tier)

    # Idempotency check: if key provided, look for existing completed generation
    if idempotency_key:
        from django.utils import timezone
        from datetime import timedelta

        existing = GeneratedImage.objects.filter(
            user=user,
            idempotency_key=idempotency_key,
            status__in=[GeneratedImage.Status.READY, GeneratedImage.Status.FAILED],
            created_at__gte=timezone.now() - timedelta(hours=24),
        ).first()
        if existing:
            # Verify tier matches (can't upgrade/downgrade via replay)
            if existing.tier != tier:
                raise TierError("Idempotency key tier mismatch.")
            return existing

    record = GeneratedImage.objects.create(
        user=user,
        prompt=cleaned,
        source_post=source_post,
        provider_model=config.model,
        credit_cost=cost,
        status=GeneratedImage.Status.PENDING,
        idempotency_key=idempotency_key or "",
        tier=tier,
    )

    # Reserve the credits before doing any work. A refusal here is final: the
    # user is told, and nothing is owed.
    try:
        charge(user, cost, generation=record, note=f"AI generation ({tier})")
    except InsufficientCredits:
        record.delete()
        raise

    source = None
    if source_image is not None:
        try:
            source = _store_source_image(record, source_image)
        except SourceImageRejected:
            _refund(record)
            record.delete()
            raise

    # Resolved at call time, not bound as a default, so the provider is
    # swappable (tests inject one; nothing reaches for the network).
    factory = provider_factory or ImageProvider
    provider = factory(ProviderSettings.from_config(config))
    try:
        payload = provider.generate(cleaned, size or config.image_size, source)
        
        # Apply server-side watermark for standard tier
        if tier == GeneratedImage.Tier.STANDARD:
            payload = _apply_watermark(payload, config)
            
        _store_image(record, payload)
    except GenerationError as exc:
        _mark_failed(record, str(exc))
        _refund(record)
        raise
    except Exception as exc:  # unexpected provider-adapter bug
        _mark_failed(record, "Something went wrong while generating this image.")
        _refund(record)
        raise GenerationError("Something went wrong while generating this image.") from exc

    _notify_referral(user)
    _pay_prompt_creator(record, config)
    return record


def _refund(record):
    """Give back the charge for a generation that produced nothing.

    Never raises: a bookkeeping hiccup must not mask the real error the user
    is about to see.
    """
    if not record.credit_cost:
        return
    try:
        refund(
            record.user,
            record.credit_cost,
            generation=record,
            note="Refund for a failed generation",
        )
    except Exception:  # pragma: no cover - defensive
        pass


def _pay_prompt_creator(record, config):
    """Pay the author of the prompt this generation used, if the rules allow.

    Paid only for a successful, charged generation, and never to the person
    generating (no paying yourself). The amount is the admin-set reward, capped
    at what the generation itself cost, so the creator reward can never exceed
    the price the user paid. The guarded update makes the payout happen at most
    once per generation even if this runs twice.

    Never raises: a failed reward must not turn a finished image into an error.
    """
    reward_amount = min(int(config.prompt_use_reward or 0), int(record.credit_cost or 0))
    if reward_amount <= 0 or record.source_post_id is None:
        return
    if record.status != GeneratedImage.Status.READY:
        return

    author_id = Post.objects.filter(pk=record.source_post_id).values_list("author_id", flat=True).first()
    if author_id is None or author_id == record.user_id:
        return

    try:
        with transaction.atomic():
            claimed = GeneratedImage.objects.filter(
                pk=record.pk, creator_reward=0
            ).update(creator_reward=reward_amount)
            if not claimed:
                return
            author = get_user_model().objects.get(pk=author_id)
            reward(
                author,
                reward_amount,
                generation=record,
                note=f"Prompt used in a generation (#{record.pk})",
            )
        record.creator_reward = reward_amount
    except Exception:  # pragma: no cover - defensive
        logger.exception("Creator reward failed for generation %s", record.pk)


def _notify_referral(user):
    """Let the rewards layer see the first successful image. Never fatal."""
    try:
        from credits.challenges import on_first_generation

        on_first_generation(user)
    except Exception:  # pragma: no cover - defensive
        pass


def _mark_failed(record, message):
    record.status = GeneratedImage.Status.FAILED
    record.error = message
    record.finished_at = timezone.now()
    record.save(update_fields=["status", "error", "finished_at"])


def _read_source_image(source_image) -> tuple[str, bytes]:
    """Validate an uploaded reference image and return (name, bytes)."""
    try:
        validate_upload_file(source_image, "image")
    except ValidationError as exc:
        raise SourceImageRejected("; ".join(exc.messages)) from exc

    source_image.seek(0)
    data = source_image.read()
    if not data:
        raise SourceImageRejected("The reference image is empty.")

    extension = (source_image.name.rsplit(".", 1)[-1] if "." in source_image.name else "png").lower()
    return extension, data


def _store_source_image(record, source_image) -> SourceImage:
    """Persist the reference image, then hand the bytes to the provider."""
    extension, data = _read_source_image(source_image)
    name = f"source-{record.pk}-{secrets.token_hex(4)}.{extension}"
    record.source_image.save(name, ContentFile(data), save=False)
    record.save(update_fields=["source_image"])
    return SourceImage(filename=name, data=data)


def _store_image(record, payload):
    """Validate the provider's bytes and attach them to the record."""
    extension = _sniff_extension(payload)
    name = f"generation-{record.pk}-{secrets.token_hex(4)}.{extension}"
    file = ContentFile(payload, name=name)

    # The same rules as a user upload: extension, size cap, magic bytes and a
    # full Pillow re-decode.  A "trusted" provider is still an HTTP endpoint.
    try:
        validate_upload_file(file, "image")
    except ValidationError as exc:
        raise GenerationError("The provider returned a file that is not a valid image.") from exc

    record.image.save(name, ContentFile(payload), save=False)
    record.status = GeneratedImage.Status.READY
    record.finished_at = timezone.now()
    record.save(update_fields=["image", "status", "finished_at"])


def _sniff_extension(payload) -> str:
    """Pick a safe extension from the real decoded format, never a guess."""
    if Image is None:  # pragma: no cover - Pillow is a hard dependency
        raise GenerationError("The provider returned an unreadable image.")
    try:
        with Image.open(BytesIO(payload)) as image:
            image_format = (image.format or "").upper()
    except Exception as exc:
        raise GenerationError("The provider returned an unreadable image.") from exc

    extension = _EXTENSIONS_BY_FORMAT.get(image_format)
    if not extension:
        raise GenerationError("The provider returned an unsupported image format.")
    return extension


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def serialize_generation(record, *, label=None) -> dict:
    """The JSON shape the studio's JS renders after a generate call."""
    return {
        "id": record.pk,
        "prompt": record.prompt,
        "image": record.image.url if record.image else None,
        "source_image": record.source_image.url if record.source_image else None,
        "status": record.status,
        "error": record.error,
        "provider_model": record.provider_model,
        "credit_cost": record.credit_cost,
        "tier": record.tier,
        "created_at": record.created_at.isoformat(),
        "label": label or _format_timestamp(record.created_at),
        "source_post_id": record.source_post_id,
    }


def recent_generations(user, limit=12):
    if user is None or not getattr(user, "is_authenticated", False):
        return []
    records = GeneratedImage.objects.filter(user=user).select_related("source_post")[:limit]
    return [serialize_generation(record) for record in records]


def _format_timestamp(value):
    local = timezone.localtime(value)
    return f"{local:%Y-%m-%d %H:%M}"


# ---------------------------------------------------------------------------
# Library
# ---------------------------------------------------------------------------


def prompt_library(limit=LIBRARY_LIMIT):
    """Public prompts a user can copy from, best-provenanced first.

    Prompt posts are pure text; image posts carry the output that prompt
    produced.  Both are useful, and duplicates are collapsed so the same
    popular prompt does not fill the whole shelf.
    """
    queryset = (
        Post.objects.visible().filter(~Q(prompt=""))
        .filter(
            Q(post_type=Post.PostType.PROMPT)
            | (Q(post_type=Post.PostType.IMAGE) & ~Q(image=""))
        )
        .select_related("author")
        .annotate(copy_count=Count("copy_events", distinct=True))
        .order_by("-copy_count", "-created_at")[: limit * 3]
    )

    library = []
    seen = set()
    for post in queryset:
        key = post.prompt.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        library.append(
            {
                "post_id": post.pk,
                "title": post.title,
                "prompt": post.prompt.strip(),
                "excerpt": _excerpt(post.prompt),
                "image": post.image.url if post.image else None,
                "ai_model": post.ai_model,
                "author": post.author.username,
                "copy_count": post.copy_count,
            }
        )
        if len(library) >= limit:
            break
    return library


def _excerpt(text, length=180):
    collapsed = " ".join(str(text or "").split())
    return collapsed if len(collapsed) <= length else collapsed[: length - 1].rstrip() + "…"
