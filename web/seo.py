"""Single source of truth for Promptya's search-engine surface.

Everything a crawler reads about a page — the canonical URL, the hreflang set,
the absolute Open Graph / JSON-LD URLs, the robots directive — is computed here
rather than in a template.  Three reasons:

* **Testable.** ``web/test_seo.py`` asserts on these functions directly instead of
  scraping rendered HTML for a string.
* **One place to be right.**  A canonical that is correct in the ``<head>`` but
  relative inside the JSON-LD is worse than no canonical at all.
* **Host-header proof.**  Absolute URLs come from ``settings.SITE_URL`` (see
  ``core/settings.py``), never from ``request.get_host()``, so a spoofed ``Host``
  cannot rewrite a canonical tag, an ``og:url`` or a sitemap entry.

URL strategy (full rationale in ``docs/seo/SEO_AUDIT.md`` §4):

* ``/en/<path>`` and ``/fa/<path>`` are the canonical, crawlable addresses.
* ``/<path>`` keeps working exactly as before and canonicalises to the reader's
  language version, so no existing link, the PWA start_url, the service worker
  precache or the mobile API client ever sees a redirect.
"""

from urllib.parse import urlsplit

import re

from django.conf import settings
from django.urls import reverse

from web.i18n_strings import LANG_COOKIE, SEO_STRINGS

#: The language whose URLs are pointed at by ``x-default``.
DEFAULT_LANGUAGE = "en"

#: Every language the site is published in, in sitemap/hreflang order.  The first
#: entry is the default language.
LANGUAGES = ("en", "fa")

#: Length budgets.  Google truncates the title around 60 characters and the
#: description around 155-160; these are the ceilings every builder enforces so a
#: dynamic page can never emit an oversized tag.
TITLE_LIMIT = 70
DESCRIPTION_LIMIT = 160

#: A collection page needs at least this many items before it is worth indexing.
#: One-post tag pages are thin, and thin pages at scale are a quality problem, not
#: a traffic problem.  Imported from ``posts.models`` (not redefined) so the
#: sitemap, the robots directive and the page itself can never disagree.
from posts.models import MIN_INDEXABLE_COLLECTION_ITEMS  # noqa: E402

#: ``robots`` directives used across the site.  ``noarchive``/``noodp`` are left
#: out on purpose: there is no cached-copy or answer-box claim to deny, and
#: denying them can suppress legitimate snippet features.
ROBOTS_INDEX = "index, follow, max-image-preview:large, max-snippet:-1, max-video-preview:-1"
ROBOTS_NOINDEX_FOLLOW = "noindex, follow"
ROBOTS_NOINDEX_NOFOLLOW = "noindex, nofollow"


# ---------------------------------------------------------------------------
# Site identity
# ---------------------------------------------------------------------------


def site_origin():
    """``https://host[:port]`` from ``SITE_URL``, or "" when it is not configured."""
    configured = (getattr(settings, "SITE_URL", "") or "").strip().rstrip("/")
    if not configured:
        return ""
    parts = urlsplit(configured if "//" in configured else f"https://{configured}")
    if not parts.scheme or not parts.netloc:
        return ""
    return f"{parts.scheme}://{parts.netloc}"


def request_origin(request):
    """Origin of the incoming request, used only as a development fallback."""
    if request is None:
        return site_origin()
    return f"{request.scheme}://{request.get_host()}"


def origin(request=None):
    """The one origin every absolute URL on the page is built from."""
    return site_origin() or request_origin(request)


def media_origin(request=None):
    """Origin for ``/media/`` files.

    Uploaded media is usually served from a CDN or object store in production.  If
    ``MEDIA_URL`` is absolute the site's origin is wrong for those files, so the
    media host wins; a relative ``MEDIA_URL`` keeps them on the site origin.
    """
    media_url = (getattr(settings, "MEDIA_URL", "") or "").strip()
    if media_url.startswith(("http://", "https://", "//")):
        if media_url.startswith("//"):
            return f"{request.scheme if request is not None else 'https'}:{media_url}"
        return media_url.rstrip("/")
    return origin(request)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def split_language_prefix(path):
    """Split a leading ``/fa`` or ``/en`` segment off *path*.

    Returns ``(language_or_None, neutral_path)``.  Only a whole segment counts, so
    ``/faq/`` and ``/english/`` are left alone.  The neutral path is what the view
    layer actually routed, which is why every language version of a page can be
    described by the same neutral path.
    """
    if not path:
        return None, "/"
    stripped = path.lstrip("/")
    head, _, rest = stripped.partition("/")
    if head in LANGUAGES:
        return head, f"/{rest}" if rest else "/"
    return None, path


def language_path(path, language):
    """``path`` addressed for *language* (always prefixed)."""
    _, neutral = split_language_prefix(path)
    return f"/{language}{neutral}"


def neutral_path(request):
    """The current request's path with any language prefix removed."""
    return split_language_prefix(request.path)[1]


def normalize_path(path):
    """Collapse duplicate slashes and guarantee a single leading slash."""
    if not path:
        return "/"
    collapsed = re.sub(r"/{2,}", "/", path)
    if not collapsed.startswith("/"):
        collapsed = "/" + collapsed
    return collapsed


# ---------------------------------------------------------------------------
# Absolute URLs
# ---------------------------------------------------------------------------


def absolute_path(path, request=None):
    """Absolute site URL for a site-relative *path* (no query, no fragment)."""
    return f"{origin(request)}{normalize_path(path)}"


def canonical_path(request):
    """The canonical, language-addressed path for the current request."""
    return language_path(request.path, active_language(request))


def canonical_url(request):
    """Absolute canonical URL: the active language version of this page, clean.

    Query strings and fragments are dropped deliberately.  ``/studio/?source=12``
    and ``/studio/`` are the same document — the prefill is a client-side seed for
    the composer, not a distinct page — and canonicalising them apart would let one
    post generate an unbounded number of indexable URLs.
    """
    return absolute_path(canonical_path(request), request)


def hreflang_alternates(request):
    """Reciprocal ``<link rel="alternate">`` descriptors for the current page.

    Built from one shared neutral path, so every language version of a page emits
    the identical set and reciprocity is structural rather than maintained by
    hand.  ``x-default`` points at the default language, which is what a crawler
    with no language signal should be handed.
    """
    neutral = neutral_path(request)
    alternates = [
        {"hreflang": language, "href": absolute_path(language_path(neutral, language), request)}
        for language in LANGUAGES
    ]
    alternates.append(
        {
            "hreflang": "x-default",
            "href": absolute_path(language_path(neutral, DEFAULT_LANGUAGE), request),
        }
    )
    return alternates


def absolute_media_url(url, request=None):
    """Turn a ``FileField`` value or a media path into an absolute URL.

    Open Graph, Twitter Cards and JSON-LD all reject relative image URLs, and
    ``{{ post.image }}`` renders as ``/media/...``.  Absolute URLs are passed
    through untouched, data URIs and fragments are left alone.
    """
    if not url:
        return ""
    url = str(url)
    if url.startswith(("http://", "https://", "//", "data:", "#")):
        return url
    if not url.startswith("/"):
        url = "/" + url
    return f"{media_origin(request)}{url}"


# ---------------------------------------------------------------------------
# Language
# ---------------------------------------------------------------------------


def active_language(request):
    """The language the current request is being rendered in."""
    resolved = getattr(request, "promptya_language", None)
    if resolved in LANGUAGES:
        return resolved
    cookie = request.COOKIES.get(LANG_COOKIE) if request is not None else None
    return cookie if cookie in LANGUAGES else DEFAULT_LANGUAGE


def language_direction(language):
    return "rtl" if language == "fa" else "ltr"


# ---------------------------------------------------------------------------
# Metadata builders
# ---------------------------------------------------------------------------


def clamp(text, limit):
    """Collapse whitespace and clip to *limit* on a word boundary."""
    collapsed = " ".join(str(text or "").split())
    if len(collapsed) <= limit:
        return collapsed
    clipped = collapsed[: max(0, limit - 1)]
    cut = clipped.rfind(" ")
    if cut > limit * 0.6:
        clipped = clipped[:cut]
    return clipped.rstrip(" ,.;:-—") + "…"


def clamp_title(text):
    return clamp(text, TITLE_LIMIT)


def clamp_description(text):
    return clamp(text, DESCRIPTION_LIMIT)


def seo_strings(language):
    """The SEO string table for *language*, falling back to English."""
    return SEO_STRINGS.get(language) or SEO_STRINGS[DEFAULT_LANGUAGE]


# ---------------------------------------------------------------------------
# JSON-LD
# ---------------------------------------------------------------------------


def website_node(request):
    base = absolute_path("/", request)
    return {
        "@type": "WebSite",
        "@id": f"{base}#website",
        "url": f"{base}{DEFAULT_LANGUAGE}/",
        "name": "Promptya",
        "description": seo_strings(active_language(request))["site_description"],
        "inLanguage": list(LANGUAGES),
        "publisher": {"@id": f"{base}#organization"},
        "potentialAction": {
            "@type": "SearchAction",
            "target": {
                "@type": "EntryPoint",
                "urlTemplate": absolute_path(reverse("web:search"), request)
                + "?q={search_term_string}",
            },
            "query-input": "required name=search_term_string",
        },
    }


def organization_node(request):
    base = absolute_path("/", request)
    logo = absolute_media_url(settings.STATIC_URL + "icons/icon-512.png", request)
    return {
        "@type": "Organization",
        "@id": f"{base}#organization",
        "name": "Promptya",
        "url": f"{base}{DEFAULT_LANGUAGE}/",
        "logo": {
            "@type": "ImageObject",
            "url": logo,
            "width": 512,
            "height": 512,
        },
    }


def web_page_node(request, *, name, description, breadcrumb_id=None):
    """The ``WebPage`` shell every page can carry.

    Present on its own it earns nothing; it exists so ``breadcrumb`` and the
    page's own entity (a ``CreativeWork``, a ``ProfilePage``) can be tied together
    by ``@id`` instead of living in unrelated documents.
    """
    canonical = canonical_url(request)
    node = {
        "@type": "WebPage",
        "@id": f"{canonical}#webpage",
        "url": canonical,
        "name": name,
        "description": description,
        "inLanguage": active_language(request),
        "isPartOf": {"@id": f"{absolute_path('/', request)}#website"},
    }
    if breadcrumb_id:
        node["breadcrumb"] = {"@id": breadcrumb_id}
    return node


def breadcrumb_node(request, crumbs):
    """``BreadcrumbList`` from ``[(name, path), …]`` ordered root-first.

    *crumbs* must be built from :func:`language_path` by the caller so the items
    point at the same language versions the current page advertises in its
    ``hreflang`` set.
    """
    return {
        "@type": "BreadcrumbList",
        "@id": f"{canonical_url(request)}#breadcrumb",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": position,
                "name": name,
                "item": absolute_path(path, request),
            }
            for position, (name, path) in enumerate(crumbs, start=1)
        ],
    }


def item_list_node(request, items):
    """``ItemList`` for a listing page.

    Machine-readable internal links from a collection to its members, which is
    the structured-data counterpart of the plain ``<a>`` links the grid already
    renders.  ``items`` are absolute URLs, most prominent first.
    """
    if not items:
        return None
    return {
        "@type": "ItemList",
        "@id": f"{canonical_url(request)}#itemlist",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": position,
                "url": absolute_path(path, request),
            }
            for position, path in enumerate(items, start=1)
        ],
    }


def person_node(request, user, *, with_profile=True):
    """``Person`` for a creator.  Only public profile fields are exposed."""
    profile_path = reverse("web:profile", args=[user.username])
    node = {
        "@type": "Person",
        "@id": f"{absolute_path(profile_path, request)}#person",
        "name": (user.display_name or user.username),
        "url": absolute_path(profile_path, request),
        "identifier": f"@{user.username}",
    }
    if with_profile and user.biography:
        node["description"] = clamp_description(user.biography)
    if user.profile_picture:
        node["image"] = absolute_media_url(user.profile_picture.url, request)
    return node


def fmt_value(template, **values):
    """Substitute ``{name}`` placeholders in an SEO string.

    Unused placeholders are dropped rather than left visible, so a scaffold like
    ``post_fallback_fmt`` degrades to a clean sentence when the author has no
    display name.
    """
    text = str(template or "")
    for key, value in values.items():
        text = text.replace("{" + key + "}", "" if value is None else str(value))
    return clamp(text, TITLE_LIMIT + DESCRIPTION_LIMIT)
