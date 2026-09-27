"""Give accounts that existed before credits a ledgered welcome balance.

The wallet was added with a zero default and funded by a signal on user
creation, so accounts created earlier would otherwise sit at zero forever.
Each backfilled account gets the same opening balance, with the same ledger
row a new account would get.
"""

from django.db import migrations

SIGNUP_CREDITS = 200


def grant_welcome_credits(apps, schema_editor):
    User = apps.get_model("account", "CustomUser")
    CreditTransaction = apps.get_model("credits", "CreditTransaction")

    unfunded = User.objects.filter(credit_balance=0).exclude(
        pk__in=CreditTransaction.objects.values("user_id")
    )
    for user in unfunded.iterator():
        User.objects.filter(pk=user.pk).update(credit_balance=SIGNUP_CREDITS)
        CreditTransaction.objects.create(
            user_id=user.pk,
            kind="reward",
            amount=SIGNUP_CREDITS,
            balance_after=SIGNUP_CREDITS,
            note="Welcome bonus",
        )


def noop(apps, schema_editor):
    """Nothing to undo: the balance is a wallet, not a schema change."""


class Migration(migrations.Migration):
    dependencies = [
        ("credits", "0002_seed_challenges"),
        ("account", "0003_customuser_credit_balance_customuser_referred_by"),
    ]

    operations = [
        migrations.RunPython(grant_welcome_credits, noop),
    ]
