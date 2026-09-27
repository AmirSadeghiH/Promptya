"""The only place a credit balance is ever written.

Every movement goes through ``_apply``, which runs one guarded SQL ``UPDATE``
inside a transaction.  Guarding the balance in the ``WHERE`` clause (rather
than read-modify-write in Python) is what keeps the balance correct under
concurrent requests: the database decides the winner, and a charge that would
push the balance below zero simply matches no rows and is refused.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import F

from credits.models import CreditTransaction, TransactionKind

# A brand-new account starts here.  Granted by credits.signals, not as a
# column default, so the opening balance has a ledger row like everything else.
SIGNUP_CREDITS = 200


class InsufficientCredits(RuntimeError):
    """The wallet cannot cover the charge. Nothing was written."""

    def __init__(self, balance: int, required: int):
        self.balance = int(balance)
        self.required = int(required)
        self.shortfall = max(0, self.required - self.balance)
        super().__init__(
            f"Needs {self.required} credits, but the balance is {self.balance}."
        )


def get_balance(user) -> int:
    if user is None or not getattr(user, "is_authenticated", False):
        return 0
    value = get_user_model().objects.filter(pk=user.pk).values_list(
        "credit_balance", flat=True
    ).first()
    return int(value or 0)


def history(user, limit: int = 20):
    if user is None or not getattr(user, "is_authenticated", False):
        return []
    return list(
        CreditTransaction.objects.filter(user=user).select_related("challenge")[:limit]
    )


def _apply(user, delta, kind, *, generation=None, challenge=None, note=""):
    """Move ``delta`` credits and record the movement. Atomic by construction."""
    if not delta:
        delta = 0

    User = get_user_model()
    with transaction.atomic():
        if delta < 0:
            # Conditional update: succeeds only if the balance can absorb the
            # debit, so two concurrent charges can never overdraw the wallet.
            updated = User.objects.filter(
                pk=user.pk, credit_balance__gte=-delta
            ).update(credit_balance=F("credit_balance") + delta)
            if not updated:
                raise InsufficientCredits(get_balance(user), -delta)
        else:
            User.objects.filter(pk=user.pk).update(
                credit_balance=F("credit_balance") + delta
            )

        balance = get_balance(user)
        return CreditTransaction.objects.create(
            user_id=user.pk,
            kind=kind,
            amount=delta,
            balance_after=balance,
            generation=generation,
            challenge=challenge,
            note=note[:200],
        )


def charge(user, amount, *, generation=None, note="") -> CreditTransaction:
    """Spend ``amount`` credits. Raises ``InsufficientCredits`` if short."""
    amount = int(amount)
    if amount < 0:
        raise ValueError("A charge must be positive.")
    return _apply(
        user, -amount, TransactionKind.GENERATION, generation=generation, note=note
    )


def refund(user, amount, *, generation=None, note="") -> CreditTransaction:
    amount = int(amount)
    if amount <= 0:
        raise ValueError("A refund must be positive.")
    return _apply(
        user, amount, TransactionKind.REFUND, generation=generation, note=note
    )


def reward(user, amount, *, challenge=None, note="") -> CreditTransaction:
    amount = int(amount)
    if amount <= 0:
        raise ValueError("A reward must be positive.")
    return _apply(
        user, amount, TransactionKind.REWARD, challenge=challenge, note=note
    )


def adjust(user, delta, *, note="") -> CreditTransaction:
    """Admin correction in either direction.

    A debit adjustment may legitimately take a balance to zero, so it is
    clamped rather than refused — an operator lowering a balance should not
    have to know its exact value.
    """
    delta = int(delta)
    if delta < 0:
        delta = -min(abs(delta), get_balance(user))
    return _apply(user, delta, TransactionKind.ADJUSTMENT, note=note)
