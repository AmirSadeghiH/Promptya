# Promptya — Front-End Audit

**Scope:** the whole server-rendered front end — `templates/web/**`,
`static/css/app.css`, `static/js/*.js`, `static/sw.js`,
`static/manifest.webmanifest`, and the auth templates under `account/templates/**`.

**Date:** 2026-10-15
**Method:** headless Chromium audit (`Playwright` driven against local Chrome) over
18 routes × 5 viewports (1440×900, 1280×720, 834×1112, 390×844, 320×640), plus a
static read of every template, stylesheet and script. Raw data:
`.freebuff/audit/out/report.json`, `.freebuff/audit/out/deep.json`, and 34
captured screenshots.

**Constraints this audit works inside** (from `AGENTS.md`): no new front-end
framework, no CSS framework, server-rendered templates stay authoritative,
smallest safe change, existing behaviour preserved.

---

## 1. What is already good (do not rebuild)

This is a genuinely well-built front end. The following are correct and should be
kept as-is:

| Area | Evidence |
|---|---|
| Design-token system | Every colour/size/radius/duration resolves to a token in `app.css:53`; no hardcoded values in components |
| Light theme | A designed palette (`app.css:181`), not an inversion. Both themes were rendered and checked |
| RTL / bilingual | Logical properties throughout (`inset-inline-*`, `padding-inline-*`); explicit mirrors only where logical properties cannot reach (select chevron, theme-switch knob travel) |
| `prefers-reduced-motion` | Several dedicated blocks; the hero and the theme switch both honour it |
| Contrast | Zero WCAG AA failures across every checked page/theme/viewport. `--text-muted` and `--accent-text` are explicitly tuned with ratios recorded in comments |
| Semantic HTML | All 18 routes have exactly one `<h1>`; no duplicate `id`s anywhere; 0 images missing `alt` |
| CLS prevention | Card images carry `width`/`height` from upload time; the first card is `fetchpriority="high"`, the rest lazy |
| Infinite-scroll parity | `app.js` rebuilds the exact server card markup (SVG icons, badges, aria-labels) rather than a cheaper variant |
| Progressive enhancement | Real `<a>` pagination for crawlers, plus a `next_cursor` sentinel for JS |
| Focus handling | One `:where(...):focus-visible` ring at zero specificity; skip link; drawer focus trap with Escape and focus return |
| Safe areas | `env(safe-area-inset-*)` on topbar, drawer, bottom nav and body |

**Conclusion: the visual language and the design system should not be replaced.**
The problems below are structural, not stylistic.

---

## 2. Findings

Severity: **S1** = blocks the brief, **S2** = real defect, **S3** = polish.

### S1-1 — The home page shows no content above the fold

Measured first-card position on `/en/`:

| Viewport | Hero height | Hero % of viewport | First card starts at | Visible above fold |
|---|---|---|---|---|
| 390×844 (phone) | 380px | **45%** | y = 822 | **22px** |
| 1280×720 (laptop) | 400px | **56%** | y = 708 | **12px** |
| 1440×900 | 400px | 44% | y = 708 | 192px |

The brief requires the site to behave like a social app on mobile/tablet, whose
defining property is that content is the first thing on screen. Currently the
order is: breadcrumb → `<h1>` → 400px decorative hero → feed tabs → suggested-users
rail → posts. On a phone that is 822px of chrome before the first post.

Worse, the hero is *mostly empty for most of its loop* — several animation phases
render an almost-black panel (visible in `home-mobile.png`), so it reads as a
loading state rather than a hero.

`home.html` and `motion-graphic.html`.

### S1-2 — `motion-graphic.html` is a whole HTML document included into another document

`home.html` does `{% include "web/motion-graphic.html" %}`, but that file starts
`<!doctype html>` and contains `<html>`, `<head>`, `<title>`, `<body>` **and a
duplicate `<link>` to the same Google Fonts URL**. Browsers recover (the nested
tags are dropped as parse errors, which is why the page looks fine), so this is
invisible in a screenshot — but it is invalid HTML, it ships a second full
`<style>` block into the middle of `<body>`, and any strict parser or HTML
sanitiser downstream inherits the problem.

### S1-3 — The hero duplicates the design system inline

The hero's inline `<style>` re-declares `--bg`, `--bg-elevated`, `--bg-card`,
`--accent`, `--border`, `--text`, `--shadow-2`, `--radius-lg`, `--sp-5` (and more)
in a hand-compressed copy of the tokens, and defines **24 `@keyframes`**. Retheming
now requires editing tokens in two places, which directly violates the
"retheming is a single edit" invariant the stylesheet states in its own header.

### S2-1 — Mobile/tablet tap targets below the 44px minimum

WCAG 2.5.5 (AAA) asks for 44×44; 2.5.8 (AA) asks for 24×24 with spacing. Measured
at 390×844:

| Control | Size | Where |
|---|---|---|
| `button.theme-toggle` | 56×**26** | every auth page, offline |
| `button.lang-btn` | 38×**30** | auth pages, offline |
| `a.btn` (Sign up) | 85×**38** | topbar on every page |
| `button.stat-btn` | 52×**40** | post cards (CSS explicitly sets 40px at ≤640) |
| `button.field-toggle` (password reveal) | **38×38** | login/signup |
| `a.field-forgot` | 113×**20** | login |
| `a.auth-link` | 51×**17** | login/signup/verify |
| `a.logo` | **28×28** | topbar ≤640 (wordmark hidden, so the hit area is the mark alone) |
| `a.post-card-title` | 318×**21** | every card |
| breadcrumb `a` | 34×**15** | category/tag/post/profile |

`app.css` already argues for 44px in `.bottom-link`; the same standard is not
applied to the rest.

### S2-2 — `app.js` cannot detect a 403, so "log in to like" is dead code

```js
.catch((err) => {
  if (err && err.status === 403) { …redirect to login… }
  else { toast(t("something_wrong")); }
});
```

The request helper rejects with `r.json()` — the parsed **body**, not the
`Response`. A Django JSON 403 body (`{"detail": "…"}`) has no `.status`, so the
branch can never fire. A signed-out visitor who taps Like gets "Something went
wrong" instead of being sent to log in. This is the most-used interaction on the
site.

### S2-3 — Video cards are an undefined black rectangle

`post_grid.html` and `app.js::buildCard` both render
`<video src=… muted preload="metadata" playsinline>` with **no `poster`**. Until
the browser has decoded a frame the card is a black box with a "VIDEO" chip. On the
home feed this is the second card a visitor sees.

Note: the two large media files that failed in the automated pass
(`Screen_Recording_…mp4` → `ERR_INVALID_HTTP_RESPONSE`, `Saghi.mp3` → `ERR_ABORTED`)
were re-checked with `curl` and return `200` / `206` correctly, so they are
navigation-abort artefacts of the audit, not a defect. Not reproduced.

### S2-4 — The auth surface is mid-migration and carries dead templates

Uncommitted work in this tree has moved auth onto `auth_base_new.html` +
`login_new.html` + `signup_new.html` + `verify_email.html`, and the password-reset
templates under `account/templates/account/` now extend the new base. The old
`templates/web/auth_base.html`, `login.html` and `signup.html` are left behind and
are **no longer referenced by any view** (`web/auth_views.py` renders only the
`_new` files). Two competing auth designs and two auth stylesheets
(`app.css` §19 + `auth.css`, 451 lines) are being shipped.

### S2-5 — `scroll-behavior: smooth` is set globally

`app.css:283` sets it on `html`, so *every* programmatic scroll — including the
skip link and any `scrollIntoView` — animates. It is correctly disabled under
`prefers-reduced-motion`, but it still makes the skip link and hash navigation
feel laggy for everyone else. This is why the audit's own `scrollTo(0,0)` kept
landing mid-page.

### S3-1 — Tablets get phone layout, phones get desktop density

The single 1024px breakpoint collapses the sidebar into the drawer and shows the
bottom nav. At 834×1112 (iPad portrait) the result is a phone UI in a large
window: one card per row, 720px capped content, and a very large empty gutter.
The audit found no *overflow* at any viewport (all 5 viewports pass with
`scrollWidth == clientWidth`), so this is a density problem, not a breakage.

### S3-2 — Small-phone behaviour at 320px

320×640 is the narrowest supported viewport and passes without horizontal scroll.
`a.btn` and the topbar controls get very tight; the topbar hides the language
button at ≤720 and the theme switch at ≤400, so at 320px the topbar has no theme
control at all (the drawer still does).

### S3-3 — Breadcrumbs duplicate the primary navigation

Every listing renders `Home / Categories / Coding` immediately above an `<h1>`,
directly under a bottom nav that already has Home. On a 390px screen that is a
21px-tall row of 15px-tall links costing 40px of the fold for no new information.

---

## 3. What the brief asks for, mapped to findings

| Brief requirement | Status | Finding |
|---|---|---|
| Fully responsive, all screen sizes | Passes (no overflow at 320–1440) | S3-1 tablet density |
| SEO-friendly | Already strong | — |
| Dynamic / interactive | Already strong | S2-2 dead 403 branch |
| Smooth professional animation | Strong system; one global overreach | S1-3, S2-5 |
| No conflict with the backend | Untouched so far | — |
| No heavy frameworks | Already vanilla | — |
| Bilingual preserved | Passes | — |
| Dark/light preserved | Passes | — |
| App-like on mobile/tablet | **Fails** | **S1-1**, S2-1, S3-1 |
| PWA correct | Mostly correct | see §4 |

## 4. PWA status

Correct: `manifest.webmanifest` has `id`, `scope`, `start_url`, `display` +
`display_override`, `orientation`, `theme_color`/`background_color` matching
`--bg`, an `any` **and** `maskable` icon pair at 192/512, `categories`, and four
`shortcuts`. `sw.js` precaches an explicit shell, version-names its caches, deletes
stale ones on activate, never caches `/admin/` or `/api/`, and never caches
`robots.txt` or the sitemap (with the reasoning recorded in a comment).

Gaps: the service worker is registered from `/static/sw.js`, so its **scope is
`/static/`** — `navigator.serviceWorker.register()` defaults `scope` to the
script's directory. A worker at `/static/sw.js` can only intercept requests under
`/static/`, which means the offline page fallback and the page cache in `sw.js`
can never run in production. The `fetch` handler's page branch is unreachable.
(This does not show up in local testing because the dev server serves the file at
that path and Chrome is permissive about scope during development.)

`sw.js` also precaches `/offline/` but `offline.html` is served by a view that
requires no auth — consistent. `theme.js`, `nav.js`, `player.js` are precached
but `create-form.js`, `studio.js`, `upload.js`, `profile-edit.js`, `auth.js` are
not, so those pages half-load offline.

---

## 5. Recommended fix order

1. **S1-2, S1-3** — split the hero into a real partial + move its CSS into `app.css` (mechanical, no visual change).
2. **S1-1** — rework home so content leads, and the hero becomes compact on small screens.
3. **S2-1** — raise tap targets to 44px under `pointer: coarse`.
4. **S2-2** — carry the HTTP status into the rejected error so the login redirect works.
5. **S2-3** — `poster` for video cards (+ `preload="none"` on the grid).
6. **S2-5** — scope smooth scrolling to intentional navigation only.
7. **S2-4** — retire the dead auth templates.
8. **PWA** — register the worker at `/` scope and align the precache list.
9. **S3-*** — tablet density, small-phone topbar, breadcrumb visibility.

Every item above is UI-layer only: no model, migration, view-signature, URL or API
change is required.
