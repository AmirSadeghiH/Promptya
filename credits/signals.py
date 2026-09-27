"""Signup bonus: every wallet opens with the same, ledgered, opening balance."""

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from credits.services import SIGNUP_CREDITS, reward


@receiver(post_save, sender=settings.AUTH_USER_MODEL, dispatch_uid="credits.signup_bonus")
def grant_signup_credits(sender, instance, created, **kwargs):
    if not created:
        return
    # A user created with a balance already set (fixtures, admin) keeps it.
    if instance.credit_balance:
        return
    reward(instance, SIGNUP_CREDITS, note="Welcome bonus")
