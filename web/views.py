"""Server-rendered pages, and the two documents crawlers read directly.

The views stay thin: a view resolves the object, decides whether it is
indexable, and hands the page everything the template needs — including the
titles, descriptions, canonical URL and structured data, which are **computed
here** rather than assembled in the template.  That is what makes the SEO
surface assertable in a unit test instead of only visible in rendered HTML.
"""

from django.contrib.auth import get_user_model
from django.contrib.sitemaps.views import sitemap as django_sitemap
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.urls import reverse

from credits.challenges import INVITE_FRIEND, challenge_state
from imagegen.models import AIConfig
from imagegen.services import (
    MAX_PROMPT_LENGTH,
    credit_payload,
    prompt_library,
    recent_generations,
)
from interactions.models import Follow, Save
from notifications.models import Notification
from notifications.services import serialize_notification, unread_count
from posts.models import Category, Post, Tag
from posts.recommendations import get_recommended_feed, get_suggested_users
from posts.services import (
    get_explore_data,
    get_following_feed,
    get_latest_feed,
    get_trending_feed,
    post_list_queryset,
    search_posts,
    serialize_post,
)
from web import seo
from web.i18n_strings import STRINGS
from web.middleware import mark_noindex, noindex
from web.sitemaps import SITEMAPS

#: Posts rendered on a creator profile. The *count* shown in metadata comes from
#: a real aggregate, not from ``len()`` of this page, so a capped list never
#: misreports a creator's output.
PROFILE_POST_LIMIT = 24

#: Posts per HTML listing page. Cursor pagination stays in the JSON API; HTML
#: pages need real ``<a href>`` links so page 2+ is reachable without JavaScript.
LISTING_PAGE_SIZE = 24


def _viewer(request):
    return request.user if request.user.is_authenticated else None


# ---------------------------------------------------------------------------
# Shared context
# ---------------------------------------------------------------------------


def seo_labels(request):
    """SEO strings for the current render language."""
    return seo.seo_strings(seo.active_language(request))


def _meta_context(request, *, title, description, robots=None, og_type="website",
                  og_image=None, og_image_alt=None, og_image_dims=True, listing_items=None):
    """The metadata every page needs, derived once.

    ``title``/``description`` arrive already clamped by the caller (or are
    clamped here), so no template can emit an over-length tag.  The canonical URL
    is the language-addressed, query-free version of the current path.

    ``listing_items`` are the member paths of a collection page.  When present the
    page also gets a ``CollectionPage`` + ``ItemList`` node, which is the
    machine-readable counterpart of the ``<a>`` links the grid already renders and
    gives search engines an explicit statement of what the page is a list *of*.
    """
    labels = seo_labels(request)
    context = {
        "seo_title": seo.clamp_title(title),
        "seo_description": seo.clamp_description(description),
        "canonical_url": seo.canonical_url(request),
        "robots_meta": robots or seo.ROBOTS_INDEX,
        "og_type": og_type,
        "og_image": og_image or "",
        "og_image_alt": og_image_alt or labels["site_name"],
        "og_image_dims": og_image_dims,

        # The social card for a page with no image of its own. Resolved here
        # rather than in the template because it needs the request origin and
        # {% static %} output in the same expression, which no template tag can
        # express: `{% abs_media request %}{% static … %}` passes the *request*
        # as the media path, which renders as
        # "https://host/<WSGIRequest: GET '/…'>/static/icons/icon-512.png".
        # Scrapers reject that outright, so every page with no og:image of its
        # own was emitting a broken one.
        "default_og_image": seo.absolute_media_url(static("icons/icon-512.png"), request),

        # Template-side SEO copy (breadcrumb labels, pagination text, the
        # "this profile is kept out of the index" note). One lookup per page
        # instead of a per-string language branch in every template.
        "seo_labels": labels,
    }
    if listing_items:
        context["collection_page_node"] = _collection_node(
            request,
            name=seo.clamp_title(title),
            description=seo.clamp_description(description),
            items=listing_items,
        )
    return context


def _collection_node(request, *, name, description, items):
    """``CollectionPage`` tying the page's ``WebPage`` shell to its ``ItemList``."""
    canonical = seo.canonical_url(request)
    return [
        seo.web_page_node(
            request, name=name, description=description, breadcrumb_id=f"{canonical}#breadcrumb"
        ),
        {
            "@type": "CollectionPage",
            "@id": f"{canonical}#collectionpage",
            "url": canonical,
            "name": name,
            "description": description,
            "inLanguage": seo.active_language(request),
            "isPartOf": {"@id": f"{seo.absolute_path('/', request)}#website"},
            "mainEntity": {"@id": f"{canonical}#itemlist"},
        },
        seo.item_list_node(request, items),
    ]


def _base_context(request):
    context = {
        "categories": Category.objects.all(),
        "unread_notifications": 0,
    }
    if request.user.is_authenticated:
        context["unread_notifications"] = unread_count(request.user)
    return context


def _language_alternate_path(name, *args):
    """Path of *name* in the reader's own language (already language-prefixed).

    ``reverse`` resolves against the active language, so a Persian reader gets
    ``/fa/…`` from every internal link without a single template having to know
    the site is bilingual.
    """
    return reverse(name, args=args)


def _crumbs_context(request, crumbs):
    """The visible breadcrumb trail and its ``BreadcrumbList`` node.

    Both come from one list, so the structured data and the rendered trail can
    never disagree about a name or a destination.  The node is built here rather
    than in a template tag because a Django ``simple_tag`` cannot be passed as an
    argument to another one — the inner name resolves as a context variable, so
    ``{% seo_jsonld … seo_breadcrumb_jsonld crumbs %}`` would silently emit the
    raw crumbs into ``@graph`` instead of the node built from them.
    """
    return {
        "crumbs": crumbs,
        "breadcrumb_node": (
            seo.breadcrumb_node(request, [(crumb["name"], crumb["path"]) for crumb in crumbs])
            if crumbs
            else None
        ),
    }


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


def _requested_page(request):
    """1-based page number from ``?page=``, rejecting junk with a 404."""
    raw = request.GET.get("page", "1")
    try:
        page = int(raw)
    except (TypeError, ValueError):
        raise Http404("Invalid page number.") from None
    if page < 1:
        raise Http404("Invalid page number.")
    return page


def _paginate(request, queryset, page_size=LISTING_PAGE_SIZE):
    """Offset pagination for HTML listings.

    Returns ``(page_object, has_next, next_page_number)``.  A page past the end
    is a 404, never an empty 200 — an empty listing at a valid-looking URL is the
    soft 404 pattern that gets whole sections de-indexed.
    """
    paginator = Paginator(queryset, page_size)
    try:
        page = paginator.page(_requested_page(request))
    except PageNotAnInteger:
        raise Http404("Invalid page number.") from None
    except EmptyPage:
        raise Http404("Page out of range.") from None
    has_next = page.has_next()
    return page, has_next, (page.number + 1 if has_next else None)


def _page_query(page_number):
    return f"?page={page_number}"


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


def home(request):
    viewer = _viewer(request)
    user = request.user if request.user.is_authenticated else None
    page = get_recommended_feed(user=user, page_size=12, viewer=viewer)
    labels = seo_labels(request)
    context = {
        **_base_context(request),
        **_meta_context(
            request,
            title=labels["home_title"],
            description=labels["home_description"],
        ),
        **_crumbs_context(request, _crumbs_home(labels)),
        "posts": page["results"],
        "next_cursor": page["next_cursor"],
        "feed_tab": "foryou",
        "is_recommended": user is not None,
        "suggested_users": get_suggested_users(user=user),
        "seo_h1": labels["home_h1"],
    }
    return render(request, "web/home.html", context)


def _crumbs_home(labels):
    return [{"name": labels["breadcrumb_home"], "path": _language_alternate_path("web:home")}]


def feed_page(request, feed):
    """The ``/feed/<variant>/`` listings.

    All three are ``noindex``: "following" is personalised, and "latest" /
    "trending" duplicate what home and explore already surface.  They are still
    crawlable and linked so the crawl budget reaches the posts behind them.
    """
    if feed == "following" and not request.user.is_authenticated:
        return redirect("login")

    feed_map = {
        "latest": get_latest_feed,
        "following": get_following_feed,
        "trending": get_trending_feed,
    }
    if feed not in feed_map:
        # An unknown feed variant is a broken URL, not a synonym for the home
        # page: a 302 here turns every typo into a soft duplicate of "/".
        raise Http404(f"Unknown feed: {feed}")

    viewer = _viewer(request)
    feed_fn = feed_map[feed]
    if feed == "following":
        page = feed_fn(request.user, page_size=12, viewer=viewer)
    else:
        page = feed_fn(page_size=12, viewer=viewer)

    labels = seo_labels(request)
    # The feed's own name, in the reader's language, for the H1 and the title.
    tab_label = STRINGS[seo.active_language(request)][feed]

    context = {
        **_base_context(request),
        **_meta_context(
            request,
            title=f"{tab_label} · Promptya",
            description=labels["site_description"],
            robots=seo.ROBOTS_NOINDEX_FOLLOW,
        ),
        **_crumbs_context(request, _crumbs_home(labels)),
        "posts": page["results"],
        "next_cursor": page["next_cursor"],
        "feed_tab": feed,
        "seo_h1": labels["feed_h1_fmt"].format(tab=tab_label),
    }
    return mark_noindex(render(request, "web/feed.html", context))
def explore_page(request):
    explore = get_explore_data(viewer=_viewer(request))
    labels = seo_labels(request)
    listing_items = [
        _language_alternate_path("web:post-detail", post["id"]) for post in explore["trending"]
    ]
    context = {
        **_base_context(request),
        **_meta_context(
            request,
            title=labels["explore_title"],
            description=labels["explore_description"],
            listing_items=listing_items,
        ),
        **_crumbs_context(
            request,
            _crumbs_home(labels)
            + [{"name": labels["breadcrumb_explore"], "path": _language_alternate_path("web:explore")}],
        ),
        "explore": explore,
        "seo_h1": labels["breadcrumb_explore"],
        "seo_intro": labels["explore_intro"],
    }
    return render(request, "web/explore.html", context)



@noindex(seo.ROBOTS_NOINDEX_FOLLOW)
def search_page(request):
    query = (request.GET.get("q") or "").strip()
    results = []
    if query:
        results = search_posts(query, page_size=LISTING_PAGE_SIZE, viewer=_viewer(request))["results"]
    labels = seo_labels(request)
    # Every ?q= is a thin duplicate of the search page itself, so the canonical
    # is the bare path.  The title still names the query, because a user who
    # searched deserves to see what they searched for.
    context = {
        **_base_context(request),
        **_meta_context(
            request,
            title=labels["search_results_title_fmt"].format(query=query)
            if query
            else labels["search_title"],
            description=labels["search_description"],
            robots=seo.ROBOTS_NOINDEX_FOLLOW,
        ),
        "query": query,
        "results": results,
        # Already-translated UI string: "Results for “{query}”" / «…».
        "seo_h1": STRINGS[seo.active_language(request)]["results_for"].format(query=query)
        if query
        else labels["search_title"],
        **_crumbs_context(request, _crumbs_home(labels)),
    }
    return render(request, "web/search.html", context)


def category_page(request, slug):
    category = get_object_or_404(Category, slug=slug)
    viewer = _viewer(request)
    queryset = post_list_queryset(viewer).filter(category=category)
    page, has_next, next_page = _paginate(request, queryset)
    labels = seo_labels(request)

    count = queryset.count()
    indexable = category.is_indexable
    own_text = " ".join((category.description or "").split())
    if own_text:
        description = seo.clamp_description(f"{own_text} {labels['listing_count_fmt'].format(count=count)}")
    else:
        description = labels["category_description_fmt"].format(name=category.name, count=count)

    category_path = _language_alternate_path("web:category", category.slug)
    listing_items = [_language_alternate_path("web:post-detail", post.pk) for post in page.object_list]
    context = {
        **_base_context(request),
        **_meta_context(
            request,
            title=labels["category_title_fmt"].format(name=category.name),
            description=description,
            robots=seo.ROBOTS_INDEX if indexable else seo.ROBOTS_NOINDEX_FOLLOW,
            listing_items=listing_items,
        ),
        "category": category,
        "posts": [serialize_post(post, viewer=viewer) for post in page.object_list],
        "post_count": count,
        "has_next_page": has_next,
        "next_page": next_page,
        "page_query": _page_query(page.number) if page.number > 1 else "",
        "current_page": page.number,
        "seo_h1": labels["category_h1_fmt"].format(name=category.name),
        "seo_intro": labels["category_intro_fmt"].format(name=category.name),
        "seo_empty": labels["category_empty"],
        **_crumbs_context(
            request,
            _crumbs_home(labels)
            + [
                {
                    "name": labels["breadcrumb_categories"],
                    "path": _language_alternate_path("web:explore"),
                },
                {"name": category.name, "path": category_path},
            ],
        ),
    }
    response = render(request, "web/category.html", context)
    return response if indexable else mark_noindex(response)


def tag_page(request, slug):
    """A tag hub: every public post carrying *slug*.

    New page, and the reason tags are now links.  Previously ``#tag`` chips on a
    post were inert ``<span>``s — visible text with no crawlable destination, so
    the tag dimension of the site was invisible to crawlers even though the data
    and the search filter already existed.
    """
    tag = get_object_or_404(Tag, slug=slug)
    viewer = _viewer(request)
    queryset = post_list_queryset(viewer).filter(tags=tag)
    page, has_next, next_page = _paginate(request, queryset)
    labels = seo_labels(request)

    count = queryset.count()
    indexable = tag.is_indexable
    tag_path = _language_alternate_path("web:tag", tag.slug)
    listing_items = [_language_alternate_path("web:post-detail", post.pk) for post in page.object_list]
    context = {
        **_base_context(request),
        **_meta_context(
            request,
            title=labels["tag_title_fmt"].format(tag=tag.name),
            description=labels["tag_description_fmt"].format(tag=tag.name, count=count),
            robots=seo.ROBOTS_INDEX if indexable else seo.ROBOTS_NOINDEX_FOLLOW,
            listing_items=listing_items,
        ),
        "tag": tag,
        "posts": [serialize_post(post, viewer=viewer) for post in page.object_list],
        "post_count": count,
        "has_next_page": has_next,
        "next_page": next_page,
        "page_query": _page_query(page.number) if page.number > 1 else "",
        "current_page": page.number,
        "seo_h1": labels["tag_h1_fmt"].format(tag=tag.name),
        "seo_intro": labels["tag_intro_fmt"].format(tag=tag.name),
        "seo_empty": labels["tag_empty"],
        **_crumbs_context(
            request,
            _crumbs_home(labels)
            + [
                {"name": labels["breadcrumb_explore"], "path": _language_alternate_path("web:explore")},
                {"name": f"#{tag.name}", "path": tag_path},
            ],
        ),
    }
    response = render(request, "web/tag.html", context)
    return response if indexable else mark_noindex(response)


def post_detail_page(request, pk):
    viewer = _viewer(request)
    post = get_object_or_404(post_list_queryset(viewer), pk=pk)
    data = serialize_post(post, viewer=viewer)
    labels = seo_labels(request)

    # --- Metadata -------------------------------------------------------
    # Built from the author's own words first, with a translated scaffold only
    # as a fallback, so a post never ships a title or description invented by the
    # template.  Nothing private is exposed: `description`/`prompt` are public
    # fields, and an unindexable post gets noindex instead of a fabricated tag.
    body = post.meaningful_text
    type_label = labels[f"post_type_{post.post_type}"]
    if body:
        description = seo.clamp_description(
            labels["post_description_fmt"].format(text=f"{body} ", author=post.author.username)
        )
    else:
        description = labels["post_fallback_fmt"].format(type=type_label, author=post.author.username)

    title = (
        labels["post_title_prompt_fmt"]
        if post.post_type == Post.PostType.PROMPT
        else labels["post_title_fmt"]
    ).format(title=post.title, author=post.author.username)

    indexable = post.is_indexable
    og_image = seo.absolute_media_url(post.seo_image.url, request) if post.seo_image else ""

    # --- Contextual internal links --------------------------------------
    # Same category, then same tags, de-duplicated and excluding this post.
    related_ids = (
        post_list_queryset(viewer)
        .filter(category=post.category)
        .exclude(pk=post.pk)
        .values_list("pk", flat=True)[:6]
    )
    related = list(post_list_queryset(viewer).filter(pk__in=list(related_ids)))
    related = [serialize_post(item, viewer=viewer) for item in related]

    category_path = _language_alternate_path("web:category", post.category.slug)
    context = {
        **_base_context(request),
        **_meta_context(
            request,
            title=title,
            description=description,
            robots=seo.ROBOTS_INDEX if indexable else seo.ROBOTS_NOINDEX_FOLLOW,
            og_type="article",
            og_image=og_image,
            og_image_alt=post.title,
            # A user upload's aspect ratio is unknown until the file is read;
            # asserting the icon's 512x512 would be a lie.
            og_image_dims=not og_image,
        ),
        "post": data,
        "post_model": post,
        "related_posts": related,
        "related_count": len(related),
        "seo_h1": post.title,
        **_crumbs_context(
            request,
            _crumbs_home(labels)
            + [
                {
                    "name": labels["breadcrumb_categories"],
                    "path": _language_alternate_path("web:explore"),
                },
                {"name": post.category.name, "path": category_path},
                {"name": post.title, "path": _language_alternate_path("web:post-detail", post.pk)},
            ],
        ),
        "seo_jsonld_nodes": _post_jsonld(request, post, description),
    }
    response = render(request, "web/post_detail.html", context)
    return response if indexable else mark_noindex(response)


def _post_jsonld(request, post, description):
    """``WebPage`` + ``CreativeWork`` + ``Person``, tied together by ``@id``.

    Counts are read from the same aggregates the page renders, so the structured
    data can never claim engagement the visible page does not show.  There is
    deliberately no ``aggregateRating`` and no ``review``: Promptya has no
    rating system, and inventing one would be a manual action against Google's
    structured-data policy.
    """
    canonical = seo.canonical_url(request)
    work = {
        "@type": "CreativeWork",
        "@id": f"{canonical}#creativework",
        "url": canonical,
        "headline": post.title,
        "description": description,
        "datePublished": post.created_at.isoformat(),
        "dateModified": post.updated_at.isoformat(),
        "inLanguage": seo.active_language(request),
        "author": {
            "@id": f"{seo.absolute_path(reverse('web:profile', args=[post.author.username]), request)}#person"
        },
        "isPartOf": {"@id": f"{seo.canonical_url(request)}#webpage"},
    }
    if post.seo_image:
        work["image"] = seo.absolute_media_url(post.seo_image.url, request)
    if post.meaningful_text:
        work["abstract"] = seo.clamp(post.meaningful_text, 600)
    if post.ai_model:
        work["about"] = {"@type": "Thing", "name": post.ai_model}
    if post.category_id:
        work["genre"] = post.category.name
    if post.like_count or post.comment_count:
        work["interactionStatistic"] = [
            {
                "@type": "InteractionCounter",
                "interactionType": "https://schema.org/LikeAction",
                "userInteractionCount": post.like_count,
            },
            {
                "@type": "InteractionCounter",
                "interactionType": "https://schema.org/CommentAction",
                "userInteractionCount": post.comment_count,
            },
        ]
    page = seo.web_page_node(
        request,
        name=post.title,
        description=description,
        breadcrumb_id=f"{canonical}#breadcrumb",
    )
    page["mainEntity"] = {"@id": f"{canonical}#creativework"}
    return [page, work, seo.person_node(request, post.author)]


@noindex(seo.ROBOTS_NOINDEX_NOFOLLOW)
def create_post_page(request):
    context = _base_context(request)
    context["category_options"] = Category.objects.all()
    labels = seo_labels(request)
    context.update(
        _meta_context(
            request,
            title=labels["create_title"],
            description=labels["create_description"],
            robots=seo.ROBOTS_NOINDEX_NOFOLLOW,
        )
    )
    return render(request, "web/create.html", context)


def _studio_prefill(request):
    """A prompt handed to the studio by a post's "Use prompt" action.

    ``?source=<post id>`` is preferred over a raw ``?prompt=`` because it also
    preserves the link back to the post the prompt came from.

    The source lookup goes through ``post_list_queryset`` — the same visibility
    rule the post page itself uses — so the studio can never surface a post the
    viewer is not allowed to see, or echo its title and author into the page.
    """
    raw_prompt = (request.GET.get("prompt") or "").strip()
    source_id = (request.GET.get("source") or "").strip()
    post = None
    if source_id.isdigit():
        # No `.only()` here: `post_list_queryset` already select_relateds
        # `category`, and narrowing the field list on top of that defers a field
        # the queryset traverses, which Django rejects outright.
        post = (
            post_list_queryset(_viewer(request))
            .filter(pk=int(source_id))
            .first()
        )

    prompt = (post.prompt.strip() if post and post.prompt else "") or raw_prompt
    return {
        "prompt": prompt,
        "source_post_id": post.pk if post else None,
        "source_title": post.title if post else "",
        "source_author": post.author.username if post else "",
        "source_image": post.image.url if post and post.image else "",
    }


def studio_page(request):
    """The AI studio: a public prompt library plus this account's generations.

    Anonymous visitors get the public library and are indexable.  A signed-in
    visitor additionally gets *their own* generations and credit balance on the
    same URL, so that response is ``noindex``: the studio stays a crawlable
    landing page while a private view of it never enters the index.
    """
    config = AIConfig.load()
    generations = recent_generations(request.user)
    wallet = credit_payload(request.user, config)
    challenges = challenge_state(request.user)

    referral_url = None
    if request.user.is_authenticated:
        referral_url = request.build_absolute_uri(reverse("signup")) + (
            f"?ref={request.user.username}"
        )

    prefill = _studio_prefill(request)
    labels = seo_labels(request)
    # A prefill is a client-side seed for the composer, not a distinct page.
    # Without this, /studio/?source=<every post id> would be an unbounded set of
    # URLs all canonicalising to the bare studio page.
    personalised = bool(request.user.is_authenticated) or bool(prefill["source_post_id"]) or bool(
        (request.GET.get("prompt") or "").strip()
    )

    context = {
        **_base_context(request),
        **_meta_context(
            request,
            title=labels["studio_title"],
            description=labels["studio_description"],
            robots=seo.ROBOTS_NOINDEX_NOFOLLOW if personalised else seo.ROBOTS_INDEX,
        ),
        "library": prompt_library(),
        "generations": generations,
        "prompt_max_length": MAX_PROMPT_LENGTH,
        "credits": wallet,
        "challenges": challenges,
        "invite_slug": INVITE_FRIEND,
        "referral_url": referral_url,
        "prefill": prefill,
        "seo_h1": STRINGS[seo.active_language(request)]["studio"],
        "seo_note": labels["studio_h1_note"],
        **_crumbs_context(
            request,
            _crumbs_home(labels)
            + [
                {
                    "name": STRINGS[seo.active_language(request)]["studio"],
                    "path": _language_alternate_path("web:studio"),
                }
            ],
        ),
        # The canvas, the wallet and the shelf re-render from this without a
        # reload.  Rendered with |json_script so a prompt with markup escapes.
        "studio_data": {
            "credits": wallet,
            "generations": generations,
            "challenges": challenges,
        },
        # Never hand the admin object to a template — only what it displays.
        "provider": {
            "model": config.model,
            "size": config.image_size,
            "ready": config.is_ready,
        },
    }
    response = render(request, "web/studio.html", context)
    return mark_noindex(response) if personalised else response


def profile_page(request, username):
    user = get_object_or_404(get_user_model(), username=username)
    viewer = _viewer(request)
    public_posts = post_list_queryset(viewer).filter(author=user)
    page, has_next, next_page = _paginate(request, public_posts, PROFILE_POST_LIMIT)
    labels = seo_labels(request)

    # The real total, not len() of a 24-item page.
    count = public_posts.count()
    indexable = user.is_indexable
    name = user.display_label
    own_text = " ".join((user.biography or "").split())
    if own_text:
        description = seo.clamp_description(own_text)
    else:
        description = labels["profile_description_fmt"].format(count=count, username=user.username)

    listing_items = [_language_alternate_path("web:post-detail", post.pk) for post in page.object_list]
    context = {
        **_base_context(request),
        **_meta_context(
            request,
            title=labels["profile_title_fmt"].format(name=name, username=user.username),
            description=description,
            robots=seo.ROBOTS_INDEX if indexable else seo.ROBOTS_NOINDEX_FOLLOW,
            og_type="profile",
            og_image=seo.absolute_media_url(user.profile_picture.url, request)
            if user.profile_picture
            else "",
            og_image_alt=name,
            og_image_dims=not user.profile_picture,
            listing_items=listing_items,
        ),
        "profile_user": user,
        "posts": [serialize_post(post, viewer=viewer) for post in page.object_list],
        "post_count": count,
        "follower_count": Follow.objects.filter(following=user).count(),
        "following_count": Follow.objects.filter(follower=user).count(),
        "is_following": bool(
            viewer and Follow.objects.filter(follower=viewer, following=user).exists()
        ),
        "has_next_page": has_next,
        "next_page": next_page,
        "page_query": _page_query(page.number) if page.number > 1 else "",
        "current_page": page.number,
        "seo_empty": labels["profile_empty"],
        **_crumbs_context(
            request,
            _crumbs_home(labels)
            + [
                {
                    "name": f"@{user.username}",
                    "path": _language_alternate_path("web:profile", user.username),
                }
            ],
        ),
        "seo_jsonld_nodes": _profile_jsonld(request, user, count),
    }
    response = render(request, "web/profile.html", context)
    return response if indexable else mark_noindex(response)


def _profile_jsonld(request, user, post_count):
    profile_url = seo.absolute_path(reverse("web:profile", args=[user.username]), request)
    return [
        {
            "@type": "ProfilePage",
            "@id": f"{profile_url}#profilepage",
            "url": profile_url,
            "name": user.display_label,
            "inLanguage": seo.active_language(request),
            "isPartOf": {"@id": f"{seo.absolute_path('/', request)}#website"},
            "mainEntity": {"@id": f"{profile_url}#person"},
        },
        seo.person_node(request, user),
    ]


@noindex(seo.ROBOTS_NOINDEX_NOFOLLOW)
def profile_edit_page(request):
    if not request.user.is_authenticated:
        return redirect("login")
    labels = seo_labels(request)
    context = _base_context(request)
    context.update(
        _meta_context(
            request,
            title=labels["profile_edit_title"],
            description=labels["profile_edit_title"],
            robots=seo.ROBOTS_NOINDEX_NOFOLLOW,
        )
    )
    return render(request, "web/profile_edit.html", context)


@noindex(seo.ROBOTS_NOINDEX_NOFOLLOW)
def saved_page(request):
    if not request.user.is_authenticated:
        return redirect("login")

    save_rows = (
        Save.objects.filter(user=request.user).select_related("post").order_by("-created_at")
    )
    posts = post_list_queryset(request.user).filter(pk__in=[r.post_id for r in save_rows])
    by_id = {p.pk: p for p in posts}
    ordered = [by_id[r.post_id] for r in save_rows if r.post_id in by_id]
    labels = seo_labels(request)
    context = {
        **_base_context(request),
        **_meta_context(
            request,
            title=labels["saved_title"],
            description=labels["saved_title"],
            robots=seo.ROBOTS_NOINDEX_NOFOLLOW,
        ),
        "posts": [serialize_post(p, viewer=request.user) for p in ordered],
    }
    return render(request, "web/saved.html", context)


@noindex(seo.ROBOTS_NOINDEX_NOFOLLOW)
def notifications_page(request):
    if not request.user.is_authenticated:
        return redirect("login")

    notifications = (
        Notification.objects.filter(recipient=request.user)
        .select_related("actor", "post", "comment")[:50]
    )
    labels = seo_labels(request)
    context = {
        **_base_context(request),
        **_meta_context(
            request,
            title=labels["notifications_title"],
            description=labels["notifications_title"],
            robots=seo.ROBOTS_NOINDEX_NOFOLLOW,
        ),
        "notifications": [serialize_notification(n) for n in notifications],
    }
    return render(request, "web/notifications.html", context)


@noindex(seo.ROBOTS_NOINDEX_NOFOLLOW)
def offline_page(request):
    labels = seo_labels(request)
    context = {
        **_meta_context(
            request,
            title=labels["offline_title"],
            description=labels["offline_title"],
            robots=seo.ROBOTS_NOINDEX_NOFOLLOW,
        )
    }
    return render(request, "web/offline.html", context)


# ---------------------------------------------------------------------------
# Crawler-facing documents
# ---------------------------------------------------------------------------


def robots_txt(request):
    """Allow the public content, keep crawlers out of private and thin routes.

    Blocking a private page in robots.txt *prevents* a crawler from ever seeing
    its ``noindex`` tag.  That is deliberate here: these paths either require a
    session or render a per-account view, so there is nothing for a crawler to
    learn from them and no crawl budget worth spending on them.  Both mechanisms
    are in place (``Disallow`` here, ``X-Robots-Tag`` on the view) so the page
    stays excluded even for a crawler that reaches it by an internal link.

    Deliberately **not** disallowed:

    * ``/static/`` and ``/media/`` — the CSS, JS and images the crawler needs to
      render the pages it is judging;
    * ``/search/?q=…`` and ``/studio/?source=…`` — no URL is excluded on the
      strength of a query string alone.  Those pages are handled at the page
      level with ``noindex`` plus a canonical that drops the parameters, which is
      what actually consolidates them.
    * ``/feed/…`` and ``/category/…`` — real content, linked, worth crawling.
    """
    lines = [
        "# Promptya — https://promptya.com",
        "# Public content is open to crawlers. Everything below is private,",
        "# per-account, or a utility endpoint.",
        "",
        "User-agent: *",
        "Allow: /",
        "Allow: /static/",
        "Allow: /media/",
        "",
        "# JSON API: not HTML, not indexable, expensive to crawl.",
        "Disallow: /api/",
        "Disallow: /fa/api/",
        "Disallow: /en/api/",
        "",
        "# Administration.",
        "Disallow: /admin/",
        "Disallow: /fa/admin/",
        "Disallow: /en/admin/",
        "",
        "# Authentication.",
        "Disallow: /login/",
        "Disallow: /signup/",
        "Disallow: /fa/login/",
        "Disallow: /fa/signup/",
        "Disallow: /en/login/",
        "Disallow: /en/signup/",
        "",
        "# Per-account pages. Also noindex at the page level.",
        "Disallow: /settings/",
        "Disallow: /saved/",
        "Disallow: /notifications/",
        "Disallow: /create/",
        "Disallow: /feed/following/",
        "Disallow: /fa/settings/",
        "Disallow: /fa/saved/",
        "Disallow: /fa/notifications/",
        "Disallow: /fa/create/",
        "Disallow: /fa/feed/following/",
        "Disallow: /en/settings/",
        "Disallow: /en/saved/",
        "Disallow: /en/notifications/",
        "Disallow: /en/create/",
        "Disallow: /en/feed/following/",
        "",
        "# Service-worker and offline scaffolding.",
        "Disallow: /offline/",
        "Disallow: /fa/offline/",
        "Disallow: /en/offline/",
        "",
        f"Sitemap: {seo.absolute_path('/sitemap.xml', request)}",
        "",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain; charset=utf-8")


def sitemap_xml(request, sitemaps=None):
    """The XML sitemap, served from one absolute origin.

    Django's ``sitemap`` view decorates its response with
    ``X-Robots-Tag: noindex, noodp, noarchive`` — a sensible default for a sitemap
    a human might stumble onto, and a directly contradictory instruction in a
    file we explicitly ask Google to fetch and trust. The header is removed here;
    ``robots.txt`` already allows the path.
    """
    response = django_sitemap(request, SITEMAPS if sitemaps is None else sitemaps)
    response.headers.pop("X-Robots-Tag", None)
    response.headers["X-Robots-Tag"] = "index, follow"
    return response
