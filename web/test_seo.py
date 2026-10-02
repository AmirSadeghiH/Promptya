"""Tests for the search-engine surface.

Split by *what could break* rather than by function:

``UrlStrategyTests``      the bilingual URL contract — prefixed pages, unprefixed
                          aliases, canonicals, hreflang reciprocity, and the
                          ``Host``-header proof.
``RobotsDirectiveTests``  what is indexable and what is not, including the thin
                          collection rules.
``PaginationTests``       whether a crawler can reach page 2+ of a listing.
``StructuredDataTests``   the JSON-LD graph, asserted by parsing the rendered
                          ``<script>`` rather than by string-matching the page.
``MetadataTests``         titles, descriptions, and Open Graph.
``SitemapTests``          the sitemap advertising exactly the indexable set.
``CrawlerDocumentTests``  ``robots.txt`` and ``sitemap.xml`` themselves.
``SeoStringTests``        the two languages staying parallel.

Everything here asserts on a parsed structure — an element, a JSON document, a
header — rather than on a substring of the whole page.  A test that passes on a
happily-formatted page and fails after a reformat teaches the team to reformat
the test instead of the behaviour.
"""

import json
import re

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from posts.models import MIN_INDEXABLE_COLLECTION_ITEMS, Category, Post, Tag
from web import seo
from web.i18n_strings import LANG_COOKIE, SEO_STRINGS

#: The test client's own host, so ``CanonicalHostMiddleware`` is inert by default
#: and absolute URLs are assertable.  Tests that exercise the redirect send a
#: different ``Host`` explicitly, which is the only way to provoke it.
ORIGIN = "https://testserver"


def _tag(name):
    return Tag.objects.create(name=name, slug=name.lower())


def _post(author, category, title="A cinematic prompt", *, tags=(), **kwargs):
    kwargs.setdefault("prompt", "A hand-built prompt about light and lens")
    post = Post.objects.create(
        author=author,
        category=category,
        post_type=Post.PostType.PROMPT,
        title=title,
        **kwargs,
    )
    if tags:
        post.tags.set(tags)
    return post


def _canonical(html):
    match = re.search(r'<link rel="canonical" href="([^"]+)"', html)
    return match.group(1) if match else None


def _meta(html, name):
    match = re.search(r'<meta name="%s" content="([^"]+)"' % name, html)
    return match.group(1) if match else None


def _property(html, name):
    match = re.search(r'<meta property="%s" content="([^"]+)"' % name, html)
    return match.group(1) if match else None


def _title(html):
    return re.search(r"<title>(.*?)</title>", html, re.DOTALL).group(1)


def _hreflangs(html):
    return {
        lang: url
        for lang, url in re.findall(
            r'<link rel="alternate" hreflang="([^"]+)" href="([^"]+)"', html
        )
    }


def _ld_json(html):
    """Every JSON-LD document on the page, merged into one flat list of nodes."""
    graph = []
    for block in re.findall(
        r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL
    ):
        payload = json.loads(block)
        graph.extend(payload.get("@graph", [payload]))
    return graph


def _types(html):
    return [node.get("@type") for node in _ld_json(html)]


def _node(html, node_type):
    return next((node for node in _ld_json(html) if node.get("@type") == node_type), None)


@override_settings(SITE_URL=ORIGIN)
class SeoTestCase(TestCase):
    """Shared fixtures and a request helper that speaks https.

    ``secure=True`` is not optional here.  ``CanonicalHostMiddleware`` 301s every
    plain-http request onto ``SITE_URL``, which is exactly the behaviour under
    test — so a test that forgets it asserts against an empty redirect body and
    reports a failure that looks like a template bug.
    """

    @classmethod
    def setUpTestData(cls):
        cls.author = get_user_model().objects.create_user(
            username="creator", email="creator@example.com", password="test-password"
        )
        cls.silent = get_user_model().objects.create_user(
            username="silent", email="silent@example.com", password="test-password"
        )
        cls.category = Category.objects.create(name="Photography", slug="photography")
        cls.empty_category = Category.objects.create(name="Empty", slug="empty")
        cls.post = _post(cls.author, cls.category, "Neon rain, 35mm")
        cls.tag = _tag("neon")
        cls.post.tags.add(cls.tag)

    def fetch(self, url, **kwargs):
        kwargs.setdefault("secure", True)
        return self.client.get(url, **kwargs)

    def robots_header(self, url, **kwargs):
        """The ``X-Robots-Tag`` value, or "" when the page is indexable.

        An indexable page carries no header at all, so this cannot use ``[]``:
        the absence of the header *is* the indexable state.
        """
        return self.fetch(url, **kwargs).headers.get("X-Robots-Tag", "")

    def get(self, url, **kwargs):
        """GET *url* and return the body, asserting a 200."""
        response = self.fetch(url, **kwargs)
        self.assertEqual(response.status_code, 200, url)
        return response.content.decode()


# ---------------------------------------------------------------------------
# URL strategy
# ---------------------------------------------------------------------------


class UrlStrategyTests(SeoTestCase):
    def test_prefixed_pages_are_the_canonical_addresses(self):
        for url in ("/en/", "/fa/", "/en/explore/", "/fa/explore/"):
            with self.subTest(url=url):
                self.assertEqual(_canonical(self.get(url)), f"{ORIGIN}{url}")

    def test_unprefixed_aliases_resolve_without_redirecting(self):
        # 200, not 301: the PWA start_url, the service-worker offline precache
        # and every shared link depend on these addresses staying put.
        for url in ("/", "/explore/", "/studio/", "/search/"):
            with self.subTest(url=url):
                self.assertEqual(self.fetch(url).status_code, 200)

    def test_unprefixed_canonicalises_to_the_language_version(self):
        self.assertEqual(_canonical(self.get("/")), f"{ORIGIN}/en/")

    def test_cookie_selects_the_language_version_of_an_unprefixed_url(self):
        self.client.cookies[LANG_COOKIE] = "fa"
        self.assertEqual(_canonical(self.get("/")), f"{ORIGIN}/fa/")

    def test_a_prefix_beats_the_cookie(self):
        # The URL is what a crawler reads and what a reader bookmarked; the cookie
        # must never override it.
        self.client.cookies[LANG_COOKIE] = "fa"
        self.assertEqual(_canonical(self.get("/en/")), f"{ORIGIN}/en/")

    def test_hreflang_set_is_identical_in_both_languages(self):
        english = _hreflangs(self.get("/en/explore/"))
        persian = _hreflangs(self.get("/fa/explore/"))
        self.assertEqual(english, persian)
        self.assertEqual(english["en"], f"{ORIGIN}/en/explore/")
        self.assertEqual(english["fa"], f"{ORIGIN}/fa/explore/")
        self.assertEqual(english["x-default"], f"{ORIGIN}/en/explore/")

    def test_hreflang_reciprocity_holds_for_a_post(self):
        english = _hreflangs(self.get(f"/en/post/{self.post.pk}/"))
        persian = _hreflangs(self.get(f"/fa/post/{self.post.pk}/"))
        self.assertEqual(english, persian)
        self.assertEqual(english["en"], f"{ORIGIN}/en/post/{self.post.pk}/")
        self.assertEqual(english["fa"], f"{ORIGIN}/fa/post/{self.post.pk}/")

    def test_canonical_drops_the_query_string(self):
        # /studio/?source=12 and /studio/ are one document; without this, one post
        # would mint an unbounded number of indexable URLs.
        self.assertEqual(
            _canonical(self.get("/en/studio/?source=12")), f"{ORIGIN}/en/studio/"
        )

    def test_absolute_urls_ignore_a_spoofed_host_header(self):
        response = self.fetch("/en/", headers={"host": "attacker.example"})
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], f"{ORIGIN}/en/")

    def test_http_is_redirected_once_to_the_canonical_origin(self):
        response = self.client.get("/en/")
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], f"{ORIGIN}/en/")

    def test_canonical_host_redirect_preserves_the_query_string(self):
        response = self.fetch(
            "/en/studio/?source=12", headers={"host": "attacker.example"}
        )
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], f"{ORIGIN}/en/studio/?source=12")

    def test_a_post_is_not_redirected_away(self):
        # A canonical-host redirect that also rewrote the path would break every
        # shared post link; only the origin is ever touched.
        response = self.fetch(
            f"/en/post/{self.post.pk}/", headers={"host": "attacker.example"}
        )
        self.assertEqual(response["Location"], f"{ORIGIN}/en/post/{self.post.pk}/")

    def test_page_out_of_range_is_404_not_an_empty_200(self):
        # An empty listing at a valid-looking URL is the soft-404 pattern that
        # gets whole sections de-indexed.
        self.assertEqual(self.fetch("/en/category/photography/?page=99").status_code, 404)

    def test_invalid_page_number_is_404(self):
        self.assertEqual(self.fetch("/en/category/photography/?page=abc").status_code, 404)

    def test_unknown_feed_variant_is_404(self):
        self.assertEqual(self.fetch("/en/feed/nonsense/").status_code, 404)

    def test_pages_still_work_without_a_site_url(self):
        # runserver has no SITE_URL; the page must render, falling back to the
        # request origin rather than emitting a bare "/en/".
        with override_settings(SITE_URL=""):
            html = self.get("/en/")
        self.assertIn("/en/", _canonical(html))


# ---------------------------------------------------------------------------
# Indexability
# ---------------------------------------------------------------------------


class RobotsDirectiveTests(SeoTestCase):
    def test_public_pages_are_indexable(self):
        for url in ("/en/", "/fa/", "/en/explore/", "/en/studio/"):
            with self.subTest(url=url):
                html = self.get(url)
                self.assertTrue(_meta(html, "robots").startswith("index, follow"))
                self.assertEqual(self.robots_header(url), "")

    def test_private_and_per_account_pages_are_noindex_in_the_header_too(self):
        self.client.force_login(self.author)
        for url in (
            "/en/search/?q=light",
            "/en/saved/",
            "/en/notifications/",
            "/en/settings/profile/",
            "/en/create/",
        ):
            with self.subTest(url=url):
                response = self.fetch(url)
                self.assertIn("noindex", response["X-Robots-Tag"])
                self.assertIn("noindex", _meta(response.content.decode(), "robots"))

    def test_feed_variants_are_noindex(self):
        # "following" is personalised; "latest" and "trending" duplicate surfaces
        # that are themselves indexed.
        for feed in ("latest", "trending"):
            with self.subTest(feed=feed):
                self.assertIn("noindex", self.robots_header(f"/en/feed/{feed}/"))

    def test_the_following_feed_redirects_anonymous_visitors_to_login(self):
        response = self.fetch("/en/feed/following/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

    def test_a_tag_with_one_post_is_noindex(self):
        lonely = _tag("lonely")
        _post(self.author, self.category, "Only one", tags=[lonely])
        response = self.fetch("/en/tag/lonely/")
        self.assertIn("noindex", response["X-Robots-Tag"])
        self.assertIn("noindex", _meta(response.content.decode(), "robots"))

    def test_a_tag_at_the_depth_threshold_is_indexable(self):
        for index in range(MIN_INDEXABLE_COLLECTION_ITEMS):
            _post(self.author, self.category, f"Deep {index}", tags=[self.tag])
        self.assertEqual(self.robots_header("/en/tag/neon/"), "")
        self.assertTrue(
            _meta(self.get("/en/tag/neon/"), "robots").startswith("index, follow")
        )

    def test_a_creator_with_no_posts_is_noindex_but_still_reachable(self):
        response = self.fetch("/en/profile/silent/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("noindex", response["X-Robots-Tag"])

    def test_an_empty_category_is_noindex(self):
        self.assertIn("noindex", self.robots_header("/en/category/empty/"))

    def test_a_post_with_neither_text_nor_media_is_noindex(self):
        bare = Post.objects.create(
            author=self.author,
            category=self.category,
            post_type=Post.PostType.PROMPT,
            title="Nothing but a title",
        )
        self.assertIn("noindex", self.robots_header(f"/en/post/{bare.pk}/"))

    def test_a_post_with_only_a_prompt_is_indexable(self):
        self.assertEqual(self.robots_header(f"/en/post/{self.post.pk}/"), "")

    def test_the_studio_is_indexable_only_for_anonymous_visitors(self):
        self.assertTrue(
            _meta(self.get("/en/studio/"), "robots").startswith("index, follow")
        )

        # A signed-in visitor additionally gets their own generations and credit
        # balance on the same URL, so that response must not enter the index.
        self.client.force_login(self.author)
        self.assertIn("noindex", self.robots_header("/en/studio/"))

    def test_a_prefilled_studio_is_noindex(self):
        self.assertIn("noindex", self.robots_header(f"/en/studio/?source={self.post.pk}"))


# ---------------------------------------------------------------------------
# Crawlability of the listing surfaces
# ---------------------------------------------------------------------------


class PaginationTests(SeoTestCase):
    def _fill(self, count=30):
        for index in range(count):
            _post(self.author, self.category, f"Filler {index:02d}")

    def test_a_listing_offers_a_real_link_to_page_two(self):
        self._fill()
        html = self.get("/en/category/photography/")
        self.assertIn('href="?page=2"', html)

<<<<<<< ours
=======
    def test_an_offset_listing_offers_the_anchor_and_not_the_js_sentinel(self):
        # Category, tag and profile listings are offset-paginated: page 2 is a real
        # URL, so it gets a real <a> for a non-JS crawler. They deliberately carry
        # no .load-more sentinel — app.js enhances a listing only when that is
        # present, and rendering it as well would be claiming an infinite scroll
        # the cursor-paginated endpoint behind it does not serve.
        self._fill()
        html = self.get("/en/category/photography/")
        self.assertIn('class="pagination"', html)
        self.assertNotIn('class="load-more"', html)

    def test_a_cursor_listing_offers_the_sentinel_and_not_a_bare_link(self):
        # The home/feeds are cursor-paginated, so they get infinite scroll. There
        # is no ?page=2 to link to, and printing one anyway would be a link to a
        # URL that 404s. Needs more than one page of posts for a cursor to exist.
        self._fill(count=40)
        html = self.get("/en/feed/trending/")
        self.assertIn('class="load-more"', html)
        self.assertNotIn('class="pagination"', html)

    def test_the_offset_anchor_carries_no_cursor_for_app_js_to_follow(self):
        # app.js pages by data-next-cursor; on an offset surface that attribute
        # must be absent rather than present-and-empty, so the "enhance me" branch
        # cannot fire on a listing with no cursor endpoint behind it.
        self._fill()
        html = self.get("/en/category/photography/")
        self.assertIn('href="?page=2"', html)
        self.assertNotIn("data-next-cursor", html)

>>>>>>> theirs
    def test_page_two_is_reachable(self):
        self._fill()
        self.assertIn("Filler", self.get("/en/category/photography/?page=2"))

    def test_every_page_of_a_listing_canonicalises_to_page_one(self):
        # Page 2+ is the same document as page 1 of the same listing; letting them
        # compete would split the listing's own relevance across its pages.
        self._fill()
        for page in ("1", "2"):
            with self.subTest(page=page):
                self.assertEqual(
                    _canonical(self.get(f"/en/category/photography/?page={page}")),
                    f"{ORIGIN}/en/category/photography/",
                )

    def test_the_last_page_offers_no_next_link(self):
        self.assertNotIn('href="?page=', self.get("/en/category/photography/"))

    def test_a_profile_with_more_posts_than_one_page_paginates(self):
        self._fill()
        self.assertIn('href="?page=2"', self.get("/en/profile/creator/"))

    def test_tags_are_links_not_inert_text(self):
        # Tags used to be visible <span>s, which made the whole tag dimension of
        # the site invisible to a crawler.
        html = self.get(f"/en/post/{self.post.pk}/")
        self.assertIn(f'href="/en/tag/{self.tag.slug}/"', html)
        self.assertIn('rel="tag"', html)

    def test_a_post_links_to_its_category_and_creator(self):
        html = self.get(f"/en/post/{self.post.pk}/")
        self.assertIn("/en/category/photography/", html)
        self.assertIn("/en/profile/creator/", html)

    def test_the_home_page_links_out_without_javascript(self):
        # A crawlable internal-link spine: categories, Explore and the Studio are
        # all reachable from the first page as plain anchors.
        html = self.get("/en/")
        self.assertIn("/en/explore/", html)
        self.assertIn("/en/category/photography/", html)

    def test_a_category_links_to_the_other_categories(self):
        Category.objects.create(name="Writing", slug="writing")
        html = self.get("/en/category/photography/")
        self.assertIn("/en/category/writing/", html)


# ---------------------------------------------------------------------------
# Structured data
# ---------------------------------------------------------------------------


class StructuredDataTests(SeoTestCase):
    def test_every_page_carries_the_site_entities(self):
        types = _types(self.get("/en/"))
        self.assertIn("WebSite", types)
        self.assertIn("Organization", types)

    def test_the_graph_is_split_into_page_and_entity_documents(self):
        # A separate <script> per concern is fine; what matters is that each is
        # valid JSON with a declared @context, so a post's CreativeWork and the
        # site it belongs to can be tied together by @id.
        html = self.get(f"/en/post/{self.post.pk}/")
        blocks = re.findall(
            r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL
        )
        self.assertGreaterEqual(len(blocks), 2)
        for block in blocks:
            with self.subTest(block=block[:40]):
                self.assertEqual(json.loads(block)["@context"], "https://schema.org")

    def test_a_post_page_describes_its_own_work(self):
        work = _node(self.get(f"/en/post/{self.post.pk}/"), "CreativeWork")
        self.assertEqual(work["@id"], f"{ORIGIN}/en/post/{self.post.pk}/#creativework")
        self.assertEqual(work["headline"], "Neon rain, 35mm")
        self.assertEqual(work["datePublished"], self.post.created_at.isoformat())
        self.assertEqual(work["url"], f"{ORIGIN}/en/post/{self.post.pk}/")

    def test_engagement_counts_appear_only_when_the_page_shows_them(self):
        # No likes and no comments: claiming an InteractionCounter of zero would
        # assert engagement the visible page does not display.
        work = _node(self.get(f"/en/post/{self.post.pk}/"), "CreativeWork")
        self.assertNotIn("interactionStatistic", work)

    def test_engagement_counts_are_reported_once_they_exist(self):
        from interactions.models import Comment, Like

        Like.objects.create(user=self.author, post=self.post)
        Comment.objects.create(user=self.author, post=self.post, content="Useful")
        work = _node(self.get(f"/en/post/{self.post.pk}/"), "CreativeWork")
        counts = {
            stat["interactionType"].rsplit("/", 1)[-1]: stat["userInteractionCount"]
            for stat in work["interactionStatistic"]
        }
        self.assertEqual(counts, {"LikeAction": 1, "CommentAction": 1})

    def test_no_review_or_rating_is_invented(self):
        # Promptya has no rating system. Claiming one in structured data is a
        # manual-action risk, so the property is absent rather than zeroed.
        html = self.get(f"/en/post/{self.post.pk}/")
        self.assertNotIn("aggregateRating", html)
        self.assertNotIn("Review", _types(html))

    def test_the_author_is_a_person_tied_to_the_author_node(self):
        html = self.get(f"/en/post/{self.post.pk}/")
        work = _node(html, "CreativeWork")
        self.assertEqual(work["author"]["@id"], f"{ORIGIN}/en/profile/creator/#person")
        self.assertEqual(_node(html, "Person")["@id"], f"{ORIGIN}/en/profile/creator/#person")

    def test_a_profile_page_is_a_profile_page_about_a_person(self):
        html = self.get("/en/profile/creator/")
        page = _node(html, "ProfilePage")
        self.assertEqual(page["mainEntity"], {"@id": f"{ORIGIN}/en/profile/creator/#person"})

    def test_breadcrumbs_are_structured_and_match_the_visible_trail(self):
        html = self.get(f"/en/post/{self.post.pk}/")
        trail = _node(html, "BreadcrumbList")
        self.assertIsNotNone(trail)
        self.assertEqual(trail["@id"], f"{ORIGIN}/en/post/{self.post.pk}/#breadcrumb")
        last = trail["itemListElement"][-1]
        self.assertEqual(last["position"], 4)
        self.assertEqual(last["item"], f"{ORIGIN}/en/post/{self.post.pk}/")
        # The last crumb is rendered as plain text, not as a link to itself.
        self.assertIn('aria-current="page"', html)

    def test_a_breadcrumb_is_a_single_json_document(self):
        # Django's urlize/split would let a per-entity href disagree with the
        # visible trail; both come from the same `crumbs` list in the view.
        html = self.get(f"/fa/post/{self.post.pk}/")
        for crumb in _node(html, "BreadcrumbList")["itemListElement"]:
            with self.subTest(position=crumb["position"]):
                self.assertTrue(crumb["item"].startswith(f"{ORIGIN}/fa/"), crumb["item"])

    def test_a_category_page_lists_its_members(self):
        html = self.get("/en/category/photography/")
        self.assertIn("CollectionPage", _types(html))
        items = _node(html, "ItemList")
        self.assertEqual(
            items["itemListElement"][0]["url"], f"{ORIGIN}/en/post/{self.post.pk}/"
        )

    def test_a_title_containing_a_script_tag_cannot_break_out_of_the_json(self):
        nasty = _post(self.author, self.category, "Ha </script><script>alert(1)</script>")
        html = self.get(f"/en/post/{nasty.pk}/")
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertEqual(_node(html, "CreativeWork")["headline"], nasty.title)

    def test_persian_pages_declare_persian_structured_data(self):
        html = self.get(f"/fa/post/{self.post.pk}/")
        self.assertEqual(_node(html, "CreativeWork")["inLanguage"], "fa")

    def test_the_website_search_action_points_at_the_search_page(self):
        node = _node(self.get("/en/"), "WebSite")
        self.assertTrue(
            node["potentialAction"]["target"]["urlTemplate"].startswith(
                f"{ORIGIN}/en/search/?q="
            )
        )


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


class MetadataTests(SeoTestCase):
    def test_a_post_title_is_built_from_the_authors_own_words(self):
        title = _title(self.get(f"/en/post/{self.post.pk}/"))
        self.assertIn("Neon rain, 35mm", title)
        self.assertIn("@creator", title)

    def test_titles_and_descriptions_stay_within_their_budgets(self):
        long_post = _post(self.author, self.category, "T" * 400, description="D" * 900)
        html = self.get(f"/en/post/{long_post.pk}/")
        self.assertLessEqual(len(_title(html)), seo.TITLE_LIMIT)
        self.assertLessEqual(len(_meta(html, "description")), seo.DESCRIPTION_LIMIT)

    def test_every_page_has_a_non_empty_title_and_description(self):
        for url in ("/en/", "/fa/", "/en/explore/", "/en/studio/", "/en/search/"):
            with self.subTest(url=url):
                html = self.get(url)
                self.assertTrue(_title(html).strip())
                self.assertTrue(_meta(html, "description").strip())

    def test_og_image_is_absolute(self):
        image = _property(self.get(f"/en/post/{self.post.pk}/"), "og:image")
        self.assertTrue(image.startswith("https://"), image)

<<<<<<< ours
=======
    def test_the_fallback_social_image_is_a_real_url_on_every_page(self):
        # This post has no image, so it takes the site-icon fallback. That fallback
        # used to render as
        #   https://host/<WSGIRequest: GET '/…'>/static/icons/icon-512.png
        # because the template asked abs_media to absolutise the request instead of
        # the static path, and the previous assertion — startswith("https://") —
        # happily accepted it. Assert the shape, not just the scheme.
        for url in ("/en/", "/en/explore/", "/en/feed/trending/", "/en/search/"):
            with self.subTest(url=url):
                html = self.get(url)
                # og:* is a property, twitter:* is a name.
                self.assertEqual(_property(html, "og:image"), f"{ORIGIN}/static/icons/icon-512.png")
                self.assertEqual(_meta(html, "twitter:image"), f"{ORIGIN}/static/icons/icon-512.png")

    def test_no_meta_tag_leaks_a_python_repr_into_a_url(self):
        # A general guard: any URL-bearing meta must be a parseable absolute URL,
        # so a mis-passed object in a tag cannot masquerade as one.
        for url in ("/en/", "/en/explore/", f"/en/post/{self.post.pk}/"):
            with self.subTest(url=url):
                html = self.get(url)
                tags = {
                    "og:image": _property(html, "og:image"),
                    "twitter:image": _meta(html, "twitter:image"),
                    "og:url": _property(html, "og:url"),
                    "canonical": _canonical(html),
                }
                for tag, value in tags.items():
                    self.assertIsNotNone(value, tag)
                    self.assertNotIn("<", value, f"{tag}={value!r}")
                    self.assertNotIn("WSGIRequest", value, f"{tag}={value!r}")

>>>>>>> theirs
    def test_og_url_is_the_canonical_not_the_raw_request(self):
        html = self.get("/en/studio/?source=1")
        self.assertEqual(_property(html, "og:url"), f"{ORIGIN}/en/studio/")

    def test_a_post_page_is_an_article(self):
        self.assertEqual(
            _property(self.get(f"/en/post/{self.post.pk}/"), "og:type"), "article"
        )

    def test_a_profile_page_is_a_profile(self):
        self.assertEqual(
            _property(self.get("/en/profile/creator/"), "og:type"), "profile"
        )

    def test_og_locale_follows_the_language(self):
        self.assertEqual(_property(self.get("/en/"), "og:locale"), "en_US")
        self.assertEqual(_property(self.get("/fa/"), "og:locale"), "fa_IR")

    def test_the_alternate_locale_is_advertised_too(self):
        self.assertEqual(_property(self.get("/en/"), "og:locale:alternate"), "fa_IR")

    def test_the_two_languages_have_different_titles(self):
        self.assertNotEqual(_title(self.get("/en/")), _title(self.get("/fa/")))

    def test_a_category_description_counts_real_posts(self):
        _post(self.author, self.category, "Second")
        description = _meta(self.get("/en/category/photography/"), "description")
        self.assertIn("2", description)

    def test_a_profile_description_counts_real_posts_not_the_page_size(self):
        description = _meta(self.get("/en/profile/creator/"), "description")
        self.assertIn("1", description)

    def test_no_page_leaks_an_unrendered_placeholder(self):
        for url in ("/en/", "/fa/", "/en/explore/", "/en/studio/", "/en/search/"):
            with self.subTest(url=url):
                html = self.get(url)
                for token in ("{name}", "{count}", "{tag}", "{query}", "{author}", "{n}"):
                    self.assertNotIn(token, html)

    def test_every_page_has_exactly_one_h1(self):
        for url in ("/en/", "/fa/", "/en/explore/", "/en/category/photography/"):
            with self.subTest(url=url):
                self.assertEqual(len(re.findall(r"<h1[ >]", self.get(url))), 1)


# ---------------------------------------------------------------------------
# Crawler documents
# ---------------------------------------------------------------------------


class RobotsTxtTests(SeoTestCase):
    def setUp(self):
        self.body = self.get("/robots.txt")

    def test_it_advertises_the_sitemap_at_an_absolute_https_url(self):
        self.assertIn(f"Sitemap: {ORIGIN}/sitemap.xml", self.body)

    def test_static_and_media_stay_crawlable(self):
        # The crawler needs the CSS, JS and images to render the pages it judges.
        self.assertIn("Allow: /static/", self.body)
        self.assertIn("Allow: /media/", self.body)

    def test_the_api_is_disallowed(self):
        self.assertIn("Disallow: /api/", self.body)

    def test_private_routes_are_disallowed_in_every_language(self):
        for path in ("/saved/", "/fa/saved/", "/en/saved/"):
            with self.subTest(path=path):
                self.assertIn(f"Disallow: {path}", self.body)

    def test_no_url_is_excluded_on_the_strength_of_a_query_string(self):
        # Excluding /search/?q=… would be a rule no crawler can match; those pages
        # are consolidated with noindex plus a query-free canonical instead.
        self.assertNotIn("q=", self.body)
        self.assertNotIn("source=", self.body)

    def test_it_ignores_a_spoofed_host_header(self):
        response = self.fetch("/robots.txt", headers={"host": "attacker.example"})
        self.assertEqual(response.status_code, 301)
        self.assertNotIn("attacker.example", response["Location"])


class SitemapTests(SeoTestCase):
    def xml(self):
        return self.get("/sitemap.xml")

    def test_it_is_served_at_one_address_and_is_not_marked_noindex(self):
        # Django's sitemap view adds `noindex, noodp, noarchive`, which directly
        # contradicts a file we ask Google to fetch and trust.
        response = self.fetch("/sitemap.xml")
        self.assertEqual(response.status_code, 200)
        self.assertIn("index, follow", response["X-Robots-Tag"])
        self.assertEqual(self.fetch("/en/sitemap.xml").status_code, 404)

    def test_every_loc_is_an_absolute_https_language_prefixed_url(self):
        locations = re.findall(r"<loc>([^<]+)</loc>", self.xml())
        self.assertTrue(locations)
        for location in locations:
            with self.subTest(location=location):
                self.assertTrue(
                    location.startswith(f"{ORIGIN}/en/")
                    or location.startswith(f"{ORIGIN}/fa/"),
                    location,
                )

    def test_it_lists_the_indexable_landing_pages(self):
        for path in ("/en/", "/en/explore/", "/en/studio/"):
            with self.subTest(path=path):
                self.assertIn(f"<loc>{ORIGIN}{path}</loc>", self.xml())

    def test_it_omits_the_noindex_surfaces(self):
        for path in (
            "/en/feed/trending/",
            "/en/feed/latest/",
            "/en/feed/following/",
            "/en/search/",
            "/en/saved/",
        ):
            with self.subTest(path=path):
                self.assertNotIn(f"<loc>{ORIGIN}{path}</loc>", self.xml())

    def test_it_omits_a_creator_with_no_posts(self):
        self.assertNotIn(f"<loc>{ORIGIN}/en/profile/silent/</loc>", self.xml())
        self.assertIn(f"<loc>{ORIGIN}/en/profile/creator/</loc>", self.xml())

    def test_it_omits_an_empty_category(self):
        self.assertNotIn(f"<loc>{ORIGIN}/en/category/empty/</loc>", self.xml())

    def test_it_omits_a_tag_below_the_depth_threshold(self):
        lonely = _tag("lonely")
        _post(self.author, self.category, "Only one", tags=[lonely])
        _post(self.author, self.category, "And another", tags=[self.tag])
        xml = self.xml()
        self.assertNotIn(f"<loc>{ORIGIN}/en/tag/lonely/</loc>", xml)
        self.assertIn(f"<loc>{ORIGIN}/en/tag/neon/</loc>", xml)

    def test_it_lists_both_languages_of_a_post_with_an_x_default(self):
        xml = self.xml()
        self.assertIn(f"<loc>{ORIGIN}/en/post/{self.post.pk}/</loc>", xml)
        self.assertIn(f"<loc>{ORIGIN}/fa/post/{self.post.pk}/</loc>", xml)
        self.assertIn('hreflang="x-default"', xml)
        self.assertIn('hreflang="fa"', xml)

    def test_every_sitemap_entry_is_indexable_on_the_model(self):
        from web.sitemaps import SITEMAPS

        for name, sitemap_class in SITEMAPS.items():
            with self.subTest(section=name):
                for item in sitemap_class().items():
                    obj = item[0] if isinstance(item, tuple) else item
                    if hasattr(obj, "is_indexable"):
                        self.assertTrue(obj.is_indexable, f"{name}: {obj}")

    def test_the_sitemap_ignores_a_spoofed_host_header(self):
        response = self.fetch("/sitemap.xml", headers={"host": "attacker.example"})
        self.assertEqual(response.status_code, 301)
        self.assertNotIn(b"attacker.example", response.content)


# ---------------------------------------------------------------------------
# Language string tables
# ---------------------------------------------------------------------------


class SeoStringTests(TestCase):
    def test_both_languages_define_exactly_the_same_keys(self):
        # The two indexes are only genuinely parallel if both string tables are.
        self.assertEqual(set(SEO_STRINGS["en"]), set(SEO_STRINGS["fa"]))

    def test_no_seo_string_has_an_unbalanced_placeholder(self):
        for language, strings in SEO_STRINGS.items():
            for key, value in strings.items():
                with self.subTest(language=language, key=key):
                    self.assertEqual(value.count("{"), value.count("}"), value)

    def test_every_ui_string_needed_by_a_template_exists(self):
        # A missing key renders as an empty string, silently, with no error — so
        # the keys the templates reach for are asserted explicitly.
        from web.i18n_strings import STRINGS

        for key in (
            "video",
            "audio",
            "prompt",
            "posts",
            "followers",
            "level_n",
            "edit_profile",
            "share_a_prompt",
            "comments_title",
            "comment_placeholder",
            "comment_btn",
            "login_to_join",
            "studio_remix",
            "studio_use_prompt",
            "studio_use_prompt_title",
            "nothing_here",
            "share_first_prompt",
            "trending_now",
            "creators_to_follow",
            "just_added",
            "no_categories_yet",
            "no_creators_yet",
        ):
            for language, strings in STRINGS.items():
                with self.subTest(key=key, language=language):
                    self.assertTrue(strings.get(key), f"{language}.{key} is missing")


# ---------------------------------------------------------------------------
# The helpers themselves
# ---------------------------------------------------------------------------


class SeoHelperTests(TestCase):
    def test_split_language_prefix_only_matches_a_whole_segment(self):
        self.assertEqual(seo.split_language_prefix("/fa/post/1/"), ("fa", "/post/1/"))
        self.assertEqual(seo.split_language_prefix("/faq/"), (None, "/faq/"))
        self.assertEqual(seo.split_language_prefix("/english/"), (None, "/english/"))
        self.assertEqual(seo.split_language_prefix("/"), (None, "/"))

    def test_language_path_is_idempotent(self):
        # Breadcrumb paths arrive already prefixed from the view; re-prefixing
        # must not produce /fa/fa/…
        self.assertEqual(seo.language_path("/fa/post/1/", "fa"), "/fa/post/1/")
        self.assertEqual(seo.language_path("/post/1/", "fa"), "/fa/post/1/")

    def test_clamp_never_exceeds_the_budget(self):
        self.assertLessEqual(len(seo.clamp_title("word " * 100)), seo.TITLE_LIMIT)
        self.assertLessEqual(len(seo.clamp_description("word " * 200)), seo.DESCRIPTION_LIMIT)

    def test_clamp_collapses_whitespace(self):
        self.assertEqual(seo.clamp_description("  a\n\nb   c "), "a b c")

    def test_normalize_path_collapses_duplicate_slashes(self):
        self.assertEqual(seo.normalize_path("//post//1/"), "/post/1/")

    @override_settings(SITE_URL=ORIGIN)
    def test_absolute_media_url_upgrades_a_relative_path(self):
        self.assertEqual(
            seo.absolute_media_url("/media/posts/a.png", None), f"{ORIGIN}/media/posts/a.png"
        )

    def test_absolute_media_url_leaves_an_absolute_url_alone(self):
        self.assertEqual(
            seo.absolute_media_url("https://cdn.example/a.png", None),
            "https://cdn.example/a.png",
        )

    def test_site_origin_ignores_an_untrusted_host(self):
        request = type("R", (), {"scheme": "http", "get_host": lambda self: "evil.example"})()
        with override_settings(SITE_URL=ORIGIN):
            self.assertEqual(seo.origin(request), ORIGIN)

    def test_empty_site_url_falls_back_to_the_request_origin(self):
        request = type("R", (), {"scheme": "http", "get_host": lambda self: "localhost:8000"})()
        with override_settings(SITE_URL=""):
            self.assertEqual(seo.origin(request), "http://localhost:8000")
