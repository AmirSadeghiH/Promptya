"""Template filters for i18n string formatting."""

import re

from django import template

register = template.Library()

#: ``{n}``, ``{query}``, ``{count}``, ``{name}``, ``{tag}``, ``{title}``,
#: ``{author}``, ``{username}``, ``{type}`` — every placeholder the UI and SEO
#: string tables use.  Matched generically rather than listed one by one: a
#: template that renders ``{count}`` through a filter that only knows ``{n}``
#: fails silently, printing the literal placeholder to the reader.
PLACEHOLDER = re.compile(r"\{[a-z_]+\}")


@register.filter
def fmt(value, args):
    """Replace ``{placeholder}`` tokens in a UI string with a value.

    Every placeholder is replaced, not just the first: SEO listing strings are
    reused with different arguments across templates, and a filter that honoured
    only ``{n}`` would leak ``{count}`` straight into a rendered page.
    """
    text = str(value or "")
    return PLACEHOLDER.sub(lambda match: str(args), text)


@register.filter
def get(mapping, key):
    """Look a string key up in a dict from inside a template.

    Django's ``{{ d.key }}`` cannot index by a loop variable, which the i18n
    catalogs need (one dict, many keys).
    """
    if not mapping:
        return ""
    try:
        return mapping.get(key, "")
    except AttributeError:
        return ""


@register.filter
def file_url(value):
    """URL for a FileField/FieldFile, or a URL string passed straight through.

    Reads on an empty FileField raise ValueError. Plain ``{{ x }}`` output
    swallows that, but extra context inside an include tag does not — so
    touching ``field.url`` on a user with no avatar returned a 500 instead of
    falling back to the initial-letter avatar. Returning "" for "no file"
    fixes the whole class of bug at one place, and accepting a string keeps
    the API serializers (which already emit URLs) working unchanged.
    """
    if not value:
        return ""
    url = getattr(value, "url", None)
    if url is None:
        return str(value)
    try:
        return str(url)
    except (ValueError, AttributeError):
        return ""
