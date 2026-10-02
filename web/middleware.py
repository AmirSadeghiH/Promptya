"""Request-level SEO plumbing: canonical origin and language resolution.

Both run early in the chain and both are deliberately small, because each one
exists to stop a class of bug rather than to add a feature:

``CanonicalHostMiddleware``
    One origin, reached by a single 301.  Without it the site happily serves
    ``http://``, ``www.`` and any ``Host`` a client invents, and every one of
    those becomes a separate crawlable address with its own canonical tag.

``LanguageMiddleware``
    Decides the render language from the URL first and the cookie second, and
    activates it *before* URL resolution.  Django's URL resolver only knows a
    language-prefixed path is valid when the active language matches the prefix,
    so this has to run before the view stage.  It replaces ``LocaleMiddleware``,
    which would have keyed off ``Accept-Language`` and a Django-owned cookie that
    the site does not use.
"""

from urllib.parse import urlsplit, urlunsplit

from django.http import HttpResponsePermanentRedirect
from django.utils import translation

from web.i18n_strings import LANG_COOKIE
from web.seo import DEFAULT_LANGUAGE, LANGUAGES, site_origin, split_language_prefix

#: A year, matching static/js/i18n.js.  The cookie only carries a UI preference
#: for unprefixed URLs; the URL is what search engines read.
LANG_COOKIE_MAX_AGE = 60 * 60 * 24 * 365


class CanonicalHostMiddleware:
    """301 requests for a non-canonical scheme or host onto ``SITE_URL``.

    Inert when ``SITE_URL`` is unset (development, tests), which is what keeps
    ``runserver`` on ``127.0.0.1:8000`` working.  Only safe methods are
    redirected: replaying a 301'd POST as a GET would silently drop a publish.

    The redirect preserves path *and* query string, so a shared ``/studio/?source=12``
    link keeps working, and it is a single hop — ``/post/1`` becomes
    ``/post/1/`` and stops, never a chain.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        target = self._canonical_url(request)
        if target is not None:
            return HttpResponsePermanentRedirect(target)
        return self.get_response(request)

    def _canonical_url(self, request):
        if request.method not in ("GET", "HEAD"):
            return None
        origin = site_origin()
        if not origin:
            return None
        wanted = urlsplit(origin)
        if request.scheme == wanted.scheme and request.get_host() == wanted.netloc:
            return None
        return urlunsplit(
            (
                wanted.scheme,
                wanted.netloc,
                request.path,
                request.META.get("QUERY_STRING", ""),
                "",
            )
        )


class LanguageMiddleware:
    """Resolve and activate the render language for every request.

    Resolution order — the URL wins, always:

    1. an explicit ``/fa`` or ``/en`` path segment,
    2. the ``promptya-lang`` cookie,
    3. :data:`DEFAULT_LANGUAGE`.

    A prefixed request also refreshes the cookie, so a visitor who arrived on
    ``/fa/…`` keeps Persian when they follow an unprefixed link from elsewhere
    on the web.  This does not reintroduce the original problem: canonical tags
    for unprefixed URLs always point at a language-prefixed address, so the
    cookie only ever affects *which* language version is offered, never whether
    a page is indexable.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        prefix, _ = split_language_prefix(request.path)
        language = prefix or self._from_cookie(request) or DEFAULT_LANGUAGE

        request.promptya_language = language
        request.LANGUAGE_CODE = language
        translation.activate(language)
        try:
            response = self.get_response(request)
        finally:
            translation.deactivate()

        if prefix and request.COOKIES.get(LANG_COOKIE) != language:
            response.set_cookie(
                LANG_COOKIE,
                language,
                max_age=LANG_COOKIE_MAX_AGE,
                samesite="Lax",
                path="/",
            )
        return response

    @staticmethod
    def _from_cookie(request):
        stored = request.COOKIES.get(LANG_COOKIE)
        return stored if stored in LANGUAGES else None


def noindex(directives="noindex, follow"):
    """Mark a view's response ``X-Robots-Tag`` so ``noindex`` is not meta-only.

    A ``<meta name="robots">`` tag is a request to a cooperative crawler.  The
    header is the same instruction in the one place a proxy or a non-conforming
    agent cannot miss, and it survives a template refactor that forgets to
    override a block.  Private pages get both.
    """

    def decorator(view):
        def wrapper(request, *args, **kwargs):
            response = view(request, *args, **kwargs)
            response.headers["X-Robots-Tag"] = directives
            return response

        wrapper.__name__ = getattr(view, "__name__", "view")
        wrapper.__doc__ = view.__doc__
        wrapper.__module__ = view.__module__
        return wrapper

    return decorator


def mark_noindex(response, directives="noindex, follow"):
    """Set ``X-Robots-Tag`` on an already-rendered response (conditional pages)."""
    response.headers["X-Robots-Tag"] = directives
    return response
