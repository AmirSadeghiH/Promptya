"""Seed the first reward challenges.

The rows are data, not code: an operator can edit the reward, pause the
challenge, or add another one from the admin without a deploy.
"""

from django.db import migrations

CHALLENGES = [
    {
        "slug": "invite_friend",
        "title": "Invite a friend",
        "description": (
            "Share your invite link. You earn the reward once your friend has "
            "generated their first image — a real referral, not a click."
        ),
        "verifier": "invite_friend",
        "reward_credits": 100,
        "is_active": True,
        "max_rewards_per_user": 0,
    },
    {
        "slug": "instagram_share",
        "title": "Share on Instagram",
        "description": (
            "Publish one of your generated images on Instagram and submit the "
            "post link to claim the reward."
        ),
        "verifier": "instagram_share",
        "reward_credits": 40,
        "is_active": True,
        "max_rewards_per_user": 1,
    },
]


def create_challenges(apps, schema_editor):
    Challenge = apps.get_model("credits", "Challenge")
    for row in CHALLENGES:
        Challenge.objects.update_or_create(slug=row["slug"], defaults=row)


def remove_challenges(apps, schema_editor):
    Challenge = apps.get_model("credits", "Challenge")
    Challenge.objects.filter(slug__in=[row["slug"] for row in CHALLENGES]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("credits", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_challenges, remove_challenges),
    ]
