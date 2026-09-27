from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
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
from posts.models import Category, Post
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


def _viewer(request):
    return request.user if request.user.is_authenticated else None


def _base_context(request):
    context = {
        "categories": Category.objects.all(),
        "unread_notifications": 0,
    }
    if request.user.is_authenticated:
        context["unread_notifications"] = unread_count(request.user)
    return context


def home(request):
    viewer = _viewer(request)
    user = request.user if request.user.is_authenticated else None
    page = get_recommended_feed(user=user, page_size=12, viewer=viewer)
    context = {
        **_base_context(request),
        "posts": page["results"],
        "next_cursor": page["next_cursor"],
        "feed_tab": "foryou",
        "is_recommended": user is not None,
        "suggested_users": get_suggested_users(user=user),
    }
    return render(request, "web/home.html", context)


def feed_page(request, feed):
    if feed == "following" and not request.user.is_authenticated:
        return redirect("login")

    viewer = _viewer(request)
    feed_map = {
        "latest": get_latest_feed,
        "following": get_following_feed,
        "trending": get_trending_feed,
    }
    if feed not in feed_map:
        return redirect("web:home")
    feed_fn = feed_map[feed]
    if feed == "following":
        page = feed_fn(request.user, page_size=12, viewer=viewer)
    else:
        page = feed_fn(page_size=12, viewer=viewer)

    context = {
        **_base_context(request),
        "posts": page["results"],
        "next_cursor": page["next_cursor"],
        "feed_tab": feed,
    }
    return render(request, "web/feed.html", context)


def explore_page(request):
    context = {**_base_context(request), "explore": get_explore_data(viewer=_viewer(request))}
    return render(request, "web/explore.html", context)


def search_page(request):
    query = request.GET.get("q", "").strip()
    context = {**_base_context(request), "query": query, "results": []}
    if query:
        page = search_posts(query, page_size=24, viewer=_viewer(request))
        context["results"] = page["results"]
        context["next_cursor"] = page["next_cursor"]
    return render(request, "web/search.html", context)


def category_page(request, slug):
    category = get_object_or_404(Category, slug=slug)
    page = search_posts("", category_slug=slug, page_size=24, viewer=_viewer(request))
    context = {
        **_base_context(request),
        "category": category,
        "posts": page["results"],
        "next_cursor": page["next_cursor"],
    }
    return render(request, "web/category.html", context)


def post_detail_page(request, pk):
    viewer = _viewer(request)
    post = get_object_or_404(post_list_queryset(viewer), pk=pk)
    context = {**_base_context(request), "post": serialize_post(post, viewer=viewer)}
    return render(request, "web/post_detail.html", context)


def create_post_page(request):
    context = _base_context(request)
    context["category_options"] = Category.objects.all()
    return render(request, "web/create.html", context)


def _studio_prefill(request):
    """A prompt handed to the studio by a post's "Use prompt" action.

    ``?source=<post id>`` is preferred over a raw ``?prompt=`` because it also
    preserves the link back to the post the prompt came from.
    """
    raw_prompt = (request.GET.get("prompt") or "").strip()
    source_id = (request.GET.get("source") or "").strip()
    post = None
    if source_id.isdigit():
        post = Post.objects.select_related("author").filter(pk=int(source_id)).first()

    prompt = (post.prompt.strip() if post and post.prompt else "") or raw_prompt
    return {
        "prompt": prompt,
        "source_post_id": post.pk if post else None,
        "source_title": post.title if post else "",
        "source_author": post.author.username if post else "",
        "source_image": post.image.url if post and post.image else "",
    }


def studio_page(request):
    """The AI studio: a public prompt library plus this account's generations."""
    config = AIConfig.load()
    generations = recent_generations(request.user)
    wallet = credit_payload(request.user, config)
    challenges = challenge_state(request.user)

    referral_url = None
    if request.user.is_authenticated:
        referral_url = request.build_absolute_uri(reverse("signup")) + (
            f"?ref={request.user.username}"
        )

    context = {
        **_base_context(request),
        "library": prompt_library(),
        "generations": generations,
        "prompt_max_length": MAX_PROMPT_LENGTH,
        "credits": wallet,
        "challenges": challenges,
        "invite_slug": INVITE_FRIEND,
        "referral_url": referral_url,
        "prefill": _studio_prefill(request),
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
    return render(request, "web/studio.html", context)


def profile_page(request, username):
    user = get_object_or_404(get_user_model(), username=username)
    viewer = _viewer(request)
    posts = post_list_queryset(viewer).filter(author=user)[:24]
    context = {
        **_base_context(request),
        "profile_user": user,
        "posts": [serialize_post(post, viewer=viewer) for post in posts],
        "follower_count": Follow.objects.filter(following=user).count(),
        "following_count": Follow.objects.filter(follower=user).count(),
        "is_following": bool(
            viewer and Follow.objects.filter(follower=viewer, following=user).exists()
        ),
    }
    return render(request, "web/profile.html", context)


def profile_edit_page(request):
    if not request.user.is_authenticated:
        return redirect("login")
    return render(request, "web/profile_edit.html", _base_context(request))


def saved_page(request):
    if not request.user.is_authenticated:
        return redirect("login")

    save_rows = (
        Save.objects.filter(user=request.user).select_related("post").order_by("-created_at")
    )
    posts = post_list_queryset(request.user).filter(pk__in=[r.post_id for r in save_rows])
    by_id = {p.pk: p for p in posts}
    ordered = [by_id[r.post_id] for r in save_rows if r.post_id in by_id]
    context = {
        **_base_context(request),
        "posts": [serialize_post(p, viewer=request.user) for p in ordered],
    }
    return render(request, "web/saved.html", context)


def notifications_page(request):
    if not request.user.is_authenticated:
        return redirect("login")

    notifications = (
        Notification.objects.filter(recipient=request.user)
        .select_related("actor", "post", "comment")[:50]
    )
    context = {
        **_base_context(request),
        "notifications": [serialize_notification(n) for n in notifications],
    }
    return render(request, "web/notifications.html", context)


def offline_page(request):
    return render(request, "web/offline.html")


def robots_txt(request):
    """Allow the public content, keep crawlers out of private and thin routes."""
    lines = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /admin/",
        "Disallow: /api/",
        "Disallow: /settings/",
        "Disallow: /create/",
        "Disallow: /saved/",
        "Disallow: /notifications/",
        "Disallow: /offline/",
        "Disallow: /login/",
        "Disallow: /signup/",
        "",
        f"Sitemap: {request.scheme}://{request.get_host()}/sitemap.xml",
        "",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain; charset=utf-8")
