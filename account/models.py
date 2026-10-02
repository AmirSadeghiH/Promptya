from django.contrib.auth.models import AbstractUser
from django.db import models


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
