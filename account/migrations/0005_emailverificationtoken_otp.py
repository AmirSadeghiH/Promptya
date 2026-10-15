# Email verification: replace the 24h link token with a short-lived code.
#
# No data migration: pre-deploy rows keep their (about-to-be-dropped) link
# token and gain code_hash="". Such rows are inert — is_valid() requires a
# non-empty hash — and the affected users complete verification through the
# email+code fallback plus a resend, which supersedes the stale row.

import account.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0004_emailverificationtoken"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="emailverificationtoken",
            options={
                "verbose_name": "Email verification code",
                "verbose_name_plural": "Email verification codes",
            },
        ),
        migrations.AddField(
            model_name="emailverificationtoken",
            name="code_hash",
            field=models.CharField(default="", max_length=128),
        ),
        migrations.AddField(
            model_name="emailverificationtoken",
            name="attempts",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name="emailverificationtoken",
            name="expires_at",
            field=models.DateTimeField(default=account.models._default_code_expiry),
        ),
        migrations.RemoveField(
            model_name="emailverificationtoken",
            name="token",
        ),
    ]
