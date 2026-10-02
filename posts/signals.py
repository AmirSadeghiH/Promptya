"""Capture intrinsic image metadata once, at write time.

Two things are recorded the moment an image is attached to a ``Post``, and both
exist purely so the read path stays cheap:

**Dimensions.**  ``<img width height>`` is the only way to reserve space for a
media box, so a card grid does not reflow as images arrive.  Reading them at
render time would mean opening every image on every request; reading them at
save time means one decode per upload, ever.

**A WebP derivative.**  Promptya accepts JPEG/PNG/WebP/GIF, so a PNG screenshot
is served to every browser as a PNG.  A WebP copy is roughly half the bytes for
the same picture.  The original is kept untouched so the download action, the
re-encode path and any future format change still work.

Two constraints shape the implementation:

* **Never close an upload.**  ``FieldFile.open()`` closes the file it replaces,
  and for a not-yet-saved upload that file *is* the ``UploadedFile`` Django is
  about to write to storage — closing it loses the upload outright
  (``ValueError: I/O operation on closed file``).  Dimensions are therefore read
  from the in-memory upload, leaving its handle open and rewound.
* **The derivative needs a path, and a path only exists after storage write.**
  So dimensions are captured in ``pre_save`` (they have to be part of the UPDATE)
  and the WebP is built in ``post_save``, persisted with a ``QuerySet.update()``
  so it cannot recurse back into this module.

Only ``Post`` is handled.  Avatars are rendered inside a fixed-size CSS square, so
there is no layout to reserve and no bytes worth a second stored file.

Everything is best-effort.  A Pillow failure must never lose a user's upload, so
every exception is swallowed and the post simply keeps the original with no
dimensions recorded.
"""

import logging
from io import BytesIO

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from posts.models import Post

logger = logging.getLogger(__name__)

try:
    from PIL import Image
except ImportError:  # pragma: no cover - Pillow is a hard dependency
    Image = None

#: Cap on a generated derivative. Anything larger than this is stored as-is:
#: re-encoding a huge source costs CPU proportional to its area and the payload
#: saving does not justify it.
WEBP_MAX_WIDTH = 2000
WEBP_QUALITY = 82


# ---------------------------------------------------------------------------
# Reading an image without disturbing the upload
# ---------------------------------------------------------------------------


def _read_bytes(image_field):
    """The image's bytes, leaving the field's own file handle open and rewound."""
    if getattr(image_field, "_committed", True):
        with image_field.open("rb") as handle:
            return handle.read()

    # Not yet in storage: a fresh upload. `FieldFile.open()` would close this
    # handle, and Django still has to write it during the very same save.
    uploaded = image_field.file
    if uploaded is None:
        return b""
    try:
        uploaded.seek(0)
        data = uploaded.read()
    except (AttributeError, OSError, ValueError):
        return b""
    finally:
        try:
            uploaded.seek(0)
        except (AttributeError, OSError, ValueError):
            pass
    return data


def _is_new_or_replaced(instance, field_name):
    """True when *field_name* holds a file the database has not already seen.

    Without this, every unrelated save of a post would re-decode its image and
    re-encode its WebP derivative.
    """
    field = getattr(instance, field_name)
    if not field:
        return False
    if not getattr(field, "_committed", True):
        return True
    if instance.pk is None:
        return True
    previous = (
        type(instance)
        ._default_manager.filter(pk=instance.pk)
        .values_list(field_name, flat=True)
        .first()
    )
    return previous != field.name


def _describe(image_field):
    """``(width, height)`` for an image field, or ``(None, None)``."""
    if Image is None or not image_field:
        return None, None
    try:
        with Image.open(BytesIO(_read_bytes(image_field))) as image:
            return image.width, image.height
    except Exception:
        # A file that is missing from storage, truncated, or a format Pillow
        # will not decode: the upload already passed full validation, so this is
        # an infrastructure problem, not a user error.  Record nothing.
        logger.debug("Could not read image dimensions", exc_info=True)
        return None, None


def _webp_name(image_field):
    return f"{image_field.name.rsplit('.', 1)[0]}.webp"


def _build_webp(image_field):
    """Write a WebP derivative next to *image_field*; return the stored name."""
    if Image is None or not image_field:
        return None
    try:
        source = image_field.path
        stem = source.rsplit(".", 1)[0]
        with Image.open(source) as image:
            # Animated GIFs and palette images with transparency survive the
            # round trip better when converted explicitly.
            if image.mode in ("P", "LA", "PA"):
                image = image.convert("RGBA")
            elif image.mode == "CMYK":
                image = image.convert("RGB")
            if image.width > WEBP_MAX_WIDTH:
                ratio = WEBP_MAX_WIDTH / image.width
                image = image.resize(
                    (WEBP_MAX_WIDTH, max(1, round(image.height * ratio))),
                    Image.LANCZOS,
                )
            image.save(f"{stem}.webp", "WEBP", quality=WEBP_QUALITY, method=4)
        return _webp_name(image_field)
    except Exception:
        logger.debug("Could not build a WebP derivative", exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Posts
# ---------------------------------------------------------------------------


@receiver(pre_save, sender=Post, dispatch_uid="posts.seo.post_image_dimensions")
def capture_post_image_dimensions(sender, instance, **kwargs):
    """Record the attached image's size before the row is written.

    ``pre_save`` because the dimensions have to be part of the same UPDATE that
    stores the file.  The WebP derivative is *not* built here: it needs a storage
    path, which does not exist until after the save.
    """
    if not instance.image:
        instance.image_width = None
        instance.image_height = None
        return
    if not _is_new_or_replaced(instance, "image"):
        return
    width, height = _describe(instance.image)
    if width:
        instance.image_width = width
        instance.image_height = height


@receiver(post_save, sender=Post, dispatch_uid="posts.seo.post_webp_derivative")
def build_post_webp_derivative(sender, instance, **kwargs):
    """Build (or clear) the WebP copy of the post's image.

    Persisted with a ``QuerySet.update()`` rather than ``instance.save()``: a save
    would re-enter ``capture_post_image_dimensions`` and this receiver with no way
    to tell the two apart.
    """
    if not instance.image or not instance.pk:
        if instance.image_webp:
            Post.objects.filter(pk=instance.pk).update(image_webp="")
        return

    expected = _webp_name(instance.image)
    if instance.image_webp and instance.image_webp.name == expected:
        return

    derived = _build_webp(instance.image) or ""
    Post.objects.filter(pk=instance.pk).update(image_webp=derived)
    if derived:
        instance.image_webp.name = derived
    else:
        instance.image_webp = None
