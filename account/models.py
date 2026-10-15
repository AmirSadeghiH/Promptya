from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


def _default_verification_expiry():
    """Kept because migration 0004 references it when it rebuilds history."""
    return timezone.now() + timezone.timedelta(hours=24)


def _default_code_expiry():
    """Default expiry: EMAIL_VERIFICATION_CODE_TTL_SECONDS from now."""
    return timezone.now() + timezone.timedelta(
        seconds=settings.EMAIL_VERIFICATION_CODE_TTL_SECONDS
    )


class CustomUser(AbstractUser):
    display_name = models.CharField(
        max_length=100,
        blank=True
    )

    email = models.EmailField(
        unique=True
    )

    biography = models.TextField(
        blank=True,
        default=''
    )

    is_verified = models.BooleanField(
        default=False
    )

    profile_picture = models.ImageField(
        upload_to='profile_pictures/',
        blank=True,
        null=True
    )

    level = models.PositiveIntegerField(
        default=0
    )

    experience = models.PositiveIntegerField(
        default=0
    )

    # Credit wallet. The signup bonus is granted once, as a ledger entry, by
    # credits.signals so every credit the user ever holds has a reason.
    credit_balance = models.PositiveIntegerField(
        default=0,
        help_text="Credits available for AI generations. Managed by credits.services.",
    )

    # Who invited this account, captured from a ?ref= link at signup.  The
    # referrer is rewarded only after this user's first successful generation.
    referred_by = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="referrals",
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return self.username

    @property
    def display_label(self):
        return self.display_name or self.username

    @property
    def public_post_count(self):
        """Posts a visitor can actually see.

        ``web.views.profile_page`` renders at most ``PROFILE_POST_LIMIT`` of
        them, so counting the rendered list produced a meta description that
        claimed "24 posts" for a creator with three hundred.
        """
        return self.posts.count()

    @property
    def is_indexable(self):
        """A profile with no public content is an empty page, not a result.

        Such profiles stay reachable (they are linked from posts and from the
        follow button) but are excluded from the index and from the sitemap.
        """
        return self.is_active and self.public_post_count > 0


class EmailVerificationToken(models.Model):
    """Row holding a user's emailed verification code.

    The code is a short numeric value, sent by email at signup, valid for
    exactly EMAIL_VERIFICATION_CODE_TTL_SECONDS and usable once. Only its
    salted hash (django.contrib.auth.hashers) is stored — the code itself
    never appears in the database, URLs, or logs. A user has at most one row;
    issuing a new code supersedes and invalidates the previous one.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="verification_token",
    )

    # make_password() output (pbkdf2_sha256, salt embedded in the string).
    # Empty until the first code is issued; a row with an empty hash is inert.
    code_hash = models.CharField(max_length=128, default="")

    # Wrong 6-digit entries against the currently issued code. Reset to 0 on
    # every re-issue; at EMAIL_VERIFICATION_CODE_MAX_ATTEMPTS the code dies.
    attempts = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    expires_at = models.DateTimeField(default=_default_code_expiry)

    used_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        verbose_name = "Email verification code"
        verbose_name_plural = "Email verification codes"

    def __str__(self):
        return f"Verification code for {self.user}"

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at

    def is_valid(self):
        """Issued, not used, not attempt-locked, and not expired."""
        if not self.code_hash or self.used_at is not None:
            return False
        if self.attempts >= settings.EMAIL_VERIFICATION_CODE_MAX_ATTEMPTS:
            return False
        return not self.is_expired

    def mark_used(self):
        """Mark the code as used."""
        self.used_at = timezone.now()
        self.save(update_fields=["used_at"])
