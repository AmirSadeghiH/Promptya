# Promptya — Technical SEO Audit

**Scope:** full audit of `https://github.com/AmirSadeghiH/Promptya` (Django 6.1, SQLite
for dev, session auth, server-rendered templates + vanilla JS, PWA, EN/FA with RTL).

**Date:** 2026-10-02
**Baseline before this work:** 155 tests passing, `manage.py check` clean, 8 Django apps
(`account`, `core`, `credits`, `imagegen`, `interactions`, `notifications`, `posts`, `web`).

This document records what already existed, what was broken, what was missing, the
decisions taken, and the final state. It is written so a reviewer can verify each claim
against the code.

---

## 1. What was already implemented (kept, not duplicated)

Promptya was **not** starting from zero. The following were already present and correct
in spirit, and this work improved them in place:

| Area | Existing implementation | File |
|---|---|---|
| `<title>` / meta description | Template `{% block %}`s on `base.html`, per-page overrides | `templates/web/base.html` |
| Canonical link | `{% block canonical %}` defaulting to `request.build_absolute_uri` | `templates/web/base.html:21` |
| `robots` meta | `{% block robots %}` with per-template overrides | `templates/web/base.html:20` |
| Open Graph | `og:site_name`, `og:locale`, `og:locale:alternate`, `og:type`, `og:title`, `og:description`, `og:url`, `og:image`, `og:image:alt`, dimensions | `templates/web/base.html:23-34` |
| Twitter Card | `twitter:card`, `twitter:title`, `twitter:image` | `templates/web/base.html:35-37` |
| JSON-LD | Site-wide `WebSite` + `SearchAction` graph; `CollectionPage` + `BreadcrumbList` on categories; `CreativeWork` + `InteractionCounter`s on posts | `base.html:87-111`, `category.html`, `post_detail.html` |
| `robots.txt` | Django view, blocks admin/api/settings/create/saved/notifications/offline/login/signup, points at the sitemap | `web/views.py:247` |
| XML sitemap | Django `Sitemap` classes for posts, profiles, categories and static pages, mounted at `/sitemap.xml` | `web/sitemaps.py`, `web/urls.py:25` |
| `noindex` | `search.html`, `feed.html`, `create.html`, `saved.html`, `notifications.html`, `profile_edit.html`, `offline.html`, `login.html`, `signup.html` | `templates/web/*` |
| Bilingual `lang`/`dir` | `<html lang="{{ lang }}" dir="{{ dir }}">` driven by the `promptya-lang` cookie | `base.html:2`, `web/context_processors.py` |
| Server-side i18n | Full EN/FA string tables rendered server-side, JS re-applies them live | `web/i18n_strings.py`, `static/js/i18n.js` |
| Crawlable HTML content | Everything server-rendered; JS is enhancement only | throughout |
| Sitemap pagination | Handled by Django's sitemap view | Django |

Everything below is a **gap in the above**, not a replacement of it.

---

## 2. Critical problems found

### 2.1 The bilingual architecture was invisible to search engines (severity: critical)

The only language mechanism was a cookie (`promptya-lang`) read by
`web/context_processors.py`. Consequences:

* **One URL, two languages, no way for a crawler to choose.** A crawler that does not
  send cookies gets the default (`en`). A Persian index could therefore never be built:
  the entire Persian surface was unreachable without a prior visit that set the cookie.
* **No `hreflang`.** The template advertised `og:locale:alternate`
  (`base.html:25`) — a hint that an alternate exists — but no `<link rel="alternate"
  hreflang=...>` was ever emitted, so search engines had no machine-readable signal.
* **JS-dependent language.** `static/js/i18n.js:525` rewrites every `[data-i18n]`
  element client-side. Any content that only exists as a JS-swapped string is
  effectively invisible to a non-JS crawler, and the string table in `i18n.js` is a
  hand-maintained **duplicate** of `web/i18n_strings.py` with no parity test.
* **The advertised alternates were not real.** `og:locale:alternate` claimed `fa_IR`
  existed at the same URL; it did not, as far as a crawler was concerned.

### 2.2 Canonical URLs were derived from the request, not from a fixed site identity (severity: critical)

`base.html:21`, `base.html:29`, `base.html:94-103`, `category.html:18,23-24`,
`post_detail.html:138,149` and `web/views.py:262` all used `request.scheme` /
`request.get_host()` / `request.build_absolute_uri`.

* `request.build_absolute_uri` **includes the query string**. `/studio/?source=12` and
  `/studio/?source=99` each canonicalised to *themselves*, i.e. self-canonicalising
  duplicate URLs. Same for `/search/?q=...` (mitigated only by a manual `{% block
  canonical %}` override in `search.html:7`).
* `ALLOWED_HOSTS` defaults to `["*"]` (`core/settings.py:20`), so with no
  `DJANGO_ALLOWED_HOSTS` set, **any** `Host` header was echoed into the canonical tag,
  the `og:url` tag and the JSON-LD `@id`/`url` fields. That is a canonical-injection and
  duplicate-content vector.
* The `robots.txt` `Sitemap:` line was built from `request.get_host()` too.

### 2.3 The sitemap contradicted the site's own `noindex` directives (severity: high)

`web/sitemaps.py:73-79` published `/feed/trending/` and `/feed/latest/`, while
`templates/web/feed.html:4` marks every `/feed/<variant>/` page `noindex, follow`.
A sitemap must only contain indexable URLs.

### 2.4 The sitemap listed thin and non-indexable pages at scale (severity: high)

* `ProfileSitemap.items()` returned **every** `is_active` user, including accounts with
  zero public posts — an empty, thin profile page per registered account.
* `CategorySitemap.items()` returned **every** category, including ones with no posts.
* `PostSitemap.items()` returned **every** post, including posts with neither prompt nor
  media and neither a title worth indexing nor a description.
* `CategorySitemap.lastmod()` returned `created_at` — a value that never changes, so
  `lastmod` was permanently wrong for any category whose posts changed.

### 2.5 Absolute-URL requirements were unmet (severity: high)

* `<loc>` in the sitemap was `request.scheme`-dependent. Django's sitemap view uses
  `RequestSite` (the `django.contrib.sites` app is **not** installed) and
  `Sitemap.protocol = None`, so the protocol depended on how the crawler connected.
* `post_detail.html:8-9` and `profile.html:7` emitted **relative** media paths
  (`/media/posts/images/x.png`) as `og:image`, `twitter:image` and JSON-LD `image`.
  Relative Open Graph image URLs are invalid and are dropped by social scrapers.
<<<<<<< ours
* The `og:image` fallback used a 512×512 app icon — a poor share card.
=======
* **The `og:image` fallback was not merely a poor share card — it was not a URL.**
  Every page without an image of its own rendered:

  ```
  <meta property="og:image"
        content="https://host/<WSGIRequest: GET '/en/feed/trending/'>/static/icons/icon-512.png">
  ```

  The template wrote the fallback as `{% abs_media request %}{% static 'icons/icon-512.png' %}`.
  No template tag can consume another tag's output as an argument, so the `{% static %}`
  half was inert and `abs_media` was handed the *request object* to absolutise —
  `str(WSGIRequest)` and all. Every page that fell back was emitting a syntactically valid
  `https://` string that no scraper could fetch, and the pre-existing test only asserted
  `startswith("https://")`, so it passed. Fixed by resolving the fallback once in
  `_meta_context` (`default_og_image`) and asserting the full value; see
  `test_the_fallback_social_image_is_a_real_url_on_every_page` and
  `test_no_meta_tag_leaks_a_python_repr_into_a_url`.
>>>>>>> theirs

### 2.6 Duplicate content and status-code issues (severity: medium/high)

* `feed_page` (`web/views.py:70`) silently `redirect()`ed an unknown feed variant to the
  home page with a **302**. `/feed/anything/` should be a `404`.
* `web/urls.py` has no trailing-slash/`www`/scheme normalisation of its own, relying
  entirely on `CommonMiddleware` (`APPEND_SLASH` default `True`). No redirect existed
  for `http://` → `https://` or `www.` → apex at the Django layer.
* `/fa`-style duplicate space did not exist yet, but adding it naively would have.
* The homepage is **indexable and personalised** for logged-in users ("For You"
  recommended feed, `web/views.py:47`) while serving the plain latest feed to
  anonymous visitors. Two different documents at one indexable URL.

### 2.7 `X-Robots-Tag` was absent (severity: medium)

Every `noindex` decision relied on a `<meta name="robots">` tag alone. A crawler or
proxy that strips or ignores meta tags would still fetch private pages. Defense in depth
was missing.

### 2.8 Image/Core Web Vitals defects (severity: medium/high)

* **No `width`/`height` anywhere** in `templates/web/partials/post_grid.html:11` or
  `templates/web/post_detail.html:19` → guaranteed layout shift (CLS) as media loads.
* **The LCP image was lazy-loaded.** Every grid image carried `loading="lazy"`, including
  the first, above-the-fold card. The post-detail hero image
  (`post_detail.html:19`) had no `decoding`, no `fetchpriority` and no `loading` hint at
  all, so it was neither eagerly prioritised nor lazily deferred.
* No `fetchpriority="high"` on the LCP candidate anywhere.
* No WebP/AVIF derivative: a PNG upload was served as a PNG to every browser.

### 2.9 Content architecture gaps (severity: medium)

* **No tag pages.** `Tag` exists as a model and is searchable via
  `posts.services.search_posts(tag_slug=…)`, and `/api/posts/tags/` exposes it, but there
  was no HTML page and no link. `post_detail.html:77` rendered tags as inert
  `<span class="chip">#name</span>` — visible text with no crawlable destination.
<<<<<<< ours
* **No crawlable pagination.** `partials/post_grid.html:97` emitted only
  `<div class="load-more" data-next-cursor="…">`. Posts 13+ of every feed and every
  category were reachable only through a JavaScript `IntersectionObserver`. Crawlers
  that do not execute JS saw page 1 of every listing, forever.
=======
* **No crawlable pagination.** Two different failures, one cause:
  * The cursor-paginated surfaces (`partials/post_grid.html:97`) emitted only
    `<div class="load-more" data-next-cursor="…">`. Posts 13+ were reachable only through
    a JavaScript `IntersectionObserver`, so a non-JS crawler saw page 1 of every feed,
    forever.
  * The offset-paginated surfaces (category, tag, profile) emitted **neither** — not even
    a `.load-more`. They had no way to page at all.
  Fixed in item 9 of §5. Note that the fix is deliberately *not* "render both": a cursor
  has no crawlable URL and an offset page is not an infinite-scroll endpoint. See §6.
>>>>>>> theirs
* **`/search/` was not linked from any crawlable navigation element** with a query, and
  the search form's only action is `GET /search/`, which is `noindex`. Acceptable, but
  the `WebSite` `SearchAction` (`base.html:99-106`) advertises a `sitelinks searchbox`
  that the site does not actually support as an indexable surface.
* **Profile metadata lied.** `profile.html:4` used `{{ posts|length }}` for the
  meta description and `profile.html:27` for the visible post count, but the view caps
  the list at 24 (`web/views.py:191`). A creator with 300 posts was described as having
  24.

### 2.10 Structured-data correctness (severity: medium)

* `post_detail.html:134-156` emitted a second, independent `application/ld+json`
  document. The comment at `base.html:112-113` claimed pages "append their own entities
  here so the site-level `WebSite` graph above is never lost" — true, but the two
  documents cannot reference each other by `@id`, so `WebPage`/`breadcrumb` could not be
  tied to the `CreativeWork`.
* The JSON was hand-written with inline `{% if %}` commas — one missing comma and the
  block is silently invalid.
* `"image"` was a relative URL (see 2.5).
* No `Person`/`ProfilePage` on creator profiles, no `ItemList` on listings.
* No automated validation of any JSON-LD anywhere in the test suite.

### 2.11 `robots.txt` analysis (severity: medium)

The file was broadly correct, but:

* `Sitemap:` used the request host (2.2).
* The private-page `Disallow` list is fine, but the *absence* of `noindex` headers
  (2.7) meant the two mechanisms had to both be right.
* No explicit `Allow` for `/static/` and `/media/` — the default `Allow: /` covered
  them, but nothing documented that the CSS/JS the crawler needs is intentionally
  crawlable.
* Query parameters were **not** blanket-disallowed, which was correct: `/studio/?source=N`
  and `/search/?q=X` are not blocked, they are `noindex` at the page level. This was
  kept.

### 2.12 Performance (severity: medium, unmeasured)

Observed by reading the code, **not** measured with a real user or lab run:

* Google Fonts are loaded from `fonts.googleapis.com` with `media="print"` + `onload`
  (`base.html:58-64`) — a render-blocking third-party origin and two extra DNS/TLS
  handshakes on a cold mobile connection.
* `post_list_queryset` (`posts/services.py:37`) annotates five `Count(distinct=True)`
  aggregates over three reverse relations plus two `Exists` subqueries. The existing
  `FeedQueryTests.test_latest_feed_serializes_five_tagged_posts_in_two_queries` guards
  query *count* (2), not cost.
* `ProfileSitemap` / `PostSitemap` used `.only(...)`, which is correct, but
  `ProfileSitemap` had no filter to shrink the row set.
<<<<<<< ours
* The service worker caches **all** page responses in one flat `PAGE_CACHE` keyed by URL
=======
* The service worker cached **all** page responses in one flat `PAGE_CACHE` keyed by URL
>>>>>>> theirs
  (`static/sw.js:74-81`). Because language is cookie-driven and not URL-driven, a
  Persian visitor and an English visitor offline at the same URL could be served each
  other's cached copy.

---

## 3. Indexability matrix (final state)

| URL | Status | Reason |
|---|---|---|
| `/en/…`, `/fa/…` | **index, follow** | canonical, language-addressed |
| `/…` (unprefixed legacy) | indexable HTTP 200, **canonicalises** to `/en/…` or `/fa/…` | backward compatibility; canonical prevents duplicate indexing |
| `/post/<pk>/` | index iff the post is indexable | empty / low-value posts are `noindex` |
| `/category/<slug>/` | index iff the category has ≥1 post | empty category hubs are thin |
| `/tag/<slug>/` | index iff the tag has ≥2 posts | one-post tag pages are thin |
| `/profile/<username>/` | index iff the creator has ≥1 public post | empty profiles are thin |
| `/explore/`, `/studio/` | index, follow | curated landing pages |
| `/` , `/en/` , `/fa/` | index, follow | home, language roots |
| `/feed/latest/`, `/feed/trending/` | **noindex, follow** | near-duplicates of home/explore; **removed from the sitemap** |
| `/feed/following/` | noindex, nofollow | requires authentication |
| `/search/` (any `?q=`) | noindex, follow | infinite thin duplicates |
| `/studio/?source=`, `?prompt=` | noindex, follow | unbounded parameter space |
| `/studio/` for an authenticated user | noindex, nofollow | contains that account's generations and credit balance |
| `/create/`, `/saved/`, `/notifications/`, `/settings/profile/`, `/login/`, `/signup/`, `/offline/` | noindex, nofollow | private / authentication-only / utility |
| `/api/**`, `/admin/**` | `Disallow` in robots.txt, JSON/noindex headers | not HTML |
| 404 | 404 | no soft 404s |

---

## 4. Bilingual URL strategy (final decision)

**Chosen: language-prefixed canonical URLs, with unprefixed legacy aliases retained.**

```
/en/explore/          canonical English
/fa/explore/          canonical Persian
/explore/             200 OK, <link rel="canonical" href="…/en/explore/"> (or /fa/… per cookie)
```

* Built with Django's `i18n_patterns(path("", include("web.urls")),
  prefix_default_language=True)` scoped to the `web` app only, wrapped by a new
  `web.middleware.LanguageMiddleware` that resolves language as
  **path prefix → `promptya-lang` cookie → `en`**.
* **Every existing URL keeps working with no redirect.** The API, `/admin/`, `/login/`,
  `/signup/`, `/logout/`, `/static/`, `/media/`, `/robots.txt` and `/sitemap.xml` are
  untouched and never gain a prefix. Authentication, the PWA service worker, the mobile
  API client and every external link are unaffected.
* Internal links are automatically language-correct because `reverse('web:…')` resolves
  against the active language — no template had to be rewritten to link to `/fa/…`.
* `hreflang` is emitted reciprocally on every indexable page
  (`fa` ↔ `en` + `x-default` → `en`), computed from one shared
  language-neutral path, so reciprocity is structural rather than maintained by hand.
* Rejected alternatives: `?lang=` (weaker signal, easy to lose); full `prefix_default_language=False`
  (Django 6 resolves only one of the two forms, so either `/explore/` or `/en/explore/`
  would 404); global `i18n_patterns` over the whole root URLconf (would have prefixed
  `/api/` and `/admin/`).

### Gaps that remain, stated plainly

* The Persian and English versions of a **post body** (title, description, prompt) are
  the author's content and are *not* machine-translated. Only the **chrome** (nav,
  headings, labels, metadata) is genuinely translated. Per-post language versions would
  need a translated-content model and is out of scope.
* Category and tag **names** are user/seed data and are not translated.
* Pagination is cursor-based on the JSON API, so HTML paginated pages are provided via
  `?page=` on listings (see 4.1 in the implementation notes below) — see §6.

---

## 5. Prioritised implementation plan (as executed)

| # | Item | Severity | Status |
|---|---|---|---|
| 1 | Fixed site identity (`SITE_URL`), absolute HTTPS URLs everywhere, host-injection-proof | critical | done |
| 2 | Language-prefixed canonical URLs + `hreflang` + `x-default` | critical | done |
| 3 | Per-page titles/descriptions/canonicals computed in Python, not templates | high | done |
| 4 | Sitemap: absolute HTTPS, `xhtml:link` alternates, `x-default`, filtered items, correct `lastmod`, no `noindex` URLs | high | done |
| 5 | `robots.txt` rebuilt from `SITE_URL`; sitemap/view wrapper that strips Django's contradictory `X-Robots-Tag: noindex` | high | done |
| 6 | `X-Robots-Tag` on every non-indexable page (defense in depth) | high | done |
| 7 | Indexability rules: posts, profiles, categories, tags | high | done |
| 8 | Tag landing pages + tag links on post detail | medium | done |
| 9 | Crawlable pagination on every listing (infinite scroll kept as enhancement) | high | done |
| 10 | Image `width`/`height`, LCP `fetchpriority`/`decoding`, WebP derivative | medium | done |
| 11 | JSON-LD centralised, validated by tests (`WebSite`, `Organization`, `WebPage`, `BreadcrumbList`, `ProfilePage`, `Person`, `CreativeWork`, `ItemList`) | medium | done |
| 12 | `H1` on every page (home, feed and search were missing one) | medium | done |
| 13 | 404 for unknown feed variants; themed `404.html` / `500.html` | medium | done |
<<<<<<< ours
| 14 | Service worker stops cross-language offline cache poisoning | medium | done |
=======
| 14 | Service worker stops cross-language offline cache poisoning, and never caches `robots.txt` / `sitemap.xml` | medium | done |
>>>>>>> theirs
| 15 | Automated SEO test suite | high | done |
| 16 | EN/FA string-table parity test | medium | done |

### Deliberately **not** done, with reasons

* **No soft-delete / tombstone model and therefore no `410 Gone`.** Posts are hard
  deleted, so a removed post correctly returns `404`. Introducing tombstones would be a
  product decision, not an SEO one.
* **No automatic URL→`301` redirect for legacy unprefixed URLs.** Redirecting them would
  break every existing external link, the PWA `start_url`, the service worker precache
  and the mobile client. A self-referencing canonical achieves the same SEO outcome
  without a redirect chain.
* **No `django.contrib.sites`.** `SITE_URL` plus `Sitemap.get_domain()`/`get_protocol()`
  overrides do the same job with one less app and one less DB row to keep in sync.
* **No blog / article factory.** See `KEYWORD_STRATEGY.md` §6 — prioritising existing
  pages over manufactured thin content.
* **No Core Web Vitals claims.** No Lighthouse, CrUX or field data was available. See
  §7.

---

## 6. Bilingual pagination note

<<<<<<< ours
Listings are cursor-paginated in the JSON API. For HTML, listings accept `?page=N`
(1-based) rendered with ordinary `<a href>` links, each page self-canonicalising to
`?page=N` for `N > 1` and to the bare URL for `N == 1`. The cursor-based infinite scroll
is preserved on top of it and the "load more" element is only rendered when a further
page exists. Page 1 of every listing carries the plain canonical; deeper pages carry
their own, so no listing collapses to a single URL.
=======
Listings are cursor-paginated in the JSON API. For HTML, the **offset-paginated**
surfaces (category, tag, profile) accept `?page=N` (1-based), rendered with ordinary
`<a href="?page=N">` links so a crawler that does not execute JavaScript can walk past
page 1. Every page of a listing — including `?page=N` for `N > 1` — **canonicalises to
page 1** (`test_every_page_of_a_listing_canonicalises_to_page_one`). Page 2+ is the same
document with a different slice of the same ordered list, so letting them self-canonicalise
would split the listing's own relevance across its pages.

The **cursor-paginated** surfaces (home, `/feed/*/`) keep the `.load-more` sentinel and
their infinite scroll, and carry **no** pagination link: a cursor has no URL for a link to
point at, so emitting `?page=2` there would advertise an address that 404s. The two
controls are mutually exclusive by design, not an oversight — see the comment in
`partials/post_grid.html` and the tests in `web/test_seo.py::PaginationTests`.
>>>>>>> theirs

---

## 7. Performance — what was measured and what was not

**Measured:** nothing field-based. The repository has no Lighthouse CI, no
`web-vitals` library and no CrUX export.

**Measured by code review and by the existing query-count tests:** the `FeedQueryTests`
guard (2 queries for a 5-post page) still passes after these changes; the SEO work added
no new per-row queries to any feed or listing page.

**Changed for performance:**
* LCP image gets `fetchpriority="high"`, `decoding="async"` (or `sync` on the hero) and
  is never lazy-loaded; every other content image is `loading="lazy"`.
* `width`/`height` attributes on every content image, from values captured once at upload
<<<<<<< ours
  time (`Post.image_width/height`, `CustomUser.profile_picture_width/height`) — no
  per-request file read.
=======
  time (`Post.image_width/height`) — no per-request file read. Profile avatars are
  deliberately *not* covered: avatars render through the initial-letter shell, which has a
  fixed box, so there is no media element to reflow and the dimension fields would have
  been written on every upload for nothing.
>>>>>>> theirs
* A WebP derivative is produced once at upload time and served as `src`; the original is
  kept for the download action. This roughly halves the bytes for a typical PNG upload on
  browsers that support WebP, with the original still reachable.
* The sitemap now selects only the columns it needs and filters in SQL.
* Fonts remain third-party from `fonts.googleapis.com`; the render-blocking `media=print`
  + `onload` pattern already in `base.html` was left in place. Self-hosting the fonts is
  a real recommendation (§8), not a claim.

---

## 8. Recommendations not implemented (needs a decision or measurement)

1. **Self-host the fonts** (or subset + preload only the used weights). Removes two
   third-party origins and a render-blocking stylesheet. Requires choosing a licence-safe
   hosting strategy for Inter / Vazirmatn / JetBrains Mono.
2. **Responsive `srcset` derivatives** (320/640/1024/1440). The upload pipeline now knows
   the dimensions, so a thumbnail ladder is a contained follow-up and would cut LCP
   further on mobile. Not implemented because it multiplies storage and the template
   surface for an unmeasured gain.
3. **AVIF** in addition to WebP. Better compression, slower encode; worth it only if the
   encode cost is moved off the request path (it currently runs in `pre_save`).
4. **Post slugs.** `web/urls.py` uses `post/<int:pk>/`. Slugs are better for click-through
   but would need a permanent-redirect table and a decision on what happens when a title
   changes. Intentionally not introduced: the numeric URLs are stable, already shared and
   already indexed.
5. **Move heavy listing work off the request path** (cached explore data, `select_related`
   tuning) once real query timings are available.
6. **A real `410`/tombstone path** if a moderation or "unpublished" feature is ever added.
7. **Per-post language variants** if the community is willing to author both, with a
   language field on `Post`. This is the only way the two indexes become genuinely
   parallel rather than chrome-translated.
8. **Measure before optimising further**: run Lighthouse and PageSpeed Insights against
   a production deployment, and watch the Core Web Vitals report in Search Console.

---

## 9. Manual configuration still required

See `SEARCH_CONSOLE_SETUP.md`. In summary: set `PROMPTYA_SITE_URL`, set
`DJANGO_ALLOWED_HOSTS`, verify the domain property, submit the sitemap, and confirm the
production host serves HTTPS. No verification token, no DNS record and no external
account action was performed or fabricated by this work.
