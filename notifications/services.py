from notifications.models import Notification
from django.urls import reverse, NoReverseMatch

def create_notification(*, recipient, actor, notification_type, post=None, comment=None):
    """Create a notification for an interaction.

    Skips self-actions (recipient == actor) so users are never notified
    about their own likes/comments/follows.
    """
    if recipient.pk == actor.pk:
        return None
    return Notification.objects.create(
        recipient=recipient,
        actor=actor,
        notification_type=notification_type,
        post=post,
        comment=comment,
    )


def unread_count(user):
    return Notification.objects.filter(recipient=user, is_read=False).count()


def serialize_notification(notification):
    """The JSON/template shape of one notification.

    ``post`` carries ``slug`` and ``url`` as well as ``id``/``title``: the
    server-rendered notifications page links via ``n.post.slug``, and a payload
    without it used to reverse an empty slug (NoReverseMatch -> 500) for every
    like/save/comment notification.  Exactly one ``post`` key is emitted — a
    duplicate key in the dict literal silently won and dropped the slug.
    """
    post = notification.post
    comment = notification.comment
    post_data = None
    if post:
        try:
            post_url = reverse("web:post-detail", args=[post.slug]) if post.slug else None
        except NoReverseMatch:
            post_url = None
        post_data = {
            "id": post.id,
            "title": post.title,
            "slug": post.slug,
            "url": post_url,
        }
    return {
        "id": notification.id,
        "type": notification.notification_type,
        "is_read": notification.is_read,
        "created_at": notification.created_at.isoformat(),
        "actor": {
            "id": notification.actor_id,
            "username": notification.actor.username,
            "display_name": notification.actor.display_name or notification.actor.username,
            "profile_picture": (
                notification.actor.profile_picture.url
                if notification.actor.profile_picture
                else None
            ),
        },
        "post": post_data,
        "comment": {"id": comment.id, "content": comment.content} if comment else None,
    }
