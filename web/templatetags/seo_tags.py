"""Template tags for the search-engine surface of a page.

Deliberately few, and each one exists because doing it by hand in a template was
either wrong or untestable:

``{% seo_jsonld %}``
    Serialises a Python graph through :func:`json.dumps`, so a page can never
    emit malformed JSON-LD.  The previous hand-written blocks assembled JSON with
    inline ``{% if %}`` commas, where one missing comma produced silently invalid
    structured data that nothing in the suite could catch.

``{% seo_hreflang %}`` / ``{% seo_breadcrumbs %}``
    Emit the machine-readable links.  Both are built from one shared
    language-neutral path, which is what makes the hreflang set reciprocal by
    construction instead of by discipline.

``{% seo_image_attrs %}``
    Emits ``width``/``height``/``loading``/``decoding``/``fetchpriority`` from the
    dimensions captured once at upload time, so no render ever opens an image file
    and the LCP image is never lazy-loaded while everything below the fold is.
"""

import json

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

from web import seo

register = template.Library()


# ---------------------------------------------------------------------------
# Structured data
# ---------------------------------------------------------------------------


@register.simple_tag(takes_context=True)
def seo_jsonld(context, *nodes):
    """Render one valid ``application/ld+json`` document from a graph.

    Arguments may be a node, a list of nodes (a view builds a page's whole graph
    at once), or the rendered output of another tag in this library — which is how
    ``{% seo_jsonld seo_jsonld_nodes seo_breadcrumb_jsonld crumbs %}`` composes.
    Composed tags arrive as JSON *text*, so anything parseable is decoded back
    into a node rather than being emitted as a bare string inside ``@graph``.
    Falsy entries are dropped, so a view with no item list to describe can pass
    one without branching in the template.
    """
    graphs = []
    for argument in nodes:
        for node in argument if isinstance(argument, (list, tuple)) else [argument]:
            if not node:
                continue
            if isinstance(node, str):
                try:
                    node = json.loads(node)
                except ValueError:
                    continue
            if isinstance(node, dict):
                graphs.append(node)
    if not graphs:
        return ""
    payload = {"@context": "https://schema.org", "@graph": graphs}
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    # A literal "</script>" inside any value would close the element early.
    body = body.replace("</", "<\\/")
    return mark_safe(  # noqa: S308 - json.dumps output, never user markup
        f'<script type="application/ld+json">{body}</script>'
    )


# ---------------------------------------------------------------------------
# Alternate-language links
# ---------------------------------------------------------------------------


@register.simple_tag(takes_context=True)
def seo_hreflang(context):
    """Reciprocal ``hreflang`` links plus ``x-default`` for the current page."""
    request = context["request"]
    parts = ['<link rel="alternate" hreflang="{}" href="{}">'.format(
        escape(alternate["hreflang"]), escape(alternate["href"])
    ) for alternate in seo.hreflang_alternates(request)]
    return mark_safe("".join(parts))  # noqa: S308 - escaped attribute values only


@register.simple_tag(takes_context=True)
def seo_breadcrumbs(context, crumbs):
    """Visible breadcrumb navigation.

    *crumbs* is a list of ``{"name": ..., "path": ...}`` dicts; the last entry is
    rendered as the current page and is not a link.
    """
    request = context["request"]
    labels = seo.seo_strings(seo.active_language(request))
    items = []
    last = len(crumbs) - 1
    for index, crumb in enumerate(crumbs):
        name = escape(crumb["name"])
        if index == last:
            items.append(
                '<li class="breadcrumb-item is-current" aria-current="page">{}</li>'.format(name)
            )
        else:
            items.append(
                '<li class="breadcrumb-item"><a href="{}">{}</a></li>'.format(
                    escape(crumb["path"]), name
                )
            )
    return mark_safe(  # noqa: S308 - escaped names and reversed URLs only
        '<nav class="breadcrumbs" aria-label="{}"><ol>{}</ol></nav>'.format(
            escape(labels["breadcrumb_label"]), "".join(items)
        )
    )


# ---------------------------------------------------------------------------
# Media
# ---------------------------------------------------------------------------


@register.simple_tag
def seo_image_attrs(width=None, height=None, *, priority=False, sizes=None):
    """``width``/``height``/loading hints for a content image.

    *priority* marks the page's LCP candidate: it is fetched eagerly at high
    priority and never lazy-loaded.  Everything else defers.  Dimensions are
    emitted whenever they are known, which is what keeps the media box from
    reflowing while the file arrives.
    """
    attributes = []
    if width:
        attributes.append(f'width="{int(width)}"')
    if height:
        attributes.append(f'height="{int(height)}"')
    if priority:
        attributes += ['loading="eager"', 'decoding="sync"', 'fetchpriority="high"']
    else:
        attributes += ['loading="lazy"', 'decoding="async"']
    if sizes:
        attributes.append(f'sizes="{escape(sizes)}"')
    return mark_safe(" ".join(attributes))  # noqa: S308 - integers and escaped sizes


@register.simple_tag(takes_context=True)
def abs_media(context, value):
    """Absolute URL for a ``FileField``/media path (``/media/…`` → ``https://…``).

    Open Graph, Twitter Cards and JSON-LD all reject relative image URLs, and
    ``{{ post.image }}`` renders as ``/media/posts/images/x.png``.  Accepts a
    ``FieldFile`` or an already-serialized URL string, so the API serializer
    output works unchanged.
    """
    if not value:
        return ""
    url = getattr(value, "url", None)
    if url is None:
        url = str(value)
    try:
        return seo.absolute_media_url(url, context.get("request"))
    except ValueError:  # an empty FileField raises on .url
        return ""
