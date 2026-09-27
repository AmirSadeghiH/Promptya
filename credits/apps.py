from django.apps import AppConfig


class CreditsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "credits"
    verbose_name = "Credits & rewards"

    def ready(self):
        from credits import signals  # noqa: F401  (registers the receivers)
