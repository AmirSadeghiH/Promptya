"""Deployment checks for the configuration SEO correctness depends on.

This is not a style opinion.  A missing ``SITE_URL`` in production does not
degrade gracefully: canonical tags, hreflang, ``og:url``, JSON-LD and the sitemap
all fall back to whatever ``Host`` the crawler sent, which is the exact failure
mode this work was written to eliminate.
"""

import sys
from urllib.parse import urlsplit

from django.conf import settings
from django.core.checks import Error, Warning

from web.seo import site_origin


def _under_test_runner():
    """True while ``manage.py test`` is running this process.

    The test runner forces ``DEBUG=False``, which is exactly the condition these
    checks exist to catch — so on a clean checkout, with no ``SITE_URL`` in the
    environment, the suite could not start.  Exempting the test runner keeps the
    production guard intact; the alternative, relaxing the checks, would delete
    the one thing that catches a misconfigured deploy.  Each test that needs an
    origin sets one explicitly with ``override_settings``.
    """
    return "test" in sys.argv and "runserver" not in sys.argv


def site_url_check(app_configs, **kwargs):
    """``SITE_URL`` must be set in production, and must be an HTTPS origin."""
    if _under_test_runner():
        return []

    if not site_origin():
        if settings.DEBUG:
            return [
                Warning(
                    "SITE_URL is not set; canonical URLs, hreflang, Open Graph "
                    "and the sitemap are built from the incoming Host header.",
                    hint="Set PROMPTYA_SITE_URL=https://yourdomain.com in production.",
                    id="web.W001",
                )
            ]
        return [
            Error(
                "SITE_URL is not set while DEBUG is off. Canonical URLs, hreflang, "
                "Open Graph, JSON-LD and robots.txt would all be built from the "
                "incoming Host header, which lets a client rewrite the canonical "
                "address of any page.",
                hint="Set PROMPTYA_SITE_URL=https://yourdomain.com in the environment.",
                id="web.E001",
            )
        ]

    origin = site_origin()
    if not settings.DEBUG and urlsplit(origin).scheme != "https":
        return [
            Error(
                f"SITE_URL is {origin!r}, which is not HTTPS. Every canonical URL "
                "and sitemap entry would point at an insecure origin.",
                hint="Set PROMPTYA_SITE_URL=https://yourdomain.com.",
                id="web.E002",
            )
        ]
    return []


def sitemap_hosts_check(app_configs, **kwargs):
    """Every sitemap must resolve its domain and protocol from ``SITE_URL``.

    Django's sitemap view derives both from the *request* unless the sitemap
    class overrides them, which is how a crawler connecting over http could end
    up with ``http://`` entries in a sitemap that robots.txt advertises as
    ``https://``.
    """
    from web.sitemaps import SITEMAPS

    if _under_test_runner():
        return []

    origin = site_origin()
    if not origin:
        return []
    expected_domain = urlsplit(origin).netloc

    problems = []
    for label, sitemap_class in SITEMAPS.items():
        sitemap = sitemap_class() if callable(sitemap_class) else sitemap_class
        if sitemap.get_domain() != expected_domain:
            problems.append(
                Error(
                    f"Sitemap {label!r} reports domain {sitemap.get_domain()!r}, "
                    f"expected {expected_domain!r} from SITE_URL.",
                    id="web.E003",
                )
            )
        if sitemap.get_protocol() != "https":
            problems.append(
                Error(
                    f"Sitemap {label!r} reports protocol {sitemap.get_protocol()!r}, "
                    "expected 'https'.",
                    id="web.E004",
                )
            )
    return problems
