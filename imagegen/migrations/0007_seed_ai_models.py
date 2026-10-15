"""Seed the selectable AI-model list.

The create form offers a dropdown instead of a free-text field, so the table
needs rows on a fresh install.  The seed is deliberately conservative: the
models posters actually name today.  Operators add, remove or deactivate rows
in the admin; this data migration never overwrites an operator's list (it
only runs when the table is empty).
"""

from django.db import migrations

SEED_MODELS = [
    ("GPT-5", 1),
    ("Midjourney", 2),
    ("DALL·E", 3),
    ("Sora", 4),
    ("Stable Diffusion", 5),
    ("Flux", 6),
    ("Z-Image", 7),
]


def seed_ai_models(apps, schema_editor):
    AIModel = apps.get_model("imagegen", "AIModel")
    if AIModel.objects.exists():
        return  # the operator already manages this list
    for name, position in SEED_MODELS:
        AIModel.objects.create(name=name, position=position)


def unseed_ai_models(apps, schema_editor):
    """Remove only the rows this migration created (names + positions match)."""
    AIModel = apps.get_model("imagegen", "AIModel")
    for name, position in SEED_MODELS:
        AIModel.objects.filter(name=name, position=position).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("imagegen", "0006_aimodel"),
    ]

    operations = [
        migrations.RunPython(seed_ai_models, unseed_ai_models),
    ]
