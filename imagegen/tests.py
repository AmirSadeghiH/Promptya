"""Tests for the AI image studio.

Nothing here touches the network: the provider is injected, so these tests
pin the behaviour that matters — what a generation costs, what a failure does
to the wallet, how a reference image is handled, and what the endpoints answer.
"""

import io
import json
import shutil
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from credits.models import CreditTransaction, TransactionKind
from credits.services import SIGNUP_CREDITS, InsufficientCredits, get_balance
from imagegen.client import GenerationError, ImageProvider, ProviderSettings, SourceImage
from imagegen.models import DEFAULT_BASE_URL, AIConfig, GeneratedImage
from imagegen.services import (
    MAX_PROMPT_LENGTH,
    PromptRejected,
    SourceImageRejected,
    credit_payload,
    generate_image,
    prompt_library,
    recent_generations,
)
from posts.models import Category, Post


def _png_bytes(size=32, color=(120, 80, 200)):
    buffer = io.BytesIO()
    Image.new("RGB", (size, size), color).save(buffer, format="PNG")
    return buffer.getvalue()


class FakeProvider:
    """Stands in for the SDK call: returns bytes, or raises on demand."""

    def __init__(self, settings, *, payload=None, error=None):
        self.settings = settings
        self.payload = payload
        self.error = error
        self.calls = []

    def generate(self, prompt, size, source_image=None):
        self.calls.append({"prompt": prompt, "size": size, "source_image": source_image})
        if self.error:
            raise self.error
        return self.payload if self.payload is not None else _png_bytes()


def _factory(*, payload=None, error=None, sink=None):
    def build(settings):
        provider = FakeProvider(settings, payload=payload, error=error)
        if sink is not None:
            sink.append(provider)
        return provider

    return build


class MediaTestCase(TestCase):
    """Keeps generated files out of the real media root."""

    @classmethod
    def setUpClass(cls):
        cls._media_root = tempfile.mkdtemp(prefix="promptly-test-media-")
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._media_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._media_override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)


class GenerationTests(MediaTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="generator",
            email="generator@example.com",
            password="test-password",
        )
        self.config = AIConfig.objects.create(
            api_key="sk-test",
            model="gapgpt/z-image",
            base_url="https://api.gapgpt.app/v1",
            image_size="1024x1024",
        )

    def test_successful_generation_stores_the_image(self):
        record = generate_image(
            self.user, "  A sunset over mountains  ", provider_factory=_factory()
        )

        self.assertEqual(record.status, GeneratedImage.Status.READY)
        self.assertEqual(record.prompt, "A sunset over mountains")
        self.assertTrue(record.image.name.endswith(".png"))
        self.assertTrue(record.image.storage.exists(record.image.name))
        self.assertIsNotNone(record.finished_at)
        self.assertEqual(record.provider_model, "gapgpt/z-image")

    def test_generation_uses_the_configured_size_and_model(self):
        captured = {}

        def build(settings):
            provider = FakeProvider(settings)
            captured["settings"] = settings
            return provider

        generate_image(self.user, "A mountain", provider_factory=build)
        self.assertEqual(captured["settings"].model, "gapgpt/z-image")
        self.assertEqual(captured["settings"].base_url, "https://api.gapgpt.app/v1")

    def test_a_successful_generation_charges_the_configured_cost(self):
        self.assertEqual(get_balance(self.user), SIGNUP_CREDITS)

        generate_image(self.user, "A mountain", provider_factory=_factory())

        self.assertEqual(get_balance(self.user), SIGNUP_CREDITS - 80)
        charge = CreditTransaction.objects.get(kind=TransactionKind.GENERATION)
        self.assertEqual(charge.amount, -80)
        self.assertEqual(charge.balance_after, SIGNUP_CREDITS - 80)

    def test_provider_failure_is_recorded_and_refunded(self):
        with self.assertRaises(GenerationError):
            generate_image(
                self.user,
                "A mountain",
                provider_factory=_factory(error=GenerationError("The provider is down.")),
            )

        record = GeneratedImage.objects.get()
        self.assertEqual(record.status, GeneratedImage.Status.FAILED)
        self.assertEqual(record.error, "The provider is down.")
        self.assertFalse(record.image)
        # The charge was refunded: a failed generation costs nothing.
        self.assertEqual(get_balance(self.user), SIGNUP_CREDITS)
        self.assertTrue(
            CreditTransaction.objects.filter(kind=TransactionKind.REFUND).exists()
        )

    def test_unexpected_provider_bug_becomes_a_generation_error(self):
        with self.assertRaises(GenerationError):
            generate_image(
                self.user,
                "A mountain",
                provider_factory=_factory(error=RuntimeError("boom")),
            )

        record = GeneratedImage.objects.get()
        self.assertEqual(record.status, GeneratedImage.Status.FAILED)
        self.assertTrue(record.error)
        self.assertEqual(get_balance(self.user), SIGNUP_CREDITS)

    def test_non_image_payload_is_rejected(self):
        with self.assertRaises(GenerationError):
            generate_image(
                self.user,
                "A mountain",
                provider_factory=_factory(payload=b"<html>not an image</html>"),
            )
        self.assertEqual(GeneratedImage.objects.get().status, GeneratedImage.Status.FAILED)
        self.assertEqual(get_balance(self.user), SIGNUP_CREDITS)

    def test_empty_prompt_is_rejected(self):
        with self.assertRaises(PromptRejected):
            generate_image(self.user, "   ", provider_factory=_factory())
        self.assertFalse(GeneratedImage.objects.exists())

    def test_overlong_prompt_is_rejected(self):
        with self.assertRaises(PromptRejected):
            generate_image(
                self.user, "x" * (MAX_PROMPT_LENGTH + 1), provider_factory=_factory()
            )

    def test_generation_is_refused_when_credits_run_out(self):
        provider = FakeProvider(ProviderSettings("https://api.example/v1", "sk", "m"))
        called = []

        def build(settings):
            called.append(True)
            return provider

        # 200 credits afford two 80-credit images, and not a third.
        generate_image(self.user, "A mountain", provider_factory=_factory())
        generate_image(self.user, "A mountain", provider_factory=_factory())

        with self.assertRaises(InsufficientCredits):
            generate_image(self.user, "A mountain", provider_factory=build)

        self.assertEqual(called, [])  # the provider was never contacted
        self.assertEqual(GeneratedImage.objects.count(), 2)
        self.assertEqual(get_balance(self.user), SIGNUP_CREDITS - 160)

    def test_generation_is_refused_without_an_api_key(self):
        AIConfig.objects.update(api_key="", is_enabled=True)

        with self.assertRaises(GenerationError):
            generate_image(self.user, "A mountain", provider_factory=_factory())
        self.assertFalse(GeneratedImage.objects.exists())
        self.assertEqual(get_balance(self.user), SIGNUP_CREDITS)

    def test_generation_is_refused_when_disabled(self):
        AIConfig.objects.update(is_enabled=False)

        with self.assertRaises(GenerationError):
            generate_image(self.user, "A mountain", provider_factory=_factory())


class ImageToImageTests(MediaTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="remixer",
            email="remixer@example.com",
            password="test-password",
        )
        self.config = AIConfig.objects.create(api_key="sk-test", model="gapgpt/z-image")

    def _upload(self, *, name="reference.png", content=None, content_type="image/png"):
        return SimpleUploadedFile(name, content or _png_bytes(), content_type=content_type)

    def test_source_image_is_sent_to_the_provider_and_stored(self):
        sink = []
        record = generate_image(
            self.user,
            "Make it winter",
            source_image=self._upload(),
            provider_factory=_factory(sink=sink),
        )

        sent = sink[0].calls[0]["source_image"]
        self.assertIsInstance(sent, SourceImage)
        self.assertTrue(sent.data.startswith(b"\x89PNG"))

        self.assertTrue(record.source_image)
        self.assertTrue(record.source_image.storage.exists(record.source_image.name))
        # The result and its reference live on the same row: that *is* the link.
        self.assertIn("/media/generated_sources/", record.source_image.url)

    def test_text_to_image_sends_no_source_image(self):
        sink = []
        generate_image(self.user, "A mountain", provider_factory=_factory(sink=sink))
        self.assertIsNone(sink[0].calls[0]["source_image"])

    def test_a_disguised_file_is_rejected_and_the_charge_refunded(self):
        with self.assertRaises(SourceImageRejected):
            generate_image(
                self.user,
                "Make it winter",
                source_image=self._upload(
                    name="reference.png",
                    content=b"<?php echo 'not an image'; ?>",
                    content_type="image/png",
                ),
                provider_factory=_factory(),
            )

        self.assertFalse(GeneratedImage.objects.exists())
        self.assertEqual(get_balance(self.user), SIGNUP_CREDITS)

    def test_source_image_is_linked_to_a_source_post(self):
        category = Category.objects.create(name="Art", slug="art")
        post = Post.objects.create(
            author=self.user,
            category=category,
            post_type=Post.PostType.IMAGE,
            title="Source",
            prompt="A cathedral made of glass",
        )
        record = generate_image(
            self.user,
            "A cathedral made of glass",
            source_post=post,
            source_image=self._upload(),
            provider_factory=_factory(),
        )
        self.assertEqual(record.source_post_id, post.pk)
        self.assertEqual(recent_generations(self.user)[0]["source_post_id"], post.pk)


class AIConfigTests(TestCase):
    def test_load_returns_defaults_without_a_row(self):
        config = AIConfig.load()
        self.assertIsNone(config.pk)
        self.assertEqual(config.base_url, DEFAULT_BASE_URL)
        self.assertEqual(config.model, "gapgpt/z-image")
        self.assertFalse(config.is_ready)

    def test_is_ready_requires_a_key_and_the_switch(self):
        config = AIConfig.objects.create(api_key="sk-test")
        self.assertTrue(config.is_ready)

        config.is_enabled = False
        self.assertFalse(config.is_ready)

    def test_credit_cost_is_configurable_per_provider_row(self):
        AIConfig.objects.create(api_key="sk-test", credit_cost=250)
        user = get_user_model().objects.create_user(
            username="priced", email="priced@example.com", password="test-password"
        )
        payload = credit_payload(user)
        self.assertEqual(payload["cost"], 250)
        self.assertFalse(payload["can_afford"])
        self.assertEqual(payload["shortfall"], 50)


class ProviderSettingsTests(TestCase):
    def test_incomplete_settings_are_refused(self):
        settings = ProviderSettings(base_url="", api_key="", model="")
        self.assertFalse(settings.is_complete)
        with self.assertRaises(GenerationError):
            ImageProvider(settings).generate("A mountain", "1024x1024")

    def test_missing_credentials_never_reach_the_network(self):
        settings = ProviderSettings("https://api.example/v1", "", "gapgpt/z-image")
        with self.assertRaises(GenerationError):
            ImageProvider(settings).generate("A mountain", "1024x1024")

    def test_source_image_upload_is_a_mime_typed_file(self):
        source = SourceImage(filename="reference.png", data=b"\x89PNG\r\n\x1a\n")
        name, handle, mime = source.as_upload()
        self.assertEqual(name, "reference.png")
        self.assertEqual(mime, "image/png")
        self.assertEqual(handle.read(), b"\x89PNG\r\n\x1a\n")


class PromptLibraryTests(MediaTestCase):
    def setUp(self):
        self.author = get_user_model().objects.create_user(
            username="librarian",
            email="librarian@example.com",
            password="test-password",
        )
        self.category = Category.objects.create(name="Art", slug="art")

    def _post(self, *, prompt, title="A prompt", image=True, post_type=Post.PostType.IMAGE):
        post = Post.objects.create(
            author=self.author,
            category=self.category,
            post_type=post_type,
            title=title,
            prompt=prompt,
        )
        if image:
            post.image.save(f"{title}.png", ContentFile(_png_bytes()), save=True)
        return post

    def test_library_lists_prompts_with_their_output(self):
        self._post(prompt="A cathedral made of glass")
        self._post(prompt="An astronaut in a garden", post_type=Post.PostType.PROMPT, image=False)

        library = prompt_library()
        prompts = {item["prompt"] for item in library}
        self.assertEqual(prompts, {"A cathedral made of glass", "An astronaut in a garden"})
        with_image = next(item for item in library if item["prompt"] == "A cathedral made of glass")
        self.assertTrue(with_image["image"].startswith("/media/"))
        self.assertEqual(with_image["author"], "librarian")

    def test_image_posts_without_an_upload_are_skipped(self):
        self._post(prompt="No output yet", image=False)
        self.assertEqual(prompt_library(), [])

    def test_empty_prompts_are_skipped(self):
        self._post(prompt="", image=True)
        self.assertEqual(prompt_library(), [])

    def test_duplicate_prompts_collapse(self):
        self._post(prompt="Same prompt", title="First")
        self._post(prompt="Same prompt", title="Second")
        self.assertEqual(len(prompt_library()), 1)


class StudioApiTests(MediaTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="api-user",
            email="api-user@example.com",
            password="test-password",
        )
        self.url = reverse("imagegen:generate")
        self.config = AIConfig.objects.create(api_key="sk-test", model="gapgpt/z-image")

    def _post_json(self, payload):
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_anonymous_request_gets_a_401_json_response(self):
        response = self._post_json({"prompt": "A mountain"})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "Authentication required.")

    def test_get_is_not_allowed(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_successful_generation_returns_the_image_and_wallet(self):
        self.client.force_login(self.user)
        with patch("imagegen.services.ImageProvider", _factory()):
            response = self._post_json({"prompt": "A mountain at dawn"})

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["generation"]["prompt"], "A mountain at dawn")
        self.assertIn("/media/generated_images/", body["generation"]["image"])
        self.assertEqual(body["generation"]["credit_cost"], 80)
        self.assertEqual(body["credits"]["balance"], SIGNUP_CREDITS - 80)
        self.assertEqual(body["credits"]["cost"], 80)

    def test_empty_prompt_is_a_400(self):
        self.client.force_login(self.user)
        with patch("imagegen.services.ImageProvider", _factory()):
            response = self._post_json({"prompt": "   "})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error_code"], "invalid_prompt")

    def test_invalid_json_is_a_400(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, data="{", content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error_code"], "bad_request")

    def test_exhausted_credits_is_a_402_with_the_shortfall(self):
        self.client.force_login(self.user)
        GeneratedImage.objects.create(
            user=self.user, prompt="p", status=GeneratedImage.Status.READY
        )
        # Spend everything but a sliver.
        get_user_model().objects.filter(pk=self.user.pk).update(credit_balance=10)

        with patch("imagegen.services.ImageProvider", _factory()):
            response = self._post_json({"prompt": "A mountain"})

        self.assertEqual(response.status_code, 402)
        body = response.json()
        self.assertEqual(body["error_code"], "insufficient_credits")
        self.assertEqual(body["balance"], 10)
        self.assertEqual(body["required"], 80)
        self.assertEqual(body["shortfall"], 70)
        # A refused request leaves no half-written generation behind.
        self.assertEqual(GeneratedImage.objects.count(), 1)

    def test_provider_failure_is_a_502_and_is_refunded(self):
        self.client.force_login(self.user)
        provider = _factory(error=GenerationError("The provider is down."))
        with patch("imagegen.services.ImageProvider", provider):
            response = self._post_json({"prompt": "A mountain"})

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["error_code"], "provider_error")
        self.assertEqual(response.json()["credits"]["balance"], SIGNUP_CREDITS)
        self.assertEqual(GeneratedImage.objects.get().status, GeneratedImage.Status.FAILED)

    def test_generation_is_refused_when_the_provider_is_unconfigured(self):
        AIConfig.objects.update(api_key="")
        self.client.force_login(self.user)
        response = self._post_json({"prompt": "A mountain"})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["error_code"], "provider_error")

    def test_source_post_is_linked_to_the_generation(self):
        category = Category.objects.create(name="Art", slug="art")
        source = Post.objects.create(
            author=self.user,
            category=category,
            post_type=Post.PostType.PROMPT,
            title="Source",
            prompt="A cathedral made of glass",
        )
        self.client.force_login(self.user)
        with patch("imagegen.services.ImageProvider", _factory()):
            response = self._post_json(
                {"prompt": "A cathedral made of glass", "source_post_id": source.pk}
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["generation"]["source_post_id"], source.pk)

    def test_multipart_upload_generates_from_a_reference_image(self):
        sink = []
        self.client.force_login(self.user)
        with patch("imagegen.services.ImageProvider", _factory(sink=sink)):
            response = self.client.post(
                self.url,
                data={
                    "prompt": "Make it winter",
                    "source_image": SimpleUploadedFile(
                        "reference.png", _png_bytes(), content_type="image/png"
                    ),
                },
            )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertIn("/media/generated_sources/", body["generation"]["source_image"])
        self.assertIsInstance(sink[0].calls[0]["source_image"], SourceImage)

    def test_multipart_upload_rejects_a_fake_image(self):
        self.client.force_login(self.user)
        with patch("imagegen.services.ImageProvider", _factory()):
            response = self.client.post(
                self.url,
                data={
                    "prompt": "Make it winter",
                    "source_image": SimpleUploadedFile(
                        "reference.png", b"not really a png", content_type="image/png"
                    ),
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error_code"], "invalid_image")
        self.assertFalse(GeneratedImage.objects.exists())


class StudioPageTests(MediaTestCase):
    def setUp(self):
        self.url = reverse("web:studio")
        self.author = get_user_model().objects.create_user(
            username="shelf-owner",
            email="shelf@example.com",
            password="test-password",
        )
        self.category = Category.objects.create(name="Art", slug="art")

    def test_page_renders_for_anonymous_visitors(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Log in to generate")

    def test_page_seeds_the_wallet_and_the_shelf(self):
        GeneratedImage.objects.create(
            user=self.author, prompt="A latent idea", status=GeneratedImage.Status.READY
        )
        self.client.force_login(self.author)

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "studio-data")
        self.assertContains(response, "A latent idea")
        data = response.context["studio_data"]
        self.assertEqual(data["credits"]["balance"], SIGNUP_CREDITS)
        self.assertEqual(data["credits"]["cost"], 80)
        self.assertEqual(len(data["generations"]), 1)

    def test_page_lists_the_reward_challenges(self):
        self.client.force_login(self.author)
        response = self.client.get(self.url)
        slugs = {challenge["slug"] for challenge in response.context["challenges"]}
        self.assertEqual(slugs, {"invite_friend", "instagram_share"})
        self.assertContains(response, "Invite a friend")

    def test_library_shows_a_copyable_prompt(self):
        post = Post.objects.create(
            author=self.author,
            category=self.category,
            post_type=Post.PostType.PROMPT,
            title="Glass cathedral",
            prompt="A cathedral made of glass, refracted light",
        )
        response = self.client.get(self.url)
        self.assertContains(response, "A cathedral made of glass, refracted light")
        self.assertContains(response, f'data-post-id="{post.pk}"')

    def test_source_post_prefills_the_studio_and_keeps_the_link(self):
        """The "Use Prompt" flow: ?source=<post id> carries prompt + provenance."""
        source = Post.objects.create(
            author=self.author,
            category=self.category,
            post_type=Post.PostType.IMAGE,
            title="Glass cathedral",
            prompt="A cathedral made of glass, refracted light",
        )
        source.image.save("cathedral.png", ContentFile(_png_bytes()), save=True)

        response = self.client.get(self.url, {"source": source.pk})
        prefill = response.context["prefill"]
        self.assertEqual(prefill["prompt"], "A cathedral made of glass, refracted light")
        self.assertEqual(prefill["source_post_id"], source.pk)
        self.assertEqual(prefill["source_author"], "shelf-owner")
        self.assertContains(response, f"sourcePostId: {source.pk}")
        self.assertContains(response, "A cathedral made of glass, refracted light")

    def test_raw_prompt_parameter_prefills_without_a_source(self):
        response = self.client.get(self.url, {"prompt": "An astronaut in a garden"})
        prefill = response.context["prefill"]
        self.assertEqual(prefill["prompt"], "An astronaut in a garden")
        self.assertIsNone(prefill["source_post_id"])
        self.assertContains(response, "An astronaut in a garden")

    def test_unknown_source_post_falls_back_to_the_raw_prompt(self):
        response = self.client.get(self.url, {"source": "999999", "prompt": "Fallback"})
        self.assertEqual(response.context["prefill"]["prompt"], "Fallback")
        self.assertIsNone(response.context["prefill"]["source_post_id"])

    def test_image_post_offers_a_use_prompt_action(self):
        """Every public image post with a prompt points at the studio."""
        post = Post.objects.create(
            author=self.author,
            category=self.category,
            post_type=Post.PostType.IMAGE,
            title="Glass cathedral",
            prompt="A cathedral made of glass",
        )
        post.image.save("cathedral.png", ContentFile(_png_bytes()), save=True)

        detail = self.client.get(reverse("web:post-detail", args=[post.pk]))
        self.assertContains(detail, f"{self.url}?source={post.pk}")

        home = self.client.get(reverse("web:home"))
        self.assertContains(home, f"{self.url}?source={post.pk}")

    def test_prompt_post_has_no_use_prompt_action(self):
        post = Post.objects.create(
            author=self.author,
            category=self.category,
            post_type=Post.PostType.PROMPT,
            title="Glass cathedral",
            prompt="A cathedral made of glass",
        )
        detail = self.client.get(reverse("web:post-detail", args=[post.pk]))
        self.assertNotContains(detail, f"?source={post.pk}")
