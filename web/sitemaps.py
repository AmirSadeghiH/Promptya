"""XML sitemaps for every publicly indexable surface of the site.

Three properties matter here, and each one was wrong before:

**Absolute HTTPS URLs from a fixed origin.**  ``django.contrib.sites`` is not
installed, so Django's sitemap view would have derived the domain *and* the
protocol from the incoming request.  ``get_domain``/``get_protocol`` are
overridden to read ``SITE_URL`` instead, so a crawler connecting over http, or
sending a spoofed ``Host``, cannot produce ``http://`` or off-site entries.

**Only indexable URLs.**  Every ``items()`` filters in SQL, and the static set
lists only pages that are genuinely ``index, follow``.  The previous version
published ``/feed/trending/`` and ``/feed/latest/`` while ``feed.html`` marked
every feed variant ``noindex`` — a sitemap contradicting the site.

**Reciprocal language alternates.**  ``i18n = True`` makes Django build one entry
per (item, language) pair, and ``alternates`` turns that into ``xhtml:link`` tags.
Django activates each language around the ``reverse()`` call, so every
``path_for`` returns the prefixed path for the language being emitted.  Django's
own ``x_default`` handling is switched off (``x_default = False``) because it
rewrites the default language's URL by stripping ``/<lang>/``, which would
advertise the unprefixed path that no page uses as its canonical; ``_urls``
appends the same ``x-default`` entry the pages themselves emit instead.
"""

from collections import namedtuple
from urllib.parse import urlsplit

from django.contrib.sitemaps import Sitemap
from django.db.models import Count, Max, Q
from django.db.models.functions import Length, Trim
from django.urls import reverse

from account.models import CustomUser
from posts.models import Category, Post, Tag
from web import seo

#: Bounded per file so a large post table cannot produce one enormous response.
#: Django pages the rest automatically; 20k keeps each file well inside the
#: 50 MB / 50 000 URL protocol limits with room for per-language alternates.
SITEMAP_PAGE_LIMIT = 20000

#: A static landing page. A namedtuple rather than a bare tuple so the base
#: class can tell it apart from Django's own ``(obj, language)`` pairs.
StaticEntry = namedtuple("StaticEntry", "name args")


class PromptyaSitemap(Sitemap):
    """Shared absolute-URL and bilingual-alternate behaviour for every section."""

    limit = SITEMAP_PAGE_LIMIT
    protocol = "https"

    #: Emit an entry per (item, language) and cross-link them with xhtml:link.
    i18n = True
    alternates = True
    #: Handled in ``_urls`` — Django's own implementation rewrites the default
    #: language's URL by stripping "/<lang>/", which would advertise the
    #: unprefixed path that no page uses as its canonical.
    x_default = False

    def get_domain(self, site=None):
        """``SITE_URL``'s host, ignoring the request entirely."""
        origin = seo.site_origin()
        if not origin:
            # Development / tests with no SITE_URL: fall back to Django's
            # request-derived behaviour rather than emitting a broken <loc>.
            return super().get_domain(site)
        return urlsplit(origin).netloc

    def get_protocol(self, protocol=None):
        """Always https, even when the sitemap was fetched over http."""
        return "https"

    def get_languages_for_item(self, item):
        """Both languages, default first, so ``<loc>`` is the default version."""
        return list(seo.LANGUAGES)

    def path_for(self, obj):  # pragma: no cover - overridden by each section
        raise NotImplementedError

    def location(self, obj):
        """Site-relative URL of *obj* in the language Django activated for it.

        ``Sitemap._location`` unpacks its ``(obj, language)`` tuples and wraps
        this call in ``translation.override(language)`` before handing over the
        bare object, so ``reverse()`` — which reads the active language out of
        ``i18n_patterns`` — already produces the right prefix.  Prefixing by hand
        here would produce ``/fa/fa/…``.
        """
        return self.path_for(obj)

    def _urls(self, page, protocol, domain):
        """Append the ``x-default`` alternate that the HTML pages also emit."""
        urls = super()._urls(page, protocol, domain)
        for url_info in urls:
            default = next(
                (
                    alternate
                    for alternate in url_info["alternates"]
                    if alternate["lang_code"] == seo.DEFAULT_LANGUAGE
                ),
                None,
            )
            if default is not None:
                url_info["alternates"].append(
                    {"location": default["location"], "lang_code": "x-default"}
                )
        return urls


def _published_posts():
    """Posts satisfying the model's public indexability rule, in SQL.

    Keep this predicate in lockstep with Post.is_indexable: a non-blank
    title and either meaningful text (20+ characters in description or prompt)
    or an actual uploaded media file. This prevents thin posts from entering
    the sitemap even though their detail view correctly sends noindex.
    """
    return (
        Post.objects.annotate(
            seo_title=Trim("title"),
            seo_description_length=Length("description"),
            seo_prompt_length=Length("prompt"),
        )
        .filter(~Q(seo_title=""))
        .filter(
            Q(seo_description_length__gte=Post.MIN_MEANINGFUL_LENGTH)
            | Q(seo_prompt_length__gte=Post.MIN_MEANINGFUL_LENGTH)
            | (Q(image__isnull=False) & ~Q(image=""))
            | (Q(video__isnull=False) & ~Q(video=""))
            | (Q(audio__isnull=False) & ~Q(audio=""))
        )
    )

class PostSitemap(PromptyaSitemap):
    """Every public post worth a result."""

    priority = 0.9
    changefreq = "weekly"

    def items(self):
        return _published_posts().only("id", "slug", "updated_at").order_by("-created_at")

    def lastmod(self, obj):
        return obj.updated_at

    def path_for(self, obj):
        return reverse("web:post-detail", args=[obj.slug])


class ProfileSitemap(PromptyaSitemap):
    """Creator profiles that actually have public content.

    Previously every active account was listed, so each registered-but-silent
    account contributed an empty page to the index.  Now only accounts with at
    least one post qualify, matching ``CustomUser.is_indexable``.
    """

    priority = 0.6
    changefreq = "weekly"

    def items(self):
        return (
            CustomUser.objects.filter(is_active=True)
            # Aliased `seo_post_count`, not `public_post_count`: that name is a
            # property on the model, and annotating over it makes Django try to
            # assign to a read-only attribute.
            .annotate(seo_post_count=Count("posts", distinct=True))
            .filter(seo_post_count__gte=1)
            .only("id", "username", "updated_at")
            .order_by("username")
        )

    def lastmod(self, obj):
        return obj.updated_at

    def path_for(self, obj):
        return reverse("web:profile", args=[obj.username])


class CollectionSitemap(PromptyaSitemap):
    """Shared behaviour for the category and tag hubs.

    ``lastmod`` is the newest post's ``updated_at``, not the hub row's
    ``created_at``: a category's creation date never changes, so the old value
    told crawlers a hub was untouched no matter how much had been added to it.
    """

    priority = 0.7
    changefreq = "weekly"

    def items(self):
        return (
            self.model.objects.annotate(
                # Aliased for the same reason as ProfileSitemap.items: the
                # models expose `public_post_count` as a read-only property, and
                # a queryset annotation may not shadow it.
                seo_post_count=Count("posts", distinct=True),
                last_post_at=Max("posts__updated_at"),
            )
            .filter(seo_post_count__gte=self.minimum_items)
            .only(*self.only_fields)
            .order_by("slug")
        )

    def lastmod(self, obj):
        # Every item in these sections has at least one post, so `last_post_at` is
        # always populated. There is no hub-row timestamp to fall back to: a
        # category's creation date never changes, which is exactly why it was a
        # misleading lastmod before.
        return obj.last_post_at


class CategorySitemap(CollectionSitemap):
    """Category hubs holding at least one post."""

    model = Category
    minimum_items = 1
    only_fields = ("id", "slug")
    priority = 0.7

    def path_for(self, obj):
        return reverse("web:category", args=[obj.slug])


class TagSitemap(CollectionSitemap):
    """Tag hubs with enough depth to be a result rather than a duplicate.

    One post behind a tag is that post's page with a thinner title, so a tag needs
    ``MIN_INDEXABLE_COLLECTION_ITEMS`` before it is worth indexing.  The same
    threshold drives the page's robots directive, so the two cannot disagree.
    """

    model = Tag
    minimum_items = seo.MIN_INDEXABLE_COLLECTION_ITEMS
    only_fields = ("id", "slug")
    priority = 0.5

    def path_for(self, obj):
        return reverse("web:tag", args=[obj.slug])


class StaticViewSitemap(PromptyaSitemap):
    """The handful of non-parameterised entry points worth crawling.

    Only pages that are ``index, follow`` in their own template.  The feed
    variants used to be listed here while ``feed.html`` marked them ``noindex``;
    they are deliberately absent now, and ``/search/`` never belonged here
    because every one of its URLs is a thin duplicate of the bare page.
    """

    priority = 0.8
    changefreq = "daily"

    _entries = (
        StaticEntry("web:home", ()),
        StaticEntry("web:explore", ()),
        StaticEntry("web:studio", ()),
    )

    def items(self):
        return self._entries

    def path_for(self, entry):
        return reverse(entry.name, args=entry.args)


SITEMAPS = {
    "posts": PostSitemap,
    "profiles": ProfileSitemap,
    "categories": CategorySitemap,
    "tags": TagSitemap,
    "static": StaticViewSitemap,
}
