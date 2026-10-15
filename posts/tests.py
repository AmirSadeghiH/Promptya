from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from interactions.models import Follow, PostCopy, PostView
from posts.models import Category, Post, Tag
from posts.services import (
    get_following_feed,
    get_latest_feed,
    get_trending_feed,
    search_posts,
)


def _create_post(author, category, title="A prompt", post_type=Post.PostType.PROMPT, **kwargs):
    return Post.objects.create(
        author=author,
        category=category,
        post_type=post_type,
        title=title,
        **kwargs,
    )


class FeedServiceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="feed-author",
            email="feed-author@example.com",
            password="test-password",
        )
        category = Category.objects.create(name="Feed category", slug="feed-category")
        self.older_post = _create_post(self.user, category, "Older prompt")
        self.newer_post = _create_post(self.user, category, "Newer prompt")
        now = timezone.now()
        Post.objects.filter(pk=self.older_post.pk).update(created_at=now - timedelta(hours=2))
        Post.objects.filter(pk=self.newer_post.pk).update(created_at=now - timedelta(hours=1))

        self.viewer = get_user_model().objects.create_user(
            username="feed-viewer",
            email="feed-viewer@example.com",
            password="test-password",
        )
        followed_author = get_user_model().objects.create_user(
            username="followed-author",
            email="followed-author@example.com",
            password="test-password",
        )
        unfollowed_author = get_user_model().objects.create_user(
            username="unfollowed-author",
            email="unfollowed-author@example.com",
            password="test-password",
        )
        Follow.objects.create(follower=self.viewer, following=followed_author)
        self.followed_post = _create_post(followed_author, category, "Followed author prompt")
        self.unfollowed_post = _create_post(unfollowed_author, category, "Unfollowed author prompt")
        self.copied_post = _create_post(followed_author, category, "Copied prompt")
        self.viewed_post = _create_post(unfollowed_author, category, "Viewed prompt")
        PostCopy.objects.create(post=self.copied_post, user=self.viewer)
        for _ in range(5):
            PostView.objects.create(post=self.viewed_post, user=self.viewer)
        Post.objects.filter(pk=self.followed_post.pk).update(
            created_at=now - timedelta(hours=3),
        )
        Post.objects.filter(pk=self.unfollowed_post.pk).update(
            created_at=now - timedelta(hours=4),
        )
        Post.objects.filter(pk=self.copied_post.pk).update(
            created_at=now - timedelta(hours=5),
        )
        Post.objects.filter(pk=self.viewed_post.pk).update(
            created_at=now - timedelta(hours=6),
        )

    def test_latest_feed_returns_newest_post_first_with_a_next_cursor(self):
        page = get_latest_feed(page_size=1)

        self.assertEqual([item["id"] for item in page["results"]], [self.newer_post.id])
        self.assertIsNotNone(page["next_cursor"])

    def test_latest_cursor_returns_each_post_once(self):
        first_page = get_latest_feed(page_size=1)
        second_page = get_latest_feed(cursor=first_page["next_cursor"], page_size=1)

        self.assertEqual([item["id"] for item in second_page["results"]], [self.older_post.id])

    def test_following_feed_excludes_posts_by_unfollowed_authors(self):
        page = get_following_feed(self.viewer, page_size=20)

        result_ids = [item["id"] for item in page["results"]]
        self.assertIn(self.followed_post.id, result_ids)
        self.assertNotIn(self.unfollowed_post.id, result_ids)

    def test_trending_ranks_copy_above_equal_recent_view_activity(self):
        page = get_trending_feed(page_size=20)

        self.assertEqual(page["results"][0]["id"], self.copied_post.id)

    def test_trending_excludes_posts_older_than_thirty_days(self):
        old_post = _create_post(self.user, self.older_post.category, "Old but popular prompt")
        Post.objects.filter(pk=old_post.pk).update(
            created_at=timezone.now() - timedelta(days=31),
        )
        for _ in range(10):
            PostCopy.objects.create(post=old_post, user=self.viewer)

        page = get_trending_feed(page_size=20)

        self.assertNotIn(old_post.id, [item["id"] for item in page["results"]])


class FeedApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="api-feed-author",
            email="api-feed-author@example.com",
            password="test-password",
        )
        category = Category.objects.create(name="API feeds", slug="api-feeds")
        self.post = _create_post(self.user, category, "Feed API prompt")

    def test_latest_endpoint_returns_json_page(self):
        response = self.client.get(reverse("posts:feed-latest"), {"page_size": 1})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["results"]), 1)
        self.assertEqual(response.json()["results"][0]["id"], self.post.id)

    def test_anonymous_following_endpoint_returns_json_401(self):
        response = self.client.get(reverse("posts:feed-following"))

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"error": "Authentication required."})

    def test_feed_endpoint_rejects_invalid_page_size(self):
        response = self.client.get(reverse("posts:feed-latest"), {"page_size": "0"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            {"error": "page_size must be an integer between 1 and 50."},
        )

    def test_feed_endpoint_rejects_an_invalid_cursor(self):
        response = self.client.get(reverse("posts:feed-latest"), {"cursor": "not-a-cursor"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "Invalid cursor."})

    def test_explore_endpoint_returns_discovery_sections(self):
        response = self.client.get(reverse("posts:explore"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            set(response.json()),
            {"latest", "trending", "popular_categories", "popular_creators"},
        )


class FeedQueryTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(
            username="query-author",
            email="query-author@example.com",
            password="test-password",
        )
        category = Category.objects.create(name="Query category", slug="query-category")
        tag = Tag.objects.create(
            name="efficient",
            slug="efficient",
        )
        for index in range(5):
            post = _create_post(user, category, f"Query prompt {index}")
            post.tags.add(tag)

    def test_latest_feed_serializes_five_tagged_posts_in_two_queries(self):
        with CaptureQueriesContext(connection) as queries:
            page = get_latest_feed(page_size=5)

        self.assertEqual(len(page["results"]), 5)
        self.assertEqual(len(queries), 2)


class SearchServiceTests(TestCase):
    def setUp(self):
        self.author = get_user_model().objects.create_user(
            username="picasso",
            email="picasso@example.com",
            password="test-password",
        )
        self.writing = Category.objects.create(name="Writing", slug="writing")
        self.art = Category.objects.create(name="Art", slug="art")
        self.tag = Tag.objects.create(name="midjourney", slug="midjourney")
        self.prompt_post = _create_post(
            self.author,
            self.writing,
            "Cyberpunk storyteller",
            prompt="Write a cyberpunk story about memory.",
            ai_model="GPT-5",
        )
        self.image_post = _create_post(
            self.author,
            self.art,
            "Neon city render",
            post_type=Post.PostType.IMAGE,
            prompt="Neon city at dusk, ultra detailed",
            ai_model="Midjourney",
        )
        self.image_post.tags.add(self.tag)

    def test_matches_title_prompt_description_and_ai_model(self):
        self.assertEqual(
            {p["id"] for p in search_posts("cyberpunk")["results"]},
            {self.prompt_post.id},
        )
        self.assertEqual(
            {p["id"] for p in search_posts("midjourney")["results"]},
            {self.image_post.id},
        )

    def test_matches_creator_username(self):
        page = search_posts("picasso")

        self.assertEqual(
            {p["id"] for p in page["results"]},
            {self.prompt_post.id, self.image_post.id},
        )

    def test_filters_by_post_type_and_category(self):
        page = search_posts("", post_type=Post.PostType.IMAGE, category_slug="art")

        self.assertEqual([p["id"] for p in page["results"]], [self.image_post.id])

    def test_filter_by_tag_slug(self):
        page = search_posts("", tag_slug="midjourney")

        self.assertEqual([p["id"] for p in page["results"]], [self.image_post.id])

    def test_search_api_returns_results(self):
        response = self.client.get(reverse("posts:search"), {"q": "neon"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual([p["id"] for p in response.json()["results"]], [self.image_post.id])

    def test_categories_and_tags_endpoints(self):
        categories = self.client.get(reverse("posts:categories")).json()["results"]
        self.assertEqual(
            {c["slug"] for c in categories},
            {"writing", "art"},
        )

        tags = self.client.get(reverse("posts:tags")).json()["results"]
        self.assertEqual([t["slug"] for t in tags], ["midjourney"])

        category_page = self.client.get(reverse("posts:category-posts", args=["art"])).json()
        self.assertEqual([p["id"] for p in category_page["results"]], [self.image_post.id])


class PostCrudApiTests(TestCase):
    def setUp(self):
        self.author = get_user_model().objects.create_user(
            username="crud-author",
            email="crud-author@example.com",
            password="test-password",
        )
        self.other = get_user_model().objects.create_user(
            username="crud-other",
            email="crud-other@example.com",
            password="test-password",
        )
        self.category = Category.objects.create(name="CRUD", slug="crud")
        self.post = _create_post(self.author, self.category, "Original title")

    def _create_payload(self, **overrides):
        payload = {
            "post_type": "prompt",
            "title": "Brand new prompt",
            "description": "desc",
            "prompt": "Do something amazing",
            "ai_model": "GPT-5",
            "category_id": self.category.id,
        }
        payload.update(overrides)
        return payload

    def test_anonymous_user_cannot_create(self):
        response = self.client.post(
            reverse("posts:post-create"),
            self._create_payload(),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)  # JSON unauthorized (API compat)

    def test_authenticated_user_can_create_a_post(self):
        self.client.force_login(self.author)

        response = self.client.post(
            reverse("posts:post-create"),
            self._create_payload(tag_ids=[]),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["post"]["title"], "Brand new prompt")
        self.assertTrue(Post.objects.filter(title="Brand new prompt").exists())

    def test_create_rejects_invalid_payload(self):
        self.client.force_login(self.author)

        response = self.client.post(
            reverse("posts:post-create"),
            {"title": ""},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("errors", response.json())

    def test_detail_returns_serialized_post(self):
        response = self.client.get(reverse("posts:post-detail", args=[self.post.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["post"]["id"], self.post.pk)

    def test_only_owner_can_update(self):
        self.client.force_login(self.other)

        response = self.client.patch(
            reverse("posts:post-update", args=[self.post.pk]),
            {"title": "Hacked"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)

    def test_owner_can_update(self):
        self.client.force_login(self.author)

        response = self.client.patch(
            reverse("posts:post-update", args=[self.post.pk]),
            {"title": "Updated title"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.post.refresh_from_db()
        self.assertEqual(self.post.title, "Updated title")

    def test_only_owner_can_delete(self):
        self.client.force_login(self.other)

        response = self.client.delete(reverse("posts:post-delete", args=[self.post.pk]))

        self.assertEqual(response.status_code, 403)

    def test_owner_can_delete(self):
        self.client.force_login(self.author)

        response = self.client.delete(reverse("posts:post-delete", args=[self.post.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Post.objects.filter(pk=self.post.pk).exists())


class AIModelSelectTests(TestCase):
    """Posters pick the AI model from the admin-maintained list; never a text box."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="model-picker",
            email="model-picker@example.com",
            password="test-password",
        )
        self.category = Category.objects.create(name="Models", slug="models")
        self.create_url = reverse("web:create")
        self.api_url = reverse("posts:post-create")

    def _payload(self, **overrides):
        payload = {
            "post_type": "prompt",
            "title": "Modelled prompt",
            "prompt": "Do something amazing",
            "ai_model": "GPT-5",
            "category_id": self.category.id,
        }
        payload.update(overrides)
        return payload

    def test_the_seed_migration_makes_the_list_non_empty(self):
        from imagegen.models import AIModel

        names = AIModel.active_names()
        self.assertIn("GPT-5", names)
        self.assertIn("Midjourney", names)

    def test_the_create_page_offers_a_select_not_a_text_box(self):
        self.client.force_login(self.user)

        response = self.client.get(self.create_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<select name="ai_model">')
        self.assertNotContains(response, 'type="text" name="ai_model"')
        # A seeded option is rendered, and the empty option is the default.
        self.assertContains(response, ">GPT-5</option>")

    def test_a_seeded_model_is_accepted(self):
        self.client.force_login(self.user)

        response = self.client.post(self.api_url, self._payload(), content_type="application/json")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["post"]["ai_model"], "GPT-5")

    def test_the_canonical_spelling_is_stored(self):
        self.client.force_login(self.user)

        response = self.client.post(
            self.api_url,
            self._payload(ai_model="gpt-5"),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["post"]["ai_model"], "GPT-5")

    def test_a_hand_typed_model_is_rejected(self):
        self.client.force_login(self.user)

        response = self.client.post(
            self.api_url,
            self._payload(ai_model="MyInventedModel"),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("ai_model", response.json()["errors"])
        self.assertFalse(Post.objects.filter(title="Modelled prompt").exists())

    def test_an_inactive_model_is_not_selectable(self):
        from imagegen.models import AIModel

        AIModel.objects.filter(name="GPT-5").update(is_active=False)
        self.client.force_login(self.user)

        response = self.client.post(self.api_url, self._payload(), content_type="application/json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("ai_model", response.json()["errors"])

    def test_an_empty_model_is_allowed(self):
        self.client.force_login(self.user)

        response = self.client.post(
            self.api_url, self._payload(ai_model=""), content_type="application/json"
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["post"]["ai_model"], "")

    def test_an_unconfigured_install_still_accepts_the_api(self):
        """No rows at all = the operator hasn't set the list up; don't brick the API."""
        from imagegen.models import AIModel

        AIModel.objects.all().delete()
        self.client.force_login(self.user)

        response = self.client.post(
            self.api_url,
            self._payload(ai_model="WhateverModel"),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["post"]["ai_model"], "WhateverModel")

    def test_updates_are_validated_too(self):
        from posts.views import _clean_ai_model

        self.assertIsNone(_clean_ai_model("NotOnTheList"))
        self.assertEqual(_clean_ai_model(""), "")
        self.assertEqual(_clean_ai_model(None), "")
        self.assertEqual(_clean_ai_model("  gpt-5  "), "GPT-5")


class MediaPlayerMarkupTests(TestCase):
    """Video/audio posts are handed to the platform player, never native chrome.

    ``data-media-player`` is what static/js/player.js upgrades (base.html loads
    it on every page); without it a post would fall back to the browser's own
    controls — or to nothing at all.
    """

    def setUp(self):
        self.author = get_user_model().objects.create_user(
            username="media-author",
            email="media-author@example.com",
            password="test-password",
        )
        self.category = Category.objects.create(name="Media", slug="media")

    def _media_post(self, post_type, filename, content):
        post = _create_post(
            self.author, self.category, f"A {post_type} post", post_type=post_type
        )
        # Attach bytes directly: this test asserts the page's markup, not the
        # upload validator (covered by posts.test_validation).
        getattr(post, post_type).save(filename, ContentFile(content), save=True)
        return post

    def test_a_video_post_renders_the_platform_player(self):
        post = self._media_post(Post.PostType.VIDEO, "clip.mp4", b"fake-mp4-bytes")

        response = self.client.get(reverse("web:post-detail", args=[post.slug]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<video src=', count=1)
        self.assertContains(response, "data-media-player")
        # The player script ships on the same page.
        self.assertContains(response, "js/player.js")
        # Native controls must never be offered as a fallback.
        self.assertNotContains(response, "<video src=\"" + post.video.url + "\" controls")

    def test_an_audio_post_renders_the_audio_card(self):
        post = self._media_post(Post.PostType.AUDIO, "track.mp3", b"fake-mp3-bytes")

        response = self.client.get(reverse("web:post-detail", args=[post.slug]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<audio src=', count=1)
        self.assertContains(response, "data-media-player")
        self.assertContains(response, 'class="detail-audio-card"')
        self.assertContains(response, "js/player.js")

    def test_the_create_page_also_loads_the_player(self):
        """The create form previews media with the same player."""
        response = self.client.get(reverse("web:create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "js/player.js")
