import json

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from core.ratelimit import rate_limit_user, rate_limit_ip
from interactions.models import Comment, Follow, Like, PostCopy, PostView, Save
from moderation.antispam import looks_like_spam
from moderation.services import blocked_user_ids, is_blocked_between
from posts.models import Post
from posts.services import post_list_queryset, serialize_post


def _get_post_or_error(post_id):
    try:
        return Post.objects.visible().get(pk=post_id), None
    except Post.DoesNotExist:
        return None, JsonResponse({"error": "Post not found."}, status=404)


def _method_not_allowed():
    return JsonResponse({"error": "Method not allowed."}, status=405)


@rate_limit_ip("post_view", limit=120, window_seconds=60, error_message="Too many view requests. Slow down.")
def record_view(request, post_id):
    if request.method != "POST":
        return _method_not_allowed()

    post, error_response = _get_post_or_error(post_id)
    if error_response:
        return error_response

    user = request.user if request.user.is_authenticated else None
    PostView.objects.create(post=post, user=user)
    return JsonResponse({"post_id": post.pk, "event": "view"}, status=201)


@login_required
@rate_limit_user("post_copy", limit=30, window_seconds=60, error_message="Too many copy requests. Slow down.")
@require_POST
def record_copy(request, post_id):
    post, error_response = _get_post_or_error(post_id)
    if error_response:
        return error_response

    PostCopy.objects.create(post=post, user=request.user)
    return JsonResponse({"post_id": post.pk, "event": "copy"}, status=201)


@login_required
@rate_limit_user("post_like", limit=60, window_seconds=60, error_message="Too many like requests. Slow down.")
@require_POST
@transaction.atomic
def toggle_like(request, post_id):
    post = get_object_or_404(Post.objects.visible(), pk=post_id)

    like, created = Like.objects.get_or_create(user=request.user, post=post)
    if not created:
        like.delete()
        return JsonResponse(
            {"post_id": post.pk, "liked": False, "like_count": post.likes.count()},
            status=200,
        )
    return JsonResponse(
        {"post_id": post.pk, "liked": True, "like_count": post.likes.count()},
        status=201,
    )


@login_required
@rate_limit_user("post_save", limit=60, window_seconds=60, error_message="Too many save requests. Slow down.")
@require_POST
@transaction.atomic
def toggle_save(request, post_id):
    post = get_object_or_404(Post.objects.visible(), pk=post_id)

    save, created = Save.objects.get_or_create(user=request.user, post=post)
    if not created:
        save.delete()
        return JsonResponse(
            {"post_id": post.pk, "saved": False, "save_count": post.saves.count()},
            status=200,
        )
    return JsonResponse(
        {"post_id": post.pk, "saved": True, "save_count": post.saves.count()},
        status=201,
    )


@login_required
@rate_limit_user("post_comment", limit=20, window_seconds=60, error_message="Too many comments. Slow down.")
@require_POST
def create_comment(request, post_id):
    post, error_response = _get_post_or_error(post_id)
    if error_response:
        return error_response

    # A block is symmetric: neither party may comment on the other's post.
    if is_blocked_between(request.user, post.author):
        return JsonResponse(
            {"error": "You cannot comment on this post."}, status=403
        )

    try:
        data = json.loads(request.body.decode("utf-8")) if request.body else {}
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid JSON body."}, status=400)

    content = str(data.get("content", "")).strip()
    if not content:
        return JsonResponse({"errors": {"content": "Comment cannot be empty."}}, status=400)
    if len(content) > 2000:
        return JsonResponse(
            {"errors": {"content": "Comment must be at most 2000 characters."}},
            status=400,
        )

    # Anti-spam rejects only this submission — never the account. A false
    # positive costs one retyped comment, not a ban.
    previous = list(
        Comment.objects.filter(user=request.user, post=post)
        .order_by("-created_at")
        .values_list("content", flat=True)[:5]
    )
    if looks_like_spam(content, previous_contents=previous):
        return JsonResponse(
            {"errors": {"content": "This looks like spam. Please rewrite your comment."}},
            status=400,
        )

    comment = Comment.objects.create(post=post, user=request.user, content=content)
    return JsonResponse(
        {
            "id": comment.pk,
            "content": comment.content,
            "created_at": comment.created_at.isoformat(),
            "user": {
                "id": request.user.pk,
                "username": request.user.username,
                "display_name": request.user.display_name or request.user.username,
                "profile_picture": (
                    request.user.profile_picture.url if request.user.profile_picture else None
                ),
            },
            "comment_count": post.comments.count(),
        },
        status=201,
    )


@login_required
def delete_comment(request, comment_id):
    if request.method != "DELETE":
        return _method_not_allowed()

    comment = get_object_or_404(Comment.objects.select_related("post"), pk=comment_id)
    if comment.user_id != request.user.id and comment.post.author_id != request.user.id:
        return JsonResponse(
            {"error": "You can only delete your own comments."}, status=403
        )
    post_id = comment.post_id
    comment.delete()
    return JsonResponse(
        {"deleted": True, "comment_count": Comment.objects.filter(post_id=post_id).count()}
    )


def list_comments(request, post_id):
    if request.method != "GET":
        return _method_not_allowed()

    post, error_response = _get_post_or_error(post_id)
    if error_response:
        return error_response

    comments = (
        post.comments.filter(is_hidden=False)
        .select_related("user")
        .order_by("created_at")
    )
    viewer = request.user if request.user.is_authenticated else None
    if viewer is not None:
        blocked_ids = blocked_user_ids(viewer)
        if blocked_ids:
            comments = comments.exclude(user_id__in=blocked_ids)
    return JsonResponse(
        {
            "results": [
                {
                    "id": comment.pk,
                    "content": comment.content,
                    "created_at": comment.created_at.isoformat(),
                    "user": {
                        "id": comment.user_id,
                        "username": comment.user.username,
                        "display_name": comment.user.display_name or comment.user.username,
                        "profile_picture": (
                            comment.user.profile_picture.url
                            if comment.user.profile_picture
                            else None
                        ),
                    },
                }
                for comment in comments
            ]
        }
    )


@login_required
@rate_limit_user("user_follow", limit=30, window_seconds=60, error_message="Too many follow requests. Slow down.")
@require_POST
@transaction.atomic
def toggle_follow(request, username):
    target = get_object_or_404(
        get_user_model().objects.exclude(pk=request.user.pk),
        username=username,
    )

    if is_blocked_between(request.user, target):
        return JsonResponse({"error": "You cannot follow this user."}, status=403)

    follow, created = Follow.objects.get_or_create(follower=request.user, following=target)
    if not created:
        follow.delete()
        return JsonResponse(
            {"following": False, "follower_count": Follow.objects.filter(following=target).count()},
            status=200,
        )
    return JsonResponse(
        {"following": True, "follower_count": Follow.objects.filter(following=target).count()},
        status=201,
    )
