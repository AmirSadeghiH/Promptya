# Promptly — AI Prompt Community

A social network for AI prompts. Users share prompts, generated images and videos,
discover trending content, follow creators, save and remix.

Dark · Premium · Minimal — the mood of Pinterest, X, Product Hunt, Linear and
Dribbble, distilled into its own design system.

## Stack

- **Backend:** Django 6.1 (Python 3.12), SQLite for dev, session auth, JSON APIs
- **Frontend:** Server-rendered Django templates + vanilla JS/CSS (no build step)
- **PWA:** manifest + service worker (offline shell, cached static/media)
- **Static/media:** WhiteNoise for static, Django media for uploads

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (source .venv/bin/activate on macOS/Linux)
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo      # optional: demo users/posts/likes
python manage.py runserver
```

Open http://127.0.0.1:8000 — demo accounts: `demo_nova` … `demo_orbit`,
password `demo-password-123`. Admin: create one with `python manage.py createsuperuser`.

## Apps

| App | Purpose |
|---|---|
| `account` | Custom user, profile, signup/login/logout, follow counts, saved posts |
| `posts` | Post/Category/Tag models, CRUD API, feeds, trending ranking, search, explore |
| `interactions` | Like, Save, Comment, Follow, View & Copy events + APIs |
| `notifications` | Notification model, signals on like/save/comment/follow, read/unread API |
| `imagegen` | AI image studio: provider adapter, generation records, prompt library, generate API |
| `credits` | Credit wallet + ledger, reward challenges, referral attribution, claim API |
| `web` | Server-rendered frontend pages (feed, explore, search, detail, create, studio, profile, notifications) |

## API overview (all JSON, under `/api/`)

**Feeds & discovery** — `GET /api/posts/feed/latest|following|trending/`,
`GET /api/posts/explore/`, `GET /api/posts/search/?q=…&type=…&category=…&tag=…&ai_model=…`,
`GET /api/posts/categories/`, `GET /api/posts/categories/<slug>/`, `GET /api/posts/tags/`

**Posts** — `POST /api/posts/create/`, `GET /api/posts/<id>/`,
`PATCH|PUT /api/posts/<id>/update/`, `DELETE /api/posts/<id>/delete/`
(cursor pagination with `page_size` 1–50 and opaque `cursor`)

**Interactions** — `POST /api/posts/<id>/view|copy|like|save/`,
`GET /api/posts/<id>/comments/`, `POST /api/posts/<id>/comments/create/`,
`DELETE /api/posts/comments/<id>/delete/`, `POST /api/posts/users/<username>/follow/`

**Account** — `POST /api/auth/signup|login|logout/`, `GET /api/auth/me/`,
`PATCH /api/me/update/`, `GET /api/me/saved/`, `GET /api/users/<username>/`

**Notifications** — `GET /api/notifications/`, `POST /api/notifications/read-all/`,
`POST /api/notifications/<id>/read/`

**AI studio & credits** — `POST /api/ai/generate/` (JSON, or `multipart/form-data`
with `source_image` for image-to-image), `POST /api/credits/challenges/<slug>/claim/`

## AI studio, credits and rewards

The studio (`/studio/`) closes the product loop:

```
Discover → Use prompt → Generate / remix → Save → Earn credits → Generate again
```

- **Use prompt.** Every public image post with a prompt carries a "Use prompt"
  action linking to `/studio/?source=<post id>`, which pre-fills the prompt and
  remembers the source post so the generated image links back to it.
- **Text-to-image and image-to-image.** The composer takes an optional reference
  image (validated exactly like any other upload: extension, size cap, magic
  bytes, MIME, full Pillow decode and a dimension cap). With one attached, the
  request goes out as `images.edit`; without, as `images.generate`. Both paths
  live behind `imagegen/client.py`, so swapping provider means editing one file.
- **Provider settings** (base URL, API key, model, size, timeout, credit price)
  are a single admin-edited row (`imagegen.AIConfig`). The credit price is
  configurable per provider/model.
- **Credits.** New accounts open with **200 credits** and a standard generation
  costs **80** (both configurable). Every movement is an immutable row in the
  credit ledger — `generation`, `reward`, `refund`, `adjustment` — and the
  balance can never go negative: a charge is a single guarded SQL `UPDATE`, so
  concurrent requests cannot overdraw it. A failed generation refunds itself.
- **Challenges.** Rewards are verified, never click-based. Seeded examples:
  invite a friend (paid once that friend completes their *first* generation,
  via `?ref=<username>` at signup) and share a generated image on Instagram
  (requires a real post link and an existing generation). New challenges are a
  row plus a function in `credits/challenges.py::VERIFIERS`.

## Design system

- Colors: near-black surfaces (`#0a0a0f` → `#14141c`), violet accent `#8b7cf6`,
  semantic like-red / save-gold, 8% white borders.
- Typography: Inter for UI, JetBrains Mono for prompt text.
- **Dark/light theme:** animated sun/moon toggle in the top bar; persists via `localStorage` + `promptly-theme` cookie, respects `prefers-color-scheme`, and swaps `theme-color` metas. Full light palette lives in `static/css/app.css` under `:root[data-theme="light"]`.
- **Bilingual (EN/FA):** top-bar language button toggles English ⇄ فارسی without a reload. Server renders pages from the `promptly-lang` cookie (`web/context_processors.py`, strings in `web/i18n_strings.py`); `static/js/i18n.js` re-applies strings live, flips `dir` to RTL, and swaps to the Vazirmatn typeface. Mixed-direction content (usernames, prompts) is isolated with `dir="auto"` / `unicode-bidi: plaintext`.
- Desktop: sticky top bar + left sidebar (nav + categories) + 4-column masonry.
- Mobile/PWA: single-column cards, top bar with search, floating create button,
  bottom tab bar (Home / Explore / ＋ / Saved / Profile), safe-area aware.

## Testing

```bash
python manage.py test
```

Covers feeds & ranking, cursor pagination, query-count (N+1) guards, search,
post CRUD + permissions, like/save/comment/follow toggles, notifications
(signals + API), auth and profiles — plus media validation, credit charging /
refunds / concurrent-charge safety, image-to-image uploads, the "Use prompt"
flow and referral rewards.

## Production

Set env vars: `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=false`,
`DJANGO_ALLOWED_HOSTS=yourdomain.com`, `DJANGO_CSRF_TRUSTED_ORIGINS=https://yourdomain.com`.
Then `python manage.py collectstatic` and serve behind HTTPS (HSTS, secure cookies and
SSL redirect are enabled automatically when `DEBUG=false`). Serve `MEDIA_ROOT`
from a CDN/object store for scale; swap SQLite for Postgres when needed.

## Roadmap status (MVP)

| Area | Status |
|---|---|
| 1. Account | ✅ API, views, admin, tests |
| 2. Posts | ✅ CRUD API, media fields, admin |
| 3. Interactions | ✅ Like/Save/Comment/Follow APIs |
| 4. Feed & Discovery | ✅ (was already done) |
| 5. Search | ✅ title/prompt/description/tags/category/AI model/creator |
| 6. Notifications | ✅ app, signals, read/unread API |
| 7. APIs & Admin | ✅ all models registered, full JSON surface |
| 8. Frontend | ✅ dark premium minimal, desktop + mobile layouts |
| 9. PWA | ✅ manifest, service worker, offline page, installable |
| 10. Testing & Deploy | ✅ test suite + env-based production settings |
| 11. AI Studio | ✅ prompt library, text-to-image + image-to-image, "Use prompt" from image posts |
| 12. Credits & Rewards | ✅ configurable price, atomic ledger, refunds, verified challenges, referrals |
