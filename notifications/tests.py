from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from interactions.models import Comment, Follow, Like, Save
from notifications.models import Notification
from posts.models import Category, Post


class NotificationSignalTests(TestCase):
    def setUp(self):
        self.author = get_user_model().objects.create_user(
            username="author",
            email="author@example.com",
            password="test-password",
        )
        self.fan = get_user_model().objects.create_user(
            username="fan",
            email="fan@example.com",
            password="test-password",
        )
        category = Category.objects.create(name="Writing", slug="writing")
        self.post = Post.objects.create(
            author=self.author,
            category=category,
            post_type=Post.PostType.PROMPT,
            title="A lovely prompt",
        )

    def test_like_creates_a_notification_for_the_author(self):
        Like.objects.create(post=self.post, user=self.fan)

        self.assertEqual(Notification.objects.filter(recipient=self.author).count(), 1)
        self.assertEqual(Notification.objects.first().notification_type, "like")

    def test_save_creates_a_notification(self):
        Save.objects.create(post=self.post, user=self.fan)

        self.assertTrue(
            Notification.objects.filter(recipient=self.author, notification_type="save").exists()
        )

    def test_comment_creates_a_notification_with_comment_reference(self):
        comment = Comment.objects.create(post=self.post, user=self.fan, content="Great!")

        self.assertTrue(
            Notification.objects.filter(
                recipient=self.author, notification_type="comment", comment=comment
            ).exists()
        )

    def test_follow_creates_a_notification(self):
        Follow.objects.create(follower=self.fan, following=self.author)

        self.assertTrue(
            Notification.objects.filter(recipient=self.author, notification_type="follow").exists()
        )

    def test_no_notification_for_self_actions(self):
        Like.objects.create(post=self.post, user=self.author)
        Follow.objects.create(follower=self.author, following=self.author)

        self.assertEqual(Notification.objects.count(), 0)

    def test_unlike_and_unfollow_do_not_duplicate_notifications(self):
        like = Like.objects.create(post=self.post, user=self.fan)
        like.delete()
        Like.objects.create(post=self.post, user=self.fan)

        self.assertEqual(Notification.objects.count(), 1)


class NotificationApiTests(TestCase):
    def setUp(self):
        self.author = get_user_model().objects.create_user(
            username="api-author",
            email="api-author@example.com",
            password="test-password",
        )
        self.fan = get_user_model().objects.create_user(
            username="api-fan",
            email="api-fan@example.com",
            password="test-password",
        )
        category = Category.objects.create(name="Art", slug="art-2")
        self.post = Post.objects.create(
            author=self.author,
            category=category,
            post_type=Post.PostType.IMAGE,
            title="Notification prompt",
        )
        Like.objects.create(post=self.post, user=self.fan)

    def test_anonymous_users_get_401(self):
        response = self.client.get(reverse("notifications:list"))

        self.assertEqual(response.status_code, 401)

    def test_recipient_can_list_notifications(self):
        self.client.force_login(self.author)

        response = self.client.get(reverse("notifications:list"))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["unread_count"], 1)
        self.assertEqual(data["results"][0]["type"], "like")
        self.assertEqual(data["results"][0]["post"]["id"], self.post.pk)

    def test_only_the_recipient_sees_their_notifications(self):
        self.client.force_login(self.fan)

        response = self.client.get(reverse("notifications:list"))

        self.assertEqual(response.json()["results"], [])

    def test_mark_single_notification_read(self):
        self.client.force_login(self.author)
        notification = Notification.objects.get(recipient=self.author)

        response = self.client.post(
            reverse("notifications:read", args=[notification.pk])
        )

        self.assertEqual(response.status_code, 200)
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)

    def test_mark_all_read(self):
        Comment.objects.create(post=self.post, user=self.fan, content="Nice")
        self.client.force_login(self.author)

        response = self.client.post(reverse("notifications:read-all"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            Notification.objects.filter(recipient=self.author, is_read=False).count(),
            0,
        )

    def test_mark_read_returns_404_for_foreign_notification(self):
        other = get_user_model().objects.create_user(
            username="api-other",
            email="api-other@example.com",
            password="test-password",
        )
        notification = Notification.objects.get(recipient=self.author)
        self.client.force_login(other)

        response = self.client.post(reverse("notifications:read", args=[notification.pk]))

        self.assertEqual(response.status_code, 404)


class NotificationsPageTests(TestCase):
    """The server-rendered notifications page must survive post-linked rows.

    ``serialize_notification`` used to declare the ``post`` key twice in one
    dict literal; the second (id/title only) silently won, so ``n.post.slug``
    resolved to an empty string and reversing the post-detail URL with it
    raised NoReverseMatch — a 500 for every author with a single like.
    """

    def setUp(self):
        self.author = get_user_model().objects.create_user(
            username="page-author",
            email="page-author@example.com",
            password="test-password",
        )
        self.fan = get_user_model().objects.create_user(
            username="page-fan",
            email="page-fan@example.com",
            password="test-password",
        )
        category = Category.objects.create(name="Page", slug="page-cat")
        self.post = Post.objects.create(
            author=self.author,
            category=category,
            post_type=Post.PostType.PROMPT,
            title="Notified prompt",
        )
        Like.objects.create(post=self.post, user=self.fan)

    def test_the_page_renders_and_links_the_liked_post(self):
        self.client.force_login(self.author)

        response = self.client.get(reverse("web:notifications"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("web:post-detail", args=[self.post.slug]))
        self.assertContains(response, "Notified prompt")

    def test_the_json_payload_carries_slug_and_url(self):
        self.client.force_login(self.author)

        response = self.client.get(reverse("notifications:list"))

        post_payload = response.json()["results"][0]["post"]
        self.assertEqual(post_payload["slug"], self.post.slug)
        self.assertEqual(
            post_payload["url"], reverse("web:post-detail", args=[self.post.slug])
        )
