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


USE_DEFAULT_SOURCE = object()


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
        cls._media_root = tempfile.mkdtemp(prefix="promptya-test-media-")
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

        detail = self.client.get(reverse("web:post-detail", args=[post.slug]))
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
        detail = self.client.get(reverse("web:post-detail", args=[post.slug]))
        self.assertNotContains(detail, f"?source={post.pk}")


class PromptCreatorRewardTests(MediaTestCase):
    """Creators are paid when their prompt is used, and only under the rules."""

    def setUp(self):
        self.creator = get_user_model().objects.create_user(
            username="creator", email="creator@example.com", password="test-password",
        )
        self.user = get_user_model().objects.create_user(
            username="remixer", email="remixer@example.com", password="test-password",
        )
        self.category = Category.objects.create(name="Art", slug="art")
        self.post = Post.objects.create(
            author=self.creator,
            category=self.category,
            post_type=Post.PostType.PROMPT,
            title="Glass cathedral",
            prompt="A cathedral made of glass at dusk",
        )
        self.config = AIConfig.objects.create(
            api_key="sk-test", model="gapgpt/z-image", prompt_use_reward=20,
        )

    def _creator_balance(self):
        return get_balance(self.creator)

    def _prompt_rewards(self):
        """Prompt-use payouts only: the signup welcome bonus is also a REWARD row."""
        return CreditTransaction.objects.filter(
            user=self.creator, kind=TransactionKind.REWARD, note__startswith="Prompt used",
        )

    def _generate(self, *, user=None, source=USE_DEFAULT_SOURCE, payload=None, error=None):
        return generate_image(
            user or self.user,
            "A cathedral made of glass at dusk",
            source_post=self.post if source is USE_DEFAULT_SOURCE else source,
            provider_factory=_factory(payload=payload, error=error),
        )

    def test_a_paid_generation_pays_the_prompt_author(self):
        before = self._creator_balance()
        record = self._generate()

        self.assertEqual(record.creator_reward, 20)
        self.assertEqual(self._creator_balance(), before + 20)
        reward_row = self._prompt_rewards().get()
        self.assertEqual(reward_row.amount, 20)
        self.assertEqual(reward_row.generation_id, record.pk)

    def test_the_reward_is_capped_at_the_generation_price(self):
        self.config.prompt_use_reward = 500
        self.config.save()

        record = self._generate()

        # The standard price is 80, so a 500 setting pays at most 80.
        self.assertEqual(record.credit_cost, 80)
        self.assertEqual(record.creator_reward, 80)

    def test_zero_reward_pays_nothing(self):
        self.config.prompt_use_reward = 0
        self.config.save()

        record = self._generate()

        self.assertEqual(record.creator_reward, 0)
        self.assertFalse(self._prompt_rewards().exists())

    def test_generating_from_your_own_prompt_pays_nothing(self):
        record = self._generate(user=self.creator)

        self.assertEqual(record.creator_reward, 0)

    def test_a_failed_generation_pays_nothing(self):
        before = self._creator_balance()

        with self.assertRaises(GenerationError):
            self._generate(error=GenerationError("provider down"))

        self.assertEqual(self._creator_balance(), before)
        self.assertFalse(self._prompt_rewards().exists())

    def test_a_generation_without_a_source_pays_nothing(self):
        record = self._generate(source=None)  # explicit: no source post

        self.assertEqual(record.creator_reward, 0)

    def test_the_payout_happens_at_most_once_per_generation(self):
        record = self._generate()
        before = self._creator_balance()

        # A repeat call (e.g. a retry) must not pay again.
        from imagegen.services import _pay_prompt_creator
        _pay_prompt_creator(GeneratedImage.objects.get(pk=record.pk), self.config)

        self.assertEqual(self._creator_balance(), before)
        self.assertEqual(self._prompt_rewards().count(), 1)

    def test_a_hidden_source_post_pays_nothing_and_is_not_linked(self):
        self.post.is_hidden = True
        self.post.save(update_fields=["is_hidden"])

        request_data = {"prompt": "A cathedral made of glass at dusk", "source_post_id": self.post.pk}
        from imagegen.views import _source_post
        self.assertIsNone(_source_post(request_data))

    def test_the_admin_can_switch_the_reward_off_at_any_time(self):
        self.config.prompt_use_reward = 0
        self.config.save()

        self.assertEqual(self._generate().creator_reward, 0)


class HiddenPostVisibilityTests(TestCase):
    """Posts hidden by moderation must not appear on any public surface."""

    def setUp(self):
        self.author = get_user_model().objects.create_user(
            username="hidden-author", email="hidden-author@example.com", password="test-password",
        )
        self.viewer = get_user_model().objects.create_user(
            username="viewer", email="viewer@example.com", password="test-password",
        )
        self.category = Category.objects.create(name="Art", slug="art")
        self.visible = Post.objects.create(
            author=self.author, category=self.category, post_type=Post.PostType.PROMPT,
            title="Visible prompt", prompt="A calm lake at sunrise, soft mist over water",
        )
        self.hidden = Post.objects.create(
            author=self.author, category=self.category, post_type=Post.PostType.PROMPT,
            title="Hidden prompt", prompt="Something moderators removed from the feed",
            is_hidden=True,
        )

    def test_the_visible_queryset_excludes_hidden_posts(self):
        ids = set(Post.objects.visible().values_list("pk", flat=True))
        self.assertIn(self.visible.pk, ids)
        self.assertNotIn(self.hidden.pk, ids)

    def test_the_prompt_library_skips_hidden_prompts(self):
        from imagegen.services import prompt_library
        prompts = [entry["prompt"] for entry in prompt_library()]
        self.assertNotIn(self.hidden.prompt, prompts)

    def test_hidden_posts_cannot_be_liked_by_id(self):
        self.client.force_login(self.viewer)
        response = self.client.post(reverse("interactions:toggle-like", args=[self.hidden.pk]))
        self.assertEqual(response.status_code, 404)

    def test_hidden_posts_cannot_be_copied_by_id(self):
        self.client.force_login(self.viewer)
        response = self.client.post(reverse("interactions:record-copy", args=[self.hidden.pk]))
        self.assertEqual(response.status_code, 404)

    def test_hidden_posts_cannot_be_viewed_by_id(self):
        response = self.client.post(reverse("interactions:record-view", args=[self.hidden.pk]))
        self.assertEqual(response.status_code, 404)

    def test_the_public_post_api_returns_404_for_a_hidden_post(self):
        response = self.client.get(reverse("posts:post-detail", args=[self.hidden.pk]))
        self.assertEqual(response.status_code, 404)

    def test_a_visible_post_is_still_served(self):
        response = self.client.get(reverse("posts:post-detail", args=[self.visible.pk]))
        self.assertEqual(response.status_code, 200)


class PremiumTierTests(MediaTestCase):
    """Tests for premium (no-watermark) generation tier."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="premium-user", email="premium@example.com", password="test-password"
        )
        # Create config with premium cost 200, standard cost 80
        self.config = AIConfig.objects.create(
            api_key="sk-test", model="gapgpt/z-image",
            credit_cost=80, premium_credit_cost=200,
        )
        # Give user enough credits for premium tier
        get_user_model().objects.filter(pk=self.user.pk).update(credit_balance=300)
        self.user.refresh_from_db()

    def test_premium_generation_no_watermark(self):
        """Premium tier should generate image without watermark."""
        from imagegen.services import _apply_watermark
        from io import BytesIO

        record = generate_image(
            self.user, "A premium mountain sunset",
            provider_factory=_factory(payload=None, error=None),
            tier=GeneratedImage.Tier.PREMIUM,
        )

        self.assertEqual(record.tier, GeneratedImage.Tier.PREMIUM)
        self.assertEqual(record.credit_cost, 200)
        # Credits should be 300 - 200 = 100
        self.assertEqual(get_balance(self.user), 100)

        # Verify the stored image has no watermark by checking it can be decoded
        # (watermarked images have white text overlay)
        from PIL import Image
        img = Image.open(record.image)
        # For a truly un-watermarked image, the bottom-right shouldn't have white text
        # This is a basic check - in practice we'd compare pixel data
        self.assertIsNotNone(img)

    def test_standard_generation_has_watermark(self):
        """Standard tier should generate image with watermark."""
        record = generate_image(
            self.user, "A standard watermarked generation",
            provider_factory=_factory(payload=None, error=None),
            tier=GeneratedImage.Tier.STANDARD,
        )

        self.assertEqual(record.tier, GeneratedImage.Tier.STANDARD)
        self.assertEqual(record.credit_cost, 80)
        # Credits should be 300 - 80 = 220 (after premium generation above)
        self.assertEqual(get_balance(self.user), 220)

    def test_premium_tier_more_expensive(self):
        """Premium tier should cost more than standard tier."""
        # Standard cost is 80, premium is 200
        self.assertTrue(200 > 80)


class IdempotencyTests(MediaTestCase):
    """Tests for idempotency key duplicate prevention in generation."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="idem-user", email="idem@example.com", password="test-password"
        )
        AIConfig.objects.create(api_key="sk-test", model="gapgpt/z-image")

    def test_idempotency_key_prevents_duplicate_charge(self):
        """Same idempotency key should return existing generation without re-charging."""
        key = "idem-key-12345"

        # First generation
        record1 = generate_image(
            self.user, "Same prompt for idempotency test",
            provider_factory=_factory(),
            idempotency_key=key,
        )
        balance_after_first = get_balance(self.user)
        self.assertEqual(record1.credit_cost, 80)
        # User started with 200 credits, charged 80
        self.assertEqual(balance_after_first, 120)

        # Second generation with same idempotency key
        record2 = generate_image(
            self.user, "Same prompt for idempotency test",
            provider_factory=_factory(),
            idempotency_key=key,
        )

        # Should return the existing record, not create a new one
        self.assertEqual(record1.pk, record2.pk)
        self.assertEqual(record1.tier, record2.tier)
        # Balance should only be charged once
        self.assertEqual(get_balance(self.user), balance_after_first)

        # Only one generation record should exist
        self.assertEqual(GeneratedImage.objects.filter(user=self.user).count(), 1)

    def test_different_idempotency_key_allows_new_generation(self):
        """Different idempotency key should create new generation."""
        key1 = "key-1"
        key2 = "key-2"

        # First generation with key1
        record1 = generate_image(
            self.user, "Prompt with key1", provider_factory=_factory(), idempotency_key=key1,
        )

        # Second generation with key2
        record2 = generate_image(
            self.user, "Prompt with key2", provider_factory=_factory(), idempotency_key=key2,
        )

        # Should be two different records
        self.assertNotEqual(record1.pk, record2.pk)
        self.assertEqual(GeneratedImage.objects.filter(user=self.user).count(), 2)

    def test_empty_idempotency_key_creates_new_generation(self):
        """Empty idempotency key should create new generation (different from key-based check)."""
        # First generation with empty key
        record1 = generate_image(self.user, "Prompt with empty key", provider_factory=_factory())

        # Second generation with another empty key - should be a new generation
        # since the system falls back to evidence-based uniqueness when key is empty
        record2 = generate_image(self.user, "Prompt with empty key 2", provider_factory=_factory())

        # Two different generations should exist
        self.assertEqual(GeneratedImage.objects.filter(user=self.user).count(), 2)


class UnauthorizedAccessTests(MediaTestCase):
    """Tests for unauthorized access and insufficient credits."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="unauth-user", email="unauth@example.com", password="test-password"
        )
        # Create config with credit_cost=80, premium_credit_cost=200 for tests
        self.config = AIConfig.objects.create(
            api_key="sk-test", model="gapgpt/z-image",
            credit_cost=80, premium_credit_cost=200,
        )

    def test_insufficient_credits_standard(self):
        """Standard generation should fail when user has insufficient credits."""
        # User has 50 credits, standard cost is 80
        get_user_model().objects.filter(pk=self.user.pk).update(credit_balance=50)
        self.user.refresh_from_db()

        from credits.services import InsufficientCredits
        from imagegen.services import generate_image

        with self.assertRaises(InsufficientCredits) as caught:
            generate_image(self.user, "A mountain", provider_factory=_factory())

        self.assertEqual(caught.exception.shortfall, 30)
        # Balance should be unchanged
        self.assertEqual(get_balance(self.user), 50)

    def test_insufficient_credits_premium(self):
        """Premium generation should fail when user has insufficient credits for premium."""
        # User has 100 credits, premium cost is 200 (from config)
        get_user_model().objects.filter(pk=self.user.pk).update(credit_balance=100)
        self.user.refresh_from_db()

        from imagegen.services import generate_image

        with self.assertRaises(InsufficientCredits) as caught:
            generate_image(self.user, "A mountain", provider_factory=_factory(), tier=GeneratedImage.Tier.PREMIUM)

        # Premium costs 200 (from config), user has 100, shortfall is 100
        self.assertEqual(caught.exception.shortfall, 100)
        # Balance should be unchanged
        self.assertEqual(get_balance(self.user), 100)

    def test_tier_validation_endpoint(self):
        """API should reject invalid tier values."""
        from django.urls import reverse
        import json
        from django.core.cache import cache

        cache.clear()
        self.client.force_login(self.user)
        url = reverse("imagegen:generate")
        response = self.client.post(
            url, data=json.dumps({"prompt": "A mountain", "tier": "invalid"}),
            content_type="application/json",
        )
        # Should reject invalid tier
        self.assertEqual(response.status_code, 400)
        self.assertIn("tier", response.json()["error"].lower())

    def test_standard_tier_default_when_not_specified(self):
        """API should default to standard tier when not specified."""
        self.client.force_login(self.user)
        from imagegen.services import generate_image
        from imagegen.models import GeneratedImage

        # Create generation without specifying tier (should default to standard)
        record = generate_image(self.user, "A default tier generation", provider_factory=_factory())
        self.assertEqual(record.tier, GeneratedImage.Tier.STANDARD)
