"""Context processors exposing language, direction, UI strings and site entities."""

import json

from django.templatetags.static import static

from web.i18n_strings import LANG_COOKIE, STRINGS
from web.seo import (
    DEFAULT_LANGUAGE,
    LANGUAGES,
    absolute_media_url,
    absolute_path,
    active_language,
    language_direction,
    organization_node,
    seo_strings,
    website_node,
)


def ui_prefs(request):
    """Expose the render language and its strings to every template.

    The language comes from :func:`web.seo.active_language`, which
    ``web.middleware.LanguageMiddleware`` already resolved from the URL prefix
    first and the cookie second.  Reading the resolved value here (rather than
    re-reading the cookie) is what keeps ``<html lang>``, ``dir``, the page copy
    and the canonical URL from ever disagreeing about which language is being
    served.
    """
    lang = active_language(request)
    return {
        "lang": lang,
        "dir": language_direction(lang),
        "i18n": STRINGS[lang],
        "i18n_json": json.dumps(STRINGS),
        # The languages the site is published in, and the one hreflang's
        # x-default points at. Templates need both to emit a complete,
        # reciprocal alternate set.
        "site_languages": LANGUAGES,
        "default_language": DEFAULT_LANGUAGE,
        "lang_cookie": LANG_COOKIE,
    }


def seo_prefs(request):
    """The site-wide half of the SEO context.

    Page-specific metadata — title, description, robots directive, Open Graph
    image, the page's own structured data — is built by the view, which is the
    only place that knows what the page is.  The pieces that are identical on
    every page belong here so that no view can forget them and no template has to
    rebuild them:

    * ``site_website_node`` / ``site_organization_node`` — the two entities every
      page's graph is tied to by ``@id``.
    * ``site_origin`` — the one origin absolute URLs are built from, exposed so a
      template never has to reach for ``request.get_host()``.
    """
    return {
        "site_website_node": website_node(request),
        "site_organization_node": organization_node(request),
        "site_origin": absolute_path("/", request),
        "default_og_image": absolute_media_url(static("icons/icon-512.png"), request),
        "seo_labels": seo_strings(active_language(request)),
    }
