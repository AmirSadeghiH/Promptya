# Promptya — Search Console Setup

**Date:** 2026-10-02
**Companion to:** `SEO_AUDIT.md` (technical state), `KEYWORD_STRATEGY.md` (what to target).

> **Nothing in this document has been performed.** No property was verified, no sitemap
> submitted, no DNS record created, no token generated. Every step below is for a human
> with access to the domain registrar, the hosting environment, and a Google account. No
> verification codes, property IDs, or account details are included, because none exist
> and none were invented.

---

## 0. Before you start

The deployment must be live at a stable public HTTPS hostname. Search Console cannot
verify a staging box, an IP address, or a host that is not reachable from the internet.

You need:

- The **production hostname** (e.g. `https://promptya.example`) — decided, not guessed.
- Access to DNS/hosting, to set environment variables.
- A Google account with access to the property.

**Step 0 is the one that matters most:** set the site identity in the environment.

```bash
PROMPTYA_SITE_URL=https://your-domain.example
DJANGO_ALLOWED_HOSTS=your-domain.example,www.your-domain.example
```

`PROMPTYA_SITE_URL` is what every canonical URL, `hreflang` pair, Open Graph URL, sitemap
`<loc>`, and the `robots.txt` `Sitemap:` line are built from. Without it the site falls
back to the incoming `Host` header — which works, and is exactly what you do *not* want in
production, because it makes the canonical identity of the site equal to whatever a
misconfigured proxy or `ALLOWED_HOSTS = ["*"]` says at the moment.

Until it is set, `python manage.py check` emits:

```
?: (web.W001) SITE_URL is not set; canonical URLs, hreflang, Open Graph and the sitemap
   are built from the incoming Host header.
  HINT: Set PROMPTYA_SITE_URL=https://yourdomain.com in production.
```

Treat that warning as a deployment blocker, not a suggestion. It is the difference
between the site telling search engines what it is, and the site believing whatever it is
told.

`DJANGO_ALLOWED_HOSTS` is set separately and for a different reason: without it, `Host`
is unvalidated, which is a request-forgery/host-injection surface independent of SEO.
`ALLOWED_HOSTS` defaults to `["*"]` in this project.

Also confirm the canonical origin is reachable over plain HTTP and redirects to HTTPS —
`CanonicalHostMiddleware` does one redirect to the canonical origin, but only if it knows
what the canonical origin is, which means `PROMPTYA_SITE_URL` must be set first.

---

## 1. Which property type

**Use a `Domain` property, not a `URL prefix` property.**

| | Domain property | URL prefix property |
|---|---|---|
| Covers | `example`, `www.example`, any subdomain, any scheme | Only the exact prefix you type |
| Subdomain / protocol mismatch | Covered automatically | Needs a separate property |
| Needs DNS | Yes | No |
| Search Console API | Supported | Not supported |

Promptya is bilingual, not multi-domain, so a URL-prefix property *would* cover `/en/` and
`/fa/` equally — a domain property is chosen for the `www`/apex and `http`/`https` cases
and for API access, not for the language split.

To verify a domain property, Google gives you a **DNS TXT record**. Add it to the domain's
DNS zone and wait for propagation (minutes to a day). Note the `_googlebot.<domain>` TXT
record; that is a separate verification step from the `<domain>` one.

Verification tokens are issued by Google and are account-specific. Do not paste one into
the codebase, a template, or a commit.

---

## 2. Submitting the sitemap

The sitemap is served by Django at a single address and needs no `?page=` parameter:

```
https://your-domain.example/sitemap.xml
```

Submit it under **Sitemaps** in the property. It lists both languages of every indexable
URL, with `xhtml:link` alternates and an `x-default`, and it deliberately **omits** every
`noindex` surface (feeds, search, Studio for authenticated users, private pages).

**Verify it before submitting.** Fetch it and check:

- [ ] It is served at exactly `/sitemap.xml`, without a trailing slash and without a prefix.
- [ ] Every `<loc>` is `https://` and on the canonical hostname — not `http://`, not
      `www.`, not a staging domain.
- [ ] Both `https://…/en/…` and `https://…/fa/…` appear for shared content.
- [ ] Each URL has an `<xhtml:link rel="alternate" hreflang="…">` set including `x-default`.
- [ ] No `/feed/`, `/search/`, `/api/`, `/admin/`, `/login/`, `/saved/`, or `/notifications/`
      URL appears.
- [ ] No empty category, no tag with fewer than 2 posts, no creator with no public posts.

There is a test for each of those; `python manage.py test web.test_seo` is the authority if
you want to confirm rather than eyeball.

### If `SITE_URL` was not set

The sitemap will be built from the request host. Submitting it in that state can register
a canonical identity under the wrong origin (an internal proxy name, a preview host). Fix
`PROMPTYA_SITE_URL`, redeploy, then submit — do not submit first and correct later.

---

## 3. URL Inspection

After submitting, spot-check a handful of URLs by hand under **URL Inspection → Test a live
URL**. Pick at least one of each:

- `/en/` and `/fa/` (the two language roots)
- one category URL with enough posts
- one post URL with an image
- one profile URL with posts
- `/feed/trending/` — **expected to report "Not indexed" or blocked.** It is `noindex` and
  disallowed-ish by design. A clean "Excluded by 'noindex'" here is a **pass**, not a bug.
- `/search/?q=test` — likewise expected to be excluded.

What a live test should report for the indexable ones: *"Google-indexable"*, with the
crawled page showing the matching canonical. If Google fetches a *different* canonical than
the one submitted, that is a host/`SITE_URL` problem, and it will not fix itself.

---

## 4. Reading the reports

**Pages → Indexing → Why your pages aren't indexed.** The two buckets that should be empty:

| Bucket | Expected | If it is not empty |
|---|---|---|
| Discovered – currently not indexed | a few new URLs | Normal right after launch; watch it not grow |
| Crawled – currently not indexed | should trend to ~0 | Something is judging your pages thin. Check the test suite's indexability rules still hold against real data. |

**Pages → Crawl → Indexing problems.** Anything reported here is real and worth fixing
before anything else:

- *Submitted URL marked noindex* — a `noindex` leaked onto a sitemap URL.
- *Soft 404* — a URL returns 200 with nothing on it. The audit's `_paginate` deliberately
  raises `404` for an out-of-range page precisely to avoid manufacturing these; if one
  appears in a real listing, it is a filter that emptied after the page was rendered.
- *Alternate page with proper canonical* — **expected and fine.** The unprefixed legacy
  aliases land here.

**Crawl → URL Inspection → Crawl Stats.** Expect crawler requests against the **unprefixed**
aliases to keep going indefinitely. That is by design: the aliases return 200 with a
self-referencing canonical rather than 301, to avoid breaking existing links and the PWA
`start_url`. The canonical, not the redirect, is what keeps them out of the index. See
`SEO_AUDIT.md` §5 ("Deliberately not done") for the reasoning.

---

## 5. International targeting

**Performance → International Targeting.** Expect to see `en` and `fa` as separate
countries/regions rather than a clean per-language split — Google reports targeting by
*location*, not by language.

The specific thing to watch is the question raised in `KEYWORD_STRATEGY.md` §5: post
bodies are not machine-translated, so `/en/post/N/` and `/fa/post/N/` differ only in
chrome. If FA URLs receive no impressions while EN URLs do, the overlap is winning and the
`hreflang` signal is being resolved against you. That is a content/product decision (per-post
language variants), not something to fix by editing tags.

---

## 6. Core Web Vitals

**Experience → Core Web Vitals.** Three metrics, all reported by field data only:

| Metric | Field data available when |
|---|---|
| LCP | 28 days of traffic |
| CLS | 28 days |
| INP | 28 days |

Before that, the report shows *"Insufficient data"* — which is **not** a failure and
should not be waited on before submitting. The technical work is already done
(`SEO_AUDIT.md` §7: LCP `fetchpriority`, intrinsic `width`/`height`, WebP derivative, no
lazy-load on the hero).

For the first month, use **Lighthouse (mobile, throttled)** against production and treat it
as a *relative* number — a baseline to re-measure after each change — not as a field
measurement. Do not report it as a user-facing Core Web Vitals figure.

---

## 7. Bing Webmaster Tools

Optional, but worth it for a Persian-language audience: Bing's index and its handling of
`hreflang` differ from Google's in ways that sometimes matter.

- Import from Search Console (no re-verification if Google already verified).
- Submit the same `https://your-domain.example/sitemap.xml`.
- Add IndexNow if you later have a hot path for new posts.

Do not expect parity. Track it as a second, independent signal.

---

## 8. Monitoring and maintenance

### What to check weekly

- New sitemap errors (an empty or 404ing sitemap stops discovery of everything new).
- Indexing-reason changes on previously indexed URLs.
- Crawl stats spiking on `/static/` or `/media/` relative to pages — usually asset churn.

### What to check monthly

- Impressions and average position grouped by `/category/`, `/post/`, `/tag/`, `/profile/`.
  This is the page-*type*-level signal and is more reliable early than keyword-level signal.
- International targeting (§5).
- Core Web Vitals once field data exists (§6).
- Engagement: are indexed posts getting clicks, or only impressions? Impressions without
  clicks across a whole template usually means the title/description are wrong for the
  query, which is a content-side fix (`KEYWORD_STRATEGY.md` §4).

### When something regresses

1. Check `python manage.py check` — an unset `PROMPTYA_SITE_URL` reproduces immediately.
2. Run `python manage.py test web.test_seo` — 98 tests, covering canonical, hreflang,
   robots, sitemap contents, indexability, and metadata. Most regressions in this area
   fail there before they are visible in Search Console.
3. Use URL Inspection → *Test a live URL* on the affected page; compare Google's fetched
   canonical against what the test suite says it should be.

---

## 9. Checklist

Configuration (deployment, before anything else):

- [ ] `PROMPTYA_SITE_URL` set to the production HTTPS origin
- [ ] `DJANGO_ALLOWED_HOSTS` set explicitly (no `*`)
- [ ] `python manage.py check` shows no `web.W001`
- [ ] `python manage.py test web.test_seo` passes
- [ ] HTTP → HTTPS and apex → canonical host both redirect in one hop
- [ ] `https://your-domain.example/sitemap.xml` returns 200 with absolute HTTPS `<loc>`s
- [ ] `https://your-domain.example/robots.txt` advertises the same absolute sitemap URL

Search Console:

- [ ] Domain property verified via DNS TXT
- [ ] `https://your-domain.example/sitemap.xml` submitted
- [ ] URL Inspection run on: `/en/`, `/fa/`, one category, one post, one profile
- [ ] `/feed/trending/` and `/search/?q=x` confirmed *excluded* (a pass)
- [ ] First international-targeting read taken and the EN/FA overlap noted

Optional:

- [ ] Bing Webmaster Tools imported, same sitemap submitted
- [ ] Lighthouse mobile baseline captured against production

**Not done, and not to be fabricated:** no property was verified, no sitemap submitted, no
DNS record created, no token generated, no Core Web Vitals number measured, and no
traffic or ranking outcome predicted. Every field in this document is either a step for a
human or an explicitly blank measurement.