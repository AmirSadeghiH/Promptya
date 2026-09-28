"""Recommendation engine for the Promptya home feed.

Personalized "For You" ranking, inspired by Instagram's approach but kept
database-friendly (a handful of small aggregate queries, no heavy ML):

  score = engagement (likes/saves/comments/copies/views, decayed by age)
        × category affinity  (how much the viewer engages with this category)
        × author affinity    (boost for already-followed authors, small boost
                              for authors the viewer interacted with)
        + freshness bonus    (very recent posts surface first)

Anonymous viewers get the plain trending ranking, so the endpoint doubles
as the logged-out home feed.
"""

from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.utils import timezone

from interactions.models import Follow, Like, PostCopy, Save
from posts.models import Category, Post
from posts.services import post_list_queryset

RECOMMENDED_PAGE_SIZE = 12
SUGGESTED_USERS_LIMIT = 5


def get_recommended_feed(*, user=None, cursor=None, page_size=RECOMMENDED_PAGE_SIZE, viewer=None):
    """Personalized feed. Returns the same page shape as other feeds."""
    from posts.services import get_trending_feed

    if user is None or not getattr(user, "is_authenticated", False):
        page = get_trending_feed(cursor=cursor, page_size=page_size, viewer=viewer)
        page["feed_kind"] = "trending"
        return page

    viewer = viewer or user
    category_scores = _category_affinity(user)      # {category_id: score}
    followed_ids = set(
        Follow.objects.filter(follower=user).values_list("following_id", flat=True)
    )
    interacted_author_ids = _interacted_author_ids(user)
    followed_author_ids = {pk for pk in followed_ids if pk != user.pk}

    page = get_trending_feed(cursor=cursor, page_size=page_size, viewer=viewer)

    if not category_scores and not followed_author_ids:
        return page

    def rank(item):
        score = 0.0
        category_id = item["category"]["id"]
        score += min(category_scores.get(category_id, 0.0), 5.0)
        author_id = item["author"]["id"]
        if author_id in followed_author_ids:
            score += 3.0
        elif author_id in interacted_author_ids:
            score += 1.0
        return score

    ranked = sorted(page["results"], key=rank, reverse=True)
    page["results"] = _diversify(ranked)
    page["feed_kind"] = "recommended"
    return page


def _diversify(items):
    """Interleave the ranked page so one creator or media type can't clump.

    Greedy pass: at each position prefer the highest-ranked remaining item
    whose author differs from the previous pick and whose post_type doesn't
    complete a run of three; fall back to the plain best item when no
    alternative exists. O(n²) worst case on a page of ≤ 12 items — trivial.
    """
    remaining = list(items)
    output = []
    while remaining:
        pick_index = 0
        for index, candidate in enumerate(remaining):
            same_author = output and candidate["author"]["id"] == output[-1]["author"]["id"]
            same_type_run = (
                len(output) >= 2
                and candidate["post_type"] == output[-1]["post_type"] == output[-2]["post_type"]
            )
            if not same_author and not same_type_run:
                pick_index = index
                break
        output.append(remaining.pop(pick_index))
    return output


def _category_affinity(user):
    """How strongly the user engages with each category (0..~5)."""
    scores = {}

    # (user's related manager, weight) — like/save/copy are strong signals.
    # related_name check: Like.likes, Save.saved_posts, PostCopy.post_copies
    for related, weight in (("likes", 3.0), ("saved_posts", 5.0), ("post_copies", 6.0)):
        rows = (
            getattr(user, related)
            .values("post__category_id")
            .annotate(n=Count("id"))
        )
        for row in rows:
            key = row["post__category_id"]
            scores[key] = scores.get(key, 0.0) + row["n"] * weight

    # Views count at weight 0.5 — weak signal, many events.
    for row in (
        user.post_views.values("post__category_id").annotate(n=Count("id"))
    ):
        key = row["post__category_id"]
        scores[key] = scores.get(key, 0.0) + row["n"] * 0.5

    return scores


def _interacted_author_ids(user):
    """Authors whose posts the viewer liked/saved/copied at least once."""
    ids = set()
    for manager in ("likes", "saved_posts", "post_copies"):
        rows = getattr(user, manager).values_list("post__author_id", flat=True)
        ids.update(rows)
    return ids


def get_suggested_users(*, user=None, limit=SUGGESTED_USERS_LIMIT):
    """Users worth following for the sidebar / profile suggestions.

    Ranking:
      - authors the viewer already engages with but doesn't follow (strong)
      - creators in categories the viewer likes (medium)
      - popular creators overall (baseline)
    Always excludes self and already-followed users.
    """
    User = get_user_model()
    queryset = (
        User.objects.annotate(post_count=Count("posts"))
        .filter(post_count__gt=0)
    )

    if user is None or not getattr(user, "is_authenticated", False):
        return list(
            queryset.order_by("-post_count", "username")
            .values("id", "username", "display_name", "is_verified", "post_count")[:limit]
        )

    followed_ids = set(
        Follow.objects.filter(follower=user).values_list("following_id", flat=True)
    ) | {user.pk}
    queryset = queryset.exclude(pk__in=followed_ids)

    candidates = list(
        queryset.annotate(
            follower_count=Count("follower_relations", distinct=True),
        ).order_by("-follower_count", "-post_count")[: limit * 6]
    )
    if not candidates:
        return []

    affinity = _category_affinity(user)
    interacted = _interacted_author_ids(user)

    category_by_author = {}
    top_categories = sorted(affinity.items(), key=lambda kv: kv[1], reverse=True)[:5]
    if top_categories:
        category_ids = [cid for cid, _ in top_categories]
        for row in (
            Post.objects.filter(category_id__in=category_ids)
            .values("author_id")
            .annotate(n=Count("id"))
        ):
            category_by_author[row["author_id"]] = row["n"]

    def rank(candidate):
        score = 0.0
        if candidate.pk in interacted:
            score += 4.0
        score += 0.6 * min(category_by_author.get(candidate.pk, 0), 5)
        score += 0.05 * candidate.follower_count
        return score

    candidates.sort(key=rank, reverse=True)
    return [
        {
            "id": c.pk,
            "username": c.username,
            "display_name": c.display_name or c.username,
            "is_verified": c.is_verified,
            "post_count": c.post_count,
            "follower_count": c.follower_count,
            "profile_picture": c.profile_picture.url if c.profile_picture else None,
        }
        for c in candidates[:limit]
    ]
