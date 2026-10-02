from django.apps import AppConfig
from django.core.checks import register


class WebConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "web"
    verbose_name = "Web"

    def ready(self):
        # Deployment guards for the SEO surface. Imported here rather than at
        # module level so `manage.py check` runs them after the app registry is
        # populated (sitemap_hosts_check imports models).
        from web import checks

        register(checks.site_url_check)
        register(checks.sitemap_hosts_check)
