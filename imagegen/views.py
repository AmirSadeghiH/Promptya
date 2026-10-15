"""JSON endpoints for the AI image studio.

Thin by design: parse, delegate to ``services``, map each domain failure onto
one machine-readable ``error_code`` (the client owns the wording, so the
message can switch language without a page reload).

One endpoint accepts both content types, because the same generate action can
carry a file or not: ``application/json`` for text-to-image, and
``multipart/form-data`` when a reference image rides along for image-to-image.
"""

import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from core.ratelimit import rate_limit_user
from credits.services import InsufficientCredits
from posts.models import Post

from imagegen.client import GenerationError
from imagegen.models import GeneratedImage
from imagegen.services import (
    MAX_PROMPT_LENGTH,
    PromptRejected,
    SourceImageRejected,
    TierError,
    credit_payload,
    generate_image,
    serialize_generation,
)


def _parse_json_body(request):
    if not request.body:
        return {}
    try:
        data = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _read_request(request):
    """(fields, uploaded image) from either a JSON body or a multipart form."""
    if (request.content_type or "").startswith("multipart/form-data"):
        return request.POST, request.FILES.get("source_image")
    return _parse_json_body(request), None


def _source_post(data):
    """The prompt-library post this generation was remixed from, if any."""
    raw_id = data.get("source_post_id")
    if isinstance(raw_id, str) and raw_id.strip().isdigit():
        raw_id = int(raw_id.strip())
    if not isinstance(raw_id, int):
        return None
    return Post.objects.visible().filter(pk=raw_id).first()


@login_required
@rate_limit_user("generate", limit=10, window_seconds=60, error_message="Too many generation requests. Try again in a minute.")
@rate_limit_user("generate_hourly", limit=50, window_seconds=3600, error_message="Hourly generation limit reached. Try again later.")
@require_POST
def api_generate(request):
    data, source_image = _read_request(request)
    if data is None:
        return JsonResponse(
            {"error_code": "bad_request", "error": "Invalid JSON body."}, status=400
        )

    # Extract idempotency key from header (optional but recommended for retries)
    idempotency_key = request.headers.get("Idempotency-Key", "").strip() or None
    if idempotency_key and len(idempotency_key) > 64:
        return JsonResponse(
            {"error_code": "bad_request", "error": "Idempotency-Key too long (max 64 chars)."},
            status=400,
        )

    # Extract and validate tier
    tier = (data.get("tier") or "").strip().lower() or GeneratedImage.Tier.STANDARD
    if tier not in GeneratedImage.Tier.values:
        return JsonResponse(
            {"error_code": "bad_request", "error": f"Invalid tier: {tier}. Must be 'standard' or 'premium'."},
            status=400,
        )

    try:
        record = generate_image(
            request.user,
            data.get("prompt"),
            size=str(data.get("size") or "").strip() or None,
            source_post=_source_post(data),
            source_image=source_image,
            idempotency_key=idempotency_key,
            tier=tier,
        )
    except PromptRejected as exc:
        return JsonResponse(
            {
                "error_code": "invalid_prompt",
                "error": str(exc),
                "max_length": MAX_PROMPT_LENGTH,
                "credits": credit_payload(request.user),
            },
            status=400,
        )
    except SourceImageRejected as exc:
        return JsonResponse(
            {
                "error_code": "invalid_image",
                "error": str(exc),
                "credits": credit_payload(request.user),
            },
            status=400,
        )
    except InsufficientCredits as exc:
        # 402 is the honest status: the request is well-formed, the wallet is short.
        return JsonResponse(
            {
                "error_code": "insufficient_credits",
                "error": str(exc),
                "required": exc.required,
                "balance": exc.balance,
                "shortfall": exc.shortfall,
                "credits": credit_payload(request.user),
            },
            status=402,
        )
    except TierError as exc:
        return JsonResponse(
            {
                "error_code": "invalid_tier",
                "error": str(exc),
                "credits": credit_payload(request.user),
            },
            status=400,
        )
    except GenerationError as exc:
        return JsonResponse(
            {
                "error_code": "provider_error",
                "error": str(exc),
                "credits": credit_payload(request.user),
            },
            status=502,
        )

    return JsonResponse(
        {
            "generation": serialize_generation(record),
            "credits": credit_payload(request.user),
        },
        status=201,
    )
