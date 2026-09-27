"""The provider adapter: one prompt in, image bytes out.

Everything provider-specific lives behind this module so the rest of the app
(quota rules, storage, views) never imports the SDK.  Swapping gapgpt for
another OpenAI-compatible endpoint means editing ``ProviderSettings`` and
nothing else, and tests inject a fake provider instead of touching the network.
"""

from __future__ import annotations

import io
import urllib.error
import urllib.request
from dataclasses import dataclass

from posts.validation import MAX_SIZES

try:  # Imported lazily enough that a missing SDK only breaks generation.
    from openai import OpenAI
except ImportError:  # pragma: no cover - depends on the environment
    OpenAI = None

# Downloads are capped at the site's own image limit, so a provider that
# streams something huge cannot fill the disk.
MAX_DOWNLOAD_BYTES = MAX_SIZES["image"]
DOWNLOAD_TIMEOUT_SECONDS = 60
# Some providers hand back a data: URL instead of a link.
DATA_URL_MAX_CHARS = 16 * 1024 * 1024


class GenerationError(RuntimeError):
    """A generation failed. The message is safe to show to the user."""


@dataclass(frozen=True)
class SourceImage:
    """A reference image for image-to-image generation, already validated."""

    filename: str
    data: bytes

    def as_upload(self):
        """The (name, file, mime) triple an OpenAI-compatible edit expects."""
        return (self.filename, io.BytesIO(self.data), _mime_for(self.filename))


@dataclass(frozen=True)
class ProviderSettings:
    """The flat set of values the provider call needs."""

    base_url: str
    api_key: str
    model: str
    timeout_seconds: int = 120

    @classmethod
    def from_config(cls, config):
        """Build settings from an ``AIConfig`` row."""
        return cls(
            base_url=(config.base_url or "").strip(),
            api_key=(config.api_key or "").strip(),
            model=(config.model or "").strip(),
            timeout_seconds=config.timeout_seconds or 120,
        )

    @property
    def is_complete(self):
        return bool(self.base_url and self.api_key and self.model)


class ImageProvider:
    """Calls an OpenAI-compatible ``images.generate`` endpoint."""

    def __init__(self, settings: ProviderSettings):
        self.settings = settings

    def generate(self, prompt: str, size: str, source_image: SourceImage | None = None) -> bytes:
        """Generate one image and return its bytes.

        With ``source_image`` this is image-to-image (an edit of the supplied
        picture); without it, plain text-to-image.  Both paths share the same
        download and validation, so a new provider only has to implement the
        request half.

        Raises ``GenerationError`` with a user-readable message on any
        failure — a bad key, a rejected prompt, a timeout, a corrupt file.
        """
        if not self.settings.is_complete:
            raise GenerationError(
                "The AI provider is not configured yet. Add the API key in the admin panel."
            )

        if source_image is not None:
            url = self._request_edit_url(prompt, size, source_image)
        else:
            url = self._request_image_url(prompt, size)
        return self._download(url)

    # -- internals ---------------------------------------------------------

    def _client(self):
        if OpenAI is None:  # pragma: no cover - depends on the environment
            raise GenerationError(
                "The `openai` package is not installed, so image generation is unavailable."
            )
        return OpenAI(
            base_url=self.settings.base_url,
            api_key=self.settings.api_key,
            timeout=self.settings.timeout_seconds,
            max_retries=1,
        )

    def _request_image_url(self, prompt: str, size: str) -> str:
        try:
            response = self._client().images.generate(
                model=self.settings.model,
                prompt=prompt,
                size=size or None,
            )
        except GenerationError:
            raise
        except Exception as exc:  # SDK raises a wide family of errors
            raise GenerationError(_readable_provider_error(exc)) from exc

        return _response_url(response)

    def _request_edit_url(self, prompt: str, size: str, source_image: SourceImage) -> str:
        """Image-to-image: hand the reference picture to the provider."""
        try:
            response = self._client().images.edit(
                model=self.settings.model,
                image=source_image.as_upload(),
                prompt=prompt,
                size=size or None,
            )
        except GenerationError:
            raise
        except Exception as exc:  # the SDK raises a wide family of errors
            raise GenerationError(_readable_provider_error(exc)) from exc

        return _response_url(response)

    def _download(self, url: str) -> bytes:
        if url.startswith("data:"):
            return _decode_data_url(url)

        if not url.lower().startswith(("http://", "https://")):
            raise GenerationError("The provider returned an unusable image URL.")

        request = urllib.request.Request(url, headers={"User-Agent": "Promptly/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
                declared = response.headers.get("Content-Length")
                if declared and int(declared) > MAX_DOWNLOAD_BYTES:
                    raise GenerationError("The generated image is too large to store.")
                payload = response.read(MAX_DOWNLOAD_BYTES + 1)
        except urllib.error.URLError as exc:
            raise GenerationError(f"Could not download the generated image: {exc.reason}") from exc
        except OSError as exc:
            raise GenerationError(f"Could not download the generated image: {exc}") from exc

        if len(payload) > MAX_DOWNLOAD_BYTES:
            raise GenerationError("The generated image is too large to store.")
        if not payload:
            raise GenerationError("The provider returned an empty image.")
        return payload


def _response_url(response) -> str:
    data = getattr(response, "data", None) or []
    if not data:
        raise GenerationError("The provider returned no image.")
    url = getattr(data[0], "url", None)
    if not url:
        raise GenerationError("The provider returned no image URL.")
    return url


def _mime_for(filename: str) -> str:
    extension = (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()
    return {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
        "gif": "image/gif",
    }.get(extension, "application/octet-stream")


def _decode_data_url(url: str) -> bytes:
    """Accept a base64 ``data:`` URL, which some providers return instead."""
    import base64
    import binascii

    if len(url) > DATA_URL_MAX_CHARS:
        raise GenerationError("The generated image is too large to store.")
    try:
        _, encoded = url.split(",", 1)
        return base64.b64decode(encoded, validate=False)
    except (ValueError, binascii.Error) as exc:
        raise GenerationError("The provider returned an unreadable image.") from exc


def _readable_provider_error(exc: Exception) -> str:
    """Turn an SDK exception into something a user can act on."""
    status = getattr(exc, "status_code", None)
    if status in (401, 403):
        return "The AI provider rejected the API key. An admin needs to check the settings."
    if status == 429:
        return "The AI provider is rate limiting us right now. Try again in a moment."
    if status == 402:
        return "The AI provider account is out of credit."
    if status and status >= 500:
        return "The AI provider is having trouble right now. Try again in a moment."

    message = getattr(exc, "message", None) or str(exc) or exc.__class__.__name__
    message = " ".join(str(message).split())
    return f"The AI provider could not generate this image: {message[:300]}"
