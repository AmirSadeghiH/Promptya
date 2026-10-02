# Promptya — Keyword Strategy

**Date:** 2026-10-02
**Companion to:** `SEO_AUDIT.md` (technical state), `SEARCH_CONSOLE_SETUP.md` (submission).

> **Read this first.** Nothing below contains measured search volume, difficulty, or
> traffic forecasts. No keyword tool (Keyword Planner, Ahrefs, Semrush) was run and no
> such data was invented. Every priority is derived from what Promptya can *already*
> rank for with its real inventory, and every number that would need a tool is left
> explicitly blank. Fill the blanks from Search Console and a keyword tool before
> treating this as a plan rather than a hypothesis.

---

## 1. What Promptya actually is

A bilingual (EN/FA, RTL-aware) community where creators post **AI prompts** alongside the
**result** they produced with them — image, video, audio, or the prompt text alone. Users
browse, save, and remix.

This matters for targeting, because Promptya is not competing with prompt *libraries*.
Those sell prompt text. Promptya's differentiator is the **result**: the prompt *and* its
output side by side. That is the angle every keyword below is chosen to reinforce.

The site's structural facts that constrain this strategy:

- Only the **chrome** is machine-translated (nav, headings, metadata). Post bodies are the
  author's own words and are **not** translated between EN and FA. So EN and FA pages
  compete for the same underlying content — see §5.
- Inventory that can rank is bounded by what exists: posts, categories, tags, creators.
- Categories and tags are seed/user data, not an editorial taxonomy. §6 covers why that
  constrains the plan.

---

## 2. Priority tiers

### Tier 1 — Head terms (site-wide, homepage/Explore)

The terms a new visitor types when they want the thing, not when they want this site.

| EN | FA (informal) | Target URL | Why here |
|---|---|---|---|
| ai prompts | پرامپت هوش مصنوعی | `/en/`, `/fa/` | Category-defining, not brand-defining |
| ai prompt generator | — | `/studio/` | Only page that matches "generator" |
| image prompts | پرامپت تصویر | `/category/<image>/` | Highest-volume media type |
| video prompts | پرامپت ویدیو | `/category/<video>/` | Same intent, narrower |
| free ai prompts | پرامپت رایگان | `/en/explore/` | Free is the dominant modifier |
| prompt engineering | — | `/category/`, `/explore/` | Adjacent professional interest |

**Intent check:** every Tier 1 term is served by a page whose *visible content* matches.
The homepage is a feed, which is the right shape for these.

### Tier 2 — Category × medium (category pages)

`{medium} prompts` is the highest-leverage pattern available, because Promptya has a real
page per category and real posts under each. These pages are already
`CollectionPage` + `ItemList` in JSON-LD with breadcrumbs — the page is *built* for this.

| EN pattern | FA pattern | Count of matching categories |
|---|---|---|
| `photography prompts` | پرامپت عکاسی | fill in from seed data |
| `portrait prompts` | پرامپت پرتره | " |
| `cinematic prompts` | پرامپت سینمایی | " |
| `product prompts` | پرامپت محصول | " |
| `logo prompts` | — | " |
| `illustration prompts` | پرامپت تصویرسازی | " |

**Do not invent these.** Map them to categories that actually exist and have
`public_post_count >= 1`. A category page for a category with no posts is `noindex` by
design and will not rank regardless of how good the keyword is.

> The table above is a *pattern*, not an inventory. The authoritative list is the
> `Category` rows; the actual per-category thresholds live in
> `posts.models.Category.is_indexable`.

### Tier 3 — Post-level long tail (the real volume)

Most of Promptya's addressable search demand is here, and it is **unbounded in principle**
because every post is a distinct creative artefact with its own title, description, prompt
text, and tags.

Shape: `{style/subject} + {medium} + prompt`, e.g. `neon rain cyberpunk portrait prompt`,
`minimalist product photo prompt`, `cinematic lighting prompt`.

These are won by:
- a post title built from the author's own words (`test_a_post_title_is_built_from_the_authors_own_words`),
- the WebP/width/height/`fetchpriority` treatment that keeps LCP fast on mobile,
- `CreativeWork` structured data tying the work to its `Person`.

**Action, not analysis:** the single highest-leverage SEO work left is not keyword
research, it is making sure creator posts get written with descriptive titles and are
tagged. Every post already indexed is a long-tail result waiting to be found.

### Tier 4 — Tag pages (longest tail, lowest volume)

`/tag/<slug>/` exists, is linked from post detail (as crawlable `<a>`, not inert chips),
carries breadcrumbs + `ItemList`, and goes `noindex` below **2** posts
(`MIN_INDEXABLE_COLLECTION_ITEMS`).

Tag pages should be treated as **supporting**, not as a traffic strategy. Their job is to
capture long-tail variants of Tier 2/3 (`portrait`, `cinematic`, `35mm`) and to give those
terms a crawlable, indexable node. Do not spend effort naming or curating tags for their
own sake.

---

## 3. Deliberate exclusions

These were considered and rejected, with reasons:

| Rejected | Why |
|---|---|
| "AI art generator", "image generator" | High volume, but the intent is *a tool*, not *examples*. Promptya's `/studio/` is a real tool but a secondary surface; ranking the term on a feed page would be a mismatch. Revisit only if Studio becomes the product. |
| "chatgpt prompts", "midjourney prompts" | Brand terms of third parties. Targeting them invites both a relevance penalty and a legal/brand problem, and Promptya is multi-tool, not a single vendor's community. |
| "prompt generator free" (the "free" modifier on tools) | Same mismatch as above. |
| Volume/difficulty/KD numbers | Would have to be invented. Left blank on purpose. |
| Keyword-stuffed category/description copy | Category descriptions are generated from real post counts (`test_a_category_description_counts_real_posts`). Writing marketing copy there would mean the description stops describing the page, which is the thing §5 of the audit already fixed. |

---

## 4. Titles and descriptions as the SERP surface

The title and description are the highest-leverage on-page elements and they are already
generated, clamped, and tested (`web/test_seo.py::MetadataTests`):

- `<title>` is clamped to `seo.TITLE_LIMIT`, description to `seo.DESCRIPTION_LIMIT`.
- Both languages are genuinely different strings (`test_the_two_languages_have_different_titles`).
- Post titles come from the author's own words, never a template that keyword-stuffs a
  category name into every post.

**Operating rule:** when a page's title or description reads wrong in the SERP, fix the
*data* (the post title, the category name), not the template. A template-level keyword
edit would fight the audit's rule that descriptions describe the actual page.

---

## 5. The EN/FA overlap problem (important, and unresolved)

Because post bodies are **not** machine-translated, the EN and FA versions of a post differ
only in chrome — nav, headings, `hreflang`, `og:locale`. The *content* is identical.

This means:

- `/en/post/12/` and `/fa/post/12/` are near-duplicates to a crawler, distinguished only by
  `hreflang`.
- Google will pick one as canonical and keep the other out of the index unless a real
  Persian-speaking audience consistently prefers the FA version. `hreflang` is the correct
  signal and is implemented reciprocally with `x-default`, but it is a *request*, not a
  guarantee.

**Do not "fix" this by translating post bodies.** Machine-translating creative prompts
would change what the page is — a prompt is meant to be copied verbatim, and a translated
prompt is a different prompt that produces different output. The audit's §8.7
(per-post language variants, authored by a human who writes both) is the only honest path,
and it needs a product decision, not an SEO one.

**What to watch:** Search Console's international targeting report (§ "Common causes" in
`SEARCH_CONSOLE_SETUP.md`) is the signal for whether the split is working. If FA pages
never get impressions, the overlap is winning and the content-side work is worth raising
with the product owner.

---

## 6. Why there is no "SEO content" plan here

A common play is to manufacture a blog, a glossary, or a "best prompts" hub. That was
deliberately not done, and the audit records it as a rejected option.

The reason is specific to Promptya's inventory:

- A blog would be thin pages competing with the real thing. The site's own indexability
  rules (`MIN_INDEXABLE_COLLECTION_ITEMS`) exist precisely to keep thin pages out.
- Publishing filler to capture keywords is the behaviour those rules exist to prevent. Doing
  it deliberately would make the rules theatre.
- The site's actual competitive advantage — real prompts with real outputs — is not
  something a content calendar manufactures.

**If content marketing is wanted later,** it should be editorial about *using* prompts
(live written by someone who used them), not a keyword list. That is a product/content
decision to make explicitly, with the indexability rules still applying to whatever it
produces.

---

## 7. Measurement plan

There are no traffic forecasts here because there are no measurements yet. What to do:

1. Submit the property and sitemap (`SEARCH_CONSOLE_SETUP.md`).
2. Leave it 4–6 weeks. A new bilingual domain will have almost no data before then; any
   judgement made sooner is noise.
3. Fill in the gaps in §2 from real query data:
   - Search Console → Performance → Queries, filtered per language property/filter.
   - Note which **languages** actually produce impressions (see §5).
   - Note which of Tier 2's patterns returns real queries for categories that exist.
4. Only then pick Tier 2/3 work. Priority should be assigned by *observed impressions on
   pages that already exist and are already indexable* — not by estimated volume.

**Metrics worth watching, in order of honesty:**

| Metric | Where | What it actually tells you |
|---|---|---|
| Indexed pages vs. submitted | Search Console → Pages | Whether the technical work held |
| Crawl errors / dropped | Search Console → Pages | Whether the sitemap or server is at fault |
| Average position per template | Search Console → Performance, grouped by `/category/`, `/post/`, `/tag/` | Which *page type* works, before which keyword |
| Query → page mapping | Search Console → Performance | The only source of real demand data this strategy lacks |
| Core Web Vitals | Search Console → Experience | Whether §7 of the audit's recommendations matter yet |

---

## 8. Open items requiring a decision

1. **Per-post language variants** (§5) — needs a `Post` language field and community
   willingness to author both. Without it, FA demand is partly wasted.
2. **Whether Studio or the feed is the product.** Tier 1 targets the feed; if Studio becomes
   primary, the "generator" terms change from rejected to central.
3. **Third-party brand terms** (§3) — currently rejected. Revisit only with a decision
   about how the brand positions against Midjourney/ChatGPT/etc.
4. **Category taxonomy.** Seed data is the limiting factor on Tier 2. Whether categories
   are curated, user-created, or both changes which Tier 2 patterns are reachable at all.