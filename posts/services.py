import base64
import json
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import (
    Case,
    Count,
    Exists,
    ExpressionWrapper,
    F,
    FloatField,
    OuterRef,
    Q,
    Value,
    When,
)
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from interactions.models import Follow, Like, Save
from posts.models import Category, Post


class InvalidCursor(ValueError):
    """Raised when a feed cursor cannot be decoded safely."""


def post_list_queryset(viewer=None):
    """Base post queryset with engagement counts.

    When an authenticated ``viewer`` is passed, ``viewer_liked`` /
    ``viewer_saved`` are annotated as cheap EXISTS subqueries so
    ``serialize_post`` does not run two extra queries per post (N+1).
    """
    queryset = (
        Post.objects.select_related("author", "category")
        .prefetch_related("tags")
        .annotate(
            like_count=Count("likes", distinct=True),
            save_count=Count("saves", distinct=True),
            comment_count=Count("comments", distinct=True),
            view_count=Count("view_events", distinct=True),
            copy_count=Count("copy_events", distinct=True),
        )
    )
    if viewer is not None and getattr(viewer, "is_authenticated", False):
        queryset = queryset.annotate(
            viewer_liked=Exists(
                Like.objects.filter(user=viewer, post_id=OuterRef("pk"))
            ),
            viewer_saved=Exists(
                Save.objects.filter(user=viewer, post_id=OuterRef("pk"))
            ),
        )
    return queryset


def _viewer_followed_ids(viewer):
    """Followed-user ids for the viewer, computed once per request cycle.

    The set is cached on the viewer instance so serializing a whole feed
    page performs a single Follow query instead of one per post.
    """
    cached = getattr(viewer, "_promptya_followed_ids", None)
    if cached is None:
        cached = set(
            Follow.objects.filter(follower=viewer).values_list("following_id", flat=True)
        )
        viewer._promptya_followed_ids = cached
    return cached


def _author_payload(post, viewer=None):
    author = post.author
    data = {
        "id": author.id,
        "username": author.username,
        "display_name": author.display_name or author.username,
        "is_verified": author.is_verified,
        "profile_picture": author.profile_picture.url if author.profile_picture else None,
    }
    if getattr(post, "author_followers", None) is not None:
        data["follower_count"] = post.author_followers
    if viewer is not None and viewer.is_authenticated:
        data["is_following"] = author.id in _viewer_followed_ids(viewer)
    return data


def serialize_post(post, *, viewer=None):
    def _flag(manager_name):
        if not viewer or not viewer.is_authenticated:
            return False
        # Prefer the EXISTS annotation (no extra query); fall back to a
        # per-post lookup only when the queryset was built without a viewer.
        annotation = "viewer_liked" if manager_name == "likes" else "viewer_saved"
        annotated = getattr(post, annotation, None)
        if annotated is not None:
            return bool(annotated)
        return getattr(post, manager_name).filter(user=viewer).exists()

    return {
        "id": post.id,
        "post_type": post.post_type,
        "title": post.title,
        "description": post.description,
        "prompt": post.prompt,
        "ai_model": post.ai_model,
        "image": post.image.url if post.image else None,
        # The WebP derivative and the intrinsic size, captured once at upload time
        # (posts.signals). The client-side card builder in static/js/app.js reads
        # them so an infinitely-scrolled card reserves its space and serves the
        # smaller file, exactly as the server-rendered card does.
        "image_webp": post.image_webp.url if post.image_webp else None,
        "image_width": post.image_width,
        "image_height": post.image_height,
        "video": post.video.url if post.video else None,
        "audio": post.audio.url if post.audio else None,
        "created_at": post.created_at.isoformat(),
        "updated_at": post.updated_at.isoformat(),
        "author": _author_payload(post, viewer),
        "category": {
            "id": post.category_id,
            "name": post.category.name,
            "slug": post.category.slug,
        },
        "tags": [
            {"id": tag.id, "name": tag.name, "slug": tag.slug}
            for tag in post.tags.all()
        ],
        "like_count": post.like_count,
        "save_count": post.save_count,
        "comment_count": post.comment_count,
        "view_count": post.view_count,
        "copy_count": post.copy_count,
        "is_liked": _flag("likes"),
        "is_saved": _flag("saves"),
    }


def _encode_cursor(created_at, post_id):
    payload = json.dumps(
        {"created_at": created_at.isoformat(), "id": post_id},
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(cursor):
    try:
        padded_cursor = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded_cursor.encode()).decode())
        created_at = parse_datetime(payload["created_at"])
        post_id = payload["id"]
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
        raise InvalidCursor from None

    if created_at is None or not created_at.tzinfo or not isinstance(post_id, int):
        raise InvalidCursor
    return created_at, post_id


def _paginate_chronological(queryset, *, cursor, page_size, viewer=None):
    queryset = queryset.order_by("-created_at", "-id")
    if cursor:
        created_at, post_id = _decode_cursor(cursor)
        queryset = queryset.filter(
            Q(created_at__lt=created_at)
            | Q(created_at=created_at, id__lt=post_id),
        )

    posts = list(queryset[: page_size + 1])
    has_next_page = len(posts) > page_size
    page_posts = posts[:page_size]
    next_cursor = None
    if has_next_page:
        last_post = page_posts[-1]
        next_cursor = _encode_cursor(last_post.created_at, last_post.id)

    return {
        "results": [serialize_post(post, viewer=viewer) for post in page_posts],
        "next_cursor": next_cursor,
    }


def _encode_trending_cursor(score, created_at, post_id):
    payload = json.dumps(
        {
            "score": score,
            "created_at": created_at.isoformat(),
            "id": post_id,
        },
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_trending_cursor(cursor):
    try:
        padded_cursor = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded_cursor.encode()).decode())
        score = payload["score"]
        created_at = parse_datetime(payload["created_at"])
        post_id = payload["id"]
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
        raise InvalidCursor from None

    if (
        isinstance(score, bool)
        or not isinstance(score, (int, float))
        or created_at is None
        or not created_at.tzinfo
        or not isinstance(post_id, int)
    ):
        raise InvalidCursor
    return float(score), created_at, post_id


def _paginate_trending(queryset, *, cursor, page_size, viewer=None):
    queryset = queryset.order_by("-trending_score", "-created_at", "-id")
    if cursor:
        score, created_at, post_id = _decode_trending_cursor(cursor)
        queryset = queryset.filter(
            Q(trending_score__lt=score)
            | Q(trending_score=score, created_at__lt=created_at)
            | Q(trending_score=score, created_at=created_at, id__lt=post_id),
        )

    posts = list(queryset[: page_size + 1])
    has_next_page = len(posts) > page_size
    page_posts = posts[:page_size]
    next_cursor = None
    if has_next_page:
        last_post = page_posts[-1]
        next_cursor = _encode_trending_cursor(
            last_post.trending_score,
            last_post.created_at,
            last_post.id,
        )

    return {
        "results": [serialize_post(post, viewer=viewer) for post in page_posts],
        "next_cursor": next_cursor,
    }


def get_latest_feed(*, cursor=None, page_size=20, viewer=None):
    return _paginate_chronological(
        post_list_queryset(viewer),
        cursor=cursor,
        page_size=page_size,
        viewer=viewer,
    )


def get_following_feed(user, *, cursor=None, page_size=20, viewer=None):
    followed_user_ids = Follow.objects.filter(follower=user).values("following_id")
    return _paginate_chronological(
        post_list_queryset(viewer or user).filter(author_id__in=followed_user_ids),
        cursor=cursor,
        page_size=page_size,
        viewer=viewer or user,
    )


def get_trending_feed(*, cursor=None, page_size=20, viewer=None):
    now = timezone.now()
    age_factor = Case(
        When(created_at__gte=now - timedelta(days=1), then=Value(1.0)),
        When(created_at__gte=now - timedelta(days=7), then=Value(2.0)),
        default=Value(3.0),
        output_field=FloatField(),
    )
    engagement_score = ExpressionWrapper(
        F("like_count") * Value(3.0)
        + F("save_count") * Value(5.0)
        + F("comment_count") * Value(4.0)
        + F("copy_count") * Value(6.0)
        + F("view_count"),
        output_field=FloatField(),
    )
    queryset = (
        post_list_queryset(viewer)
        .filter(created_at__gte=now - timedelta(days=30))
        .annotate(
            trending_score=ExpressionWrapper(
                engagement_score / age_factor,
                output_field=FloatField(),
            ),
        )
    )
    return _paginate_trending(queryset, cursor=cursor, page_size=page_size, viewer=viewer)


def search_posts(query, *, post_type=None, category_slug=None, tag_slug=None,
                 ai_model=None, cursor=None, page_size=20, viewer=None):
    """Search posts by title, prompt, description, tags, category, AI model, creator."""
    queryset = post_list_queryset(viewer)
    if query:
        queryset = queryset.filter(
            Q(title__icontains=query)
            | Q(prompt__icontains=query)
            | Q(description__icontains=query)
            | Q(tags__name__icontains=query)
            | Q(category__name__icontains=query)
            | Q(ai_model__icontains=query)
            | Q(author__username__icontains=query)
            | Q(author__display_name__icontains=query)
        ).distinct()
    if post_type:
        queryset = queryset.filter(post_type=post_type)
    if category_slug:
        queryset = queryset.filter(category__slug=category_slug)
    if tag_slug:
        queryset = queryset.filter(tags__slug=tag_slug)
    if ai_model:
        queryset = queryset.filter(ai_model__icontains=ai_model)

    return _paginate_chronological(
        queryset, cursor=cursor, page_size=page_size, viewer=viewer,
    )


def get_explore_data(viewer=None):
    creator_rows = list(
        get_user_model()
        .objects.annotate(post_count=Count("posts"))
        .filter(post_count__gt=0)
        .order_by("-post_count", "username")
        .values("id", "username", "display_name", "is_verified", "post_count")[:6]
    )
    profile_pictures = {
        row["id"]: f"{settings.MEDIA_URL}{row['path']}"
        for row in get_user_model()
        .objects.filter(
            pk__in=[row["id"] for row in creator_rows],
            profile_picture__isnull=False,
        )
        .exclude(profile_picture="")
        .values("id", path=F("profile_picture"))
    }
    return {
        "latest": get_latest_feed(page_size=6, viewer=viewer)["results"],
        "trending": get_trending_feed(page_size=6, viewer=viewer)["results"],
        "popular_categories": list(
            Category.objects.annotate(post_count=Count("posts"))
            .filter(post_count__gt=0)
            .order_by("-post_count", "name")
            .values("id", "name", "slug", "post_count")[:6],
        ),
        "popular_creators": [
            {
                **creator,
                "display_name": creator.get("display_name") or creator["username"],
                "profile_picture": profile_pictures.get(creator["id"]),
            }
            for creator in creator_rows
        ],
    }
