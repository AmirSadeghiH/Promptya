"""Endpoints for earning credits from challenges."""

import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from credits.challenges import ChallengeError, challenge_state, complete_challenge


def _parse_body(request):
    try:
        data = json.loads(request.body.decode("utf-8")) if request.body else {}
    except (ValueError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _wallet(user):
    """Balance + cost + challenges in one shape, reused by every response.

    Imported lazily so credits does not import imagegen at module load.
    """
    from imagegen.services import credit_payload

    return credit_payload(user)


@login_required
@csrf_exempt
@require_POST
def claim_challenge(request, slug):
    data = _parse_body(request)
    if data is None:
        return JsonResponse(
            {"error_code": "bad_request", "error": "Invalid JSON body."}, status=400
        )

    try:
        completion, transaction_row = complete_challenge(
            request.user, slug, evidence=data.get("evidence", "")
        )
    except ChallengeError as exc:
        return JsonResponse(
            {
                "error_code": exc.code,
                "error": str(exc),
                "credits": _wallet(request.user),
                "challenges": challenge_state(request.user),
            },
            status=400,
        )

    return JsonResponse(
        {
            "challenge": completion.challenge.slug,
            "status": completion.status,
            "reward": transaction_row.amount,
            "balance": transaction_row.balance_after,
            "credits": _wallet(request.user),
            "challenges": challenge_state(request.user),
        },
        status=201,
    )
