"""Tests for moderation: reports, blocking, restrictions, anti-spam and audits.

The rules under test are security- and trust-sensitive, so this file exercises
the negative paths as deliberately as the happy ones: who may report, who may
block, what a restricted account may still do, and what moderation actions leave
behind in the audit log.
"""

import json

from django.contrib import admin
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.cookie import CookieStorage
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from account.admin import CustomUserAdmin
from account.models import CustomUser
from core.models import AuditLog
from interactions.models import Comment, Follow
from moderation import antispam, services
from moderation.models import Block, Report
from posts.models import Category, Post
from posts.services import post_list_queryset


def _user(username, **extra):
    return get_user_model().objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="test-password",
        **extra,
    )


def _make_post(author, title="A reportable prompt"):
    category, _ = Category.objects.get_or_create(name="Writing", slug="writing")
    return Post.objects.create(
        author=author,
        category=category,
        post_type=Post.PostType.PROMPT,
        title=title,
    )


class BlockServiceTests(TestCase):
    def setUp(self):
        self.alice = _user("alice")
        self.bob = _user("bob")

    def test_self_block_is_refused(self):
        with self.assertRaises(ValidationError):
            services.block_user(self.alice, self.alice)

        self.assertFalse(Block.objects.exists())

    def test_blocking_is_idempotent(self):
        services.block_user(self.alice, self.bob)
        services.block_user(self.alice, self.bob)

        self.assertEqual(Block.objects.count(), 1)

    def test_blocked_ids_are_symmetric(self):
        services.block_user(self.alice, self.bob)

        self.assertIn(self.bob.pk, services.blocked_user_ids(self.alice))
        self.assertIn(self.alice.pk, services.blocked_user_ids(self.bob))

    def test_blocked_authors_leave_the_viewer_feed(self):
        post = _make_post(self.bob)
        visible_to_alice = post_list_queryset(self.alice)
        self.assertIn(post.pk, visible_to_alice.values_list("pk", flat=True))

        services.block_user(self.alice, self.bob)
        # A fresh instance, because blocked_user_ids caches per object for the
        # life of a request and this test reuses one.
        self.alice = get_user_model().objects.get(pk=self.alice.pk)
        self.assertNotIn(
            post.pk,
            post_list_queryset(self.alice).values_list("pk", flat=True),
        )

    def test_is_blocked_between_is_false_for_the_same_user(self):
        self.assertFalse(services.is_blocked_between(self.alice, self.alice))


class ReportServiceTests(TestCase):
    def setUp(self):
        self.reporter = _user("reporter")
        self.author = _user("author")
        self.post = _make_post(self.author)

    def test_report_requires_exactly_one_target(self):
        with self.assertRaises(ValidationError):
            services.create_report(reporter=self.reporter, reason="spam")

        with self.assertRaises(ValidationError):
            services.create_report(
                reporter=self.reporter,
                reason="spam",
                target_post=self.post,
                target_user=self.author,
            )

    def test_cannot_report_own_content(self):
        own = _make_post(self.reporter, "My own prompt")

        with self.assertRaises(ValidationError):
            services.create_report(
                reporter=self.reporter, reason="spam", target_post=own
            )

    def test_invalid_reason_is_refused(self):
        with self.assertRaises(ValidationError):
            services.create_report(
                reporter=self.reporter, reason="not-a-reason", target_post=self.post
            )

    def test_duplicate_open_report_is_refused(self):
        services.create_report(
            reporter=self.reporter, reason="spam", target_post=self.post
        )

        with self.assertRaises(services.AlreadyReported):
            services.create_report(
                reporter=self.reporter, reason="harassment", target_post=self.post
            )

    def test_a_dismissed_report_allows_a_new_one(self):
        first = services.create_report(
            reporter=self.reporter, reason="spam", target_post=self.post
        )
        services.resolve_report(first, status=Report.Status.DISMISSED)

        second = services.create_report(
            reporter=self.reporter, reason="harassment", target_post=self.post
        )

        self.assertNotEqual(first.pk, second.pk)

    def test_snapshot_captures_the_target(self):
        report = services.create_report(
            reporter=self.reporter, reason="spam", target_post=self.post
        )

        self.assertIn(self.post.title, report.content_snapshot)

    def test_resolve_report_stamps_the_actor(self):
        report = services.create_report(
            reporter=self.reporter, reason="spam", target_post=self.post
        )
        services.resolve_report(
            report,
            status=Report.Status.ACTIONED,
            actor=self.author,
            note="removed",
        )
        report.refresh_from_db()

        self.assertEqual(report.status, Report.Status.ACTIONED)
        self.assertEqual(report.resolved_by, self.author)
        self.assertEqual(report.resolution_note, "removed")


class BlockApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.alice = _user("alice")
        self.bob = _user("bob")

    def test_block_requires_login(self):
        response = self.client.post(
            reverse("moderation:block-user", args=[self.bob.username])
        )

        self.assertEqual(response.status_code, 401)
        self.assertFalse(Block.objects.exists())

    def test_block_then_unblock(self):
        self.client.force_login(self.alice)
        url = reverse("moderation:block-user", args=[self.bob.username])

        created = self.client.post(url)
        self.assertEqual(created.status_code, 201)
        self.assertTrue(created.json()["blocked"])
        self.assertTrue(Block.objects.filter(blocker=self.alice, blocked=self.bob).exists())

        removed = self.client.delete(url)
        self.assertEqual(removed.status_code, 200)
        self.assertFalse(removed.json()["blocked"])
        self.assertFalse(Block.objects.filter(blocker=self.alice, blocked=self.bob).exists())

    def test_cannot_block_self(self):
        self.client.force_login(self.alice)

        response = self.client.post(
            reverse("moderation:block-user", args=[self.alice.username])
        )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(Block.objects.exists())

    def test_list_blocks_lists_only_own_blocks(self):
        _user("carol")
        self.client.force_login(self.alice)
        self.client.post(reverse("moderation:block-user", args=[self.bob.username]))

        response = self.client.get(reverse("moderation:list-blocks"))

        self.assertEqual(response.status_code, 200)
        usernames = [row["username"] for row in response.json()["results"]]
        self.assertEqual(usernames, ["bob"])


class ReportApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.reporter = _user("reporter")
        self.author = _user("author")
        self.post = _make_post(self.author)
        self.url = reverse("moderation:create-report")

    def _post(self, payload):
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_report_requires_login(self):
        response = self._post(
            {"target_type": "post", "target_id": self.post.pk, "reason": "spam"}
        )

        self.assertEqual(response.status_code, 401)
        self.assertFalse(Report.objects.exists())

    def test_report_post_creates_a_row(self):
        self.client.force_login(self.reporter)

        response = self._post(
            {"target_type": "post", "target_id": self.post.pk, "reason": "spam"}
        )

        self.assertEqual(response.status_code, 201)
        report = Report.objects.get()
        self.assertEqual(report.reporter, self.reporter)
        self.assertEqual(report.target_post, self.post)
        self.assertEqual(report.status, Report.Status.PENDING)

    def test_invalid_reason_is_rejected(self):
        self.client.force_login(self.reporter)

        response = self._post(
            {"target_type": "post", "target_id": self.post.pk, "reason": "bogus"}
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Report.objects.exists())

    def test_duplicate_report_is_flagged(self):
        self.client.force_login(self.reporter)
        payload = {"target_type": "post", "target_id": self.post.pk, "reason": "spam"}
        self._post(payload)

        response = self._post(payload)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error_code"], "already_reported")
        self.assertEqual(Report.objects.count(), 1)

    def test_unknown_target_is_404(self):
        self.client.force_login(self.reporter)

        response = self._post({"target_type": "post", "target_id": 999999, "reason": "spam"})

        self.assertEqual(response.status_code, 404)

    def test_reporting_own_post_is_rejected(self):
        self.client.force_login(self.author)

        response = self._post(
            {"target_type": "post", "target_id": self.post.pk, "reason": "spam"}
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Report.objects.exists())

    def test_report_spam_is_rate_limited(self):
        self.client.force_login(self.reporter)
        payload = {"target_type": "post", "target_id": self.post.pk, "reason": "spam"}

        for _ in range(20):
            self._post(payload)
        response = self._post(payload)

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["error_code"], "rate_limited")

    def test_can_report_a_comment(self):
        comment = Comment.objects.create(post=self.post, user=self.author, content="hi")
        self.client.force_login(self.reporter)

        response = self._post(
            {"target_type": "comment", "target_id": comment.pk, "reason": "harassment"}
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Report.objects.get().target_comment, comment)


class CommentAndFollowBlockTests(TestCase):
    def setUp(self):
        cache.clear()
        self.alice = _user("alice")
        self.bob = _user("bob")
        self.post = _make_post(self.bob)

    def test_blocked_pair_cannot_comment(self):
        services.block_user(self.alice, self.bob)
        self.client.force_login(self.alice)

        response = self.client.post(
            reverse("interactions:create-comment", args=[self.post.pk]),
            data=json.dumps({"content": "hello"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Comment.objects.exists())

    def test_blocked_pair_cannot_follow(self):
        services.block_user(self.alice, self.bob)
        self.client.force_login(self.alice)

        response = self.client.post(
            reverse("interactions:toggle-follow", args=[self.bob.username])
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Follow.objects.exists())

    def test_blocked_authors_comments_are_hidden_from_the_viewer(self):
        Comment.objects.create(post=self.post, user=self.bob, content="bob says hi")
        self.client.force_login(self.alice)

        visible = self.client.get(reverse("interactions:list-comments", args=[self.post.pk]))
        self.assertEqual(len(visible.json()["results"]), 1)

        services.block_user(self.alice, self.bob)
        hidden = self.client.get(reverse("interactions:list-comments", args=[self.post.pk]))
        self.assertEqual(hidden.json()["results"], [])

    def test_hidden_comments_are_not_listed(self):
        Comment.objects.create(post=self.post, user=self.alice, content="visible")
        Comment.objects.create(
            post=self.post, user=self.bob, content="hidden", is_hidden=True
        )

        response = self.client.get(reverse("interactions:list-comments", args=[self.post.pk]))

        self.assertEqual(
            [row["content"] for row in response.json()["results"]], ["visible"]
        )


class AntiSpamTests(TestCase):
    def setUp(self):
        cache.clear()
        self.author = _user("author")
        self.commenter = _user("commenter")
        self.post = _make_post(self.author)

    def _comment(self, content):
        return self.client.post(
            reverse("interactions:create-comment", args=[self.post.pk]),
            data=json.dumps({"content": content}),
            content_type="application/json",
        )

    def test_module_flags_excessive_links(self):
        self.assertEqual(antispam.looks_like_spam("http://a http://b http://c http://d"), "too_many_links")
        self.assertIsNone(antispam.looks_like_spam("http://a http://b"))

    def test_module_flags_duplicates_ignoring_case(self):
        self.assertEqual(
            antispam.looks_like_spam("Buy now", previous_contents=["buy   NOW"]),
            "duplicate",
        )

    def test_link_spam_comment_is_rejected(self):
        self.client.force_login(self.commenter)

        response = self._comment("http://1 http://2 http://3 http://4")

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Comment.objects.exists())

    def test_duplicate_comment_is_rejected(self):
        self.client.force_login(self.commenter)
        self._comment("Great prompt, thanks!")

        response = self._comment("great prompt, thanks!")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Comment.objects.count(), 1)

    def test_normal_comment_is_accepted(self):
        self.client.force_login(self.commenter)

        response = self._comment("Nice work on this one.")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Comment.objects.count(), 1)


class ModerationStateTests(TestCase):
    def test_expired_suspension_lapses(self):
        user = _user(
            "timed-out",
            moderation_status=CustomUser.ModerationStatus.SUSPENDED,
            moderation_until=timezone.now() - timezone.timedelta(minutes=1),
        )

        self.assertFalse(user.is_suspended)
        self.assertFalse(user.has_active_restriction)

    def test_active_suspension_restricts(self):
        user = _user(
            "suspended",
            moderation_status=CustomUser.ModerationStatus.SUSPENDED,
            moderation_until=timezone.now() + timezone.timedelta(days=1),
        )

        self.assertTrue(user.is_suspended)
        self.assertTrue(user.has_active_restriction)

    def test_banned_and_restricted_flags(self):
        banned = _user("banned", moderation_status=CustomUser.ModerationStatus.BANNED)
        restricted = _user(
            "restricted", moderation_status=CustomUser.ModerationStatus.RESTRICTED
        )

        self.assertTrue(banned.is_banned)
        self.assertTrue(banned.has_active_restriction)
        self.assertTrue(restricted.is_restricted)
        self.assertTrue(restricted.has_active_restriction)


class RestrictionMiddlewareTests(TestCase):
    def setUp(self):
        cache.clear()
        self.author = _user("author")
        self.post = _make_post(self.author)

    def _restricted(self, **extra):
        return _user("restricted", moderation_status=CustomUser.ModerationStatus.RESTRICTED, **extra)

    def test_restricted_user_cannot_like(self):
        user = self._restricted()
        self.client.force_login(user)

        response = self.client.post(
            reverse("interactions:toggle-like", args=[self.post.pk])
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error_code"], "moderation_restricted")

    def test_restricted_user_can_browse(self):
        user = self._restricted()
        self.client.force_login(user)

        response = self.client.get(reverse("interactions:list-comments", args=[self.post.pk]))

        self.assertEqual(response.status_code, 200)

    def test_restricted_user_can_still_report(self):
        user = self._restricted()
        self.client.force_login(user)

        response = self.client.post(
            reverse("moderation:create-report"),
            data=json.dumps(
                {"target_type": "post", "target_id": self.post.pk, "reason": "spam"}
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Report.objects.count(), 1)

    def test_banned_user_cannot_engage(self):
        user = _user(
            "banned",
            moderation_status=CustomUser.ModerationStatus.BANNED,
            is_active=True,
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("interactions:toggle-like", args=[self.post.pk])
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error_code"], "moderation_restricted")

    def test_banned_user_cannot_report(self):
        user = _user(
            "banned",
            moderation_status=CustomUser.ModerationStatus.BANNED,
            is_active=True,
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("moderation:create-report"),
            data=json.dumps(
                {"target_type": "post", "target_id": self.post.pk, "reason": "spam"}
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)

    def test_anonymous_visitor_is_unaffected(self):
        response = self.client.post(reverse("interactions:toggle-like", args=[self.post.pk]))

        # Anonymous is rejected by the view's own auth check (401), not the
        # moderation middleware — proof the middleware did not interfere.
        self.assertEqual(response.status_code, 401)


class LoginGateTests(TestCase):
    def setUp(self):
        cache.clear()
        self.banned = _user(
            "banned",
            moderation_status=CustomUser.ModerationStatus.BANNED,
            is_active=True,
        )

    def test_api_login_refuses_a_banned_account(self):
        response = self.client.post(
            reverse("account:login"),
            data=json.dumps({"username": "banned", "password": "test-password"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)

    def test_login_page_refuses_a_banned_account(self):
        response = self.client.post(
            reverse("login"),
            {"username": "banned", "password": "test-password"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)


class AdminModerationActionTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username="root", email="root@example.com", password="test-password"
        )
        self.target = _user("target")
        self.model_admin = CustomUserAdmin(CustomUser, AdminSite())
        self.factory = RequestFactory()

    def _request(self, user):
        request = self.factory.post("/admin/account/customuser/")
        request.user = user
        request.META["HTTP_USER_AGENT"] = "test"
        # message_user() needs a storage; a real request gets one from
        # MessageMiddleware, a RequestFactory request does not.
        request._messages = CookieStorage(request)
        return request

    def _queryset(self):
        return get_user_model().objects.filter(pk=self.target.pk)

    def test_restrict_sets_state_and_audits(self):
        self.model_admin.restrict_users(self._request(self.admin), self._queryset())
        self.target.refresh_from_db()

        self.assertEqual(self.target.moderation_status, CustomUser.ModerationStatus.RESTRICTED)
        self.assertTrue(
            AuditLog.objects.filter(
                action=AuditLog.Action.USER_RESTRICT,
                target_user=self.target,
                actor=self.admin,
            ).exists()
        )

    def test_ban_deactivates_and_audits(self):
        self.model_admin.ban_users(self._request(self.admin), self._queryset())
        self.target.refresh_from_db()

        self.assertEqual(self.target.moderation_status, CustomUser.ModerationStatus.BANNED)
        self.assertFalse(self.target.is_active)
        self.assertTrue(
            AuditLog.objects.filter(
                action=AuditLog.Action.USER_BAN, target_user=self.target
            ).exists()
        )

    def test_lift_restrictions_reactivates_and_clears_the_deadline(self):
        self.model_admin.ban_users(self._request(self.admin), self._queryset())
        self.model_admin.lift_restrictions(self._request(self.admin), self._queryset())
        self.target.refresh_from_db()

        self.assertEqual(self.target.moderation_status, CustomUser.ModerationStatus.ACTIVE)
        self.assertTrue(self.target.is_active)
        self.assertIsNone(self.target.moderation_until)
        self.assertTrue(
            AuditLog.objects.filter(
                action=AuditLog.Action.USER_UNRESTRICT, target_user=self.target
            ).exists()
        )

    def test_action_without_permission_does_nothing(self):
        staff = _user("staff", is_staff=True)

        self.model_admin.ban_users(self._request(staff), self._queryset())
        self.target.refresh_from_db()

        self.assertEqual(self.target.moderation_status, CustomUser.ModerationStatus.ACTIVE)
        self.assertFalse(AuditLog.objects.filter(target_user=self.target).exists())
