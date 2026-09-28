"""Secure media upload validation for Promptya.

Every uploaded file passes through three layers:
  1. Extension whitelist (fast reject)
  2. Size cap (DoS protection)
  3. Content inspection — declared Content-Type + magic bytes (real format)
     and, for images, a full Pillow re-decode that rejects any file the
     image library cannot parse (decompression bombs, polyglots, etc.)
"""

from django.core.exceptions import ValidationError

try:
    from PIL import Image
except ImportError:  # pragma: no cover - Pillow is a hard dependency
    Image = None

# ---- Whitelists -----------------------------------------------------------

IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif"}
VIDEO_EXTENSIONS = {"mp4", "webm", "mov"}
AUDIO_EXTENSIONS = {"mp3", "wav", "ogg", "m4a"}

# Human-friendly names used in error messages.
KIND_LABELS = {
    "image": "image (JPG, PNG, WebP, GIF)",
    "video": "video (MP4, WebM, MOV)",
    "audio": "audio (MP3, WAV, OGG, M4A)",
}

# Size caps per kind (bytes).
MAX_SIZES = {
    "image": 10 * 1024 * 1024,   # 10 MB
    "video": 200 * 1024 * 1024,  # 200 MB
    "audio": 30 * 1024 * 1024,   # 30 MB
}

# Extension -> set of acceptable MIME types (declared or sniffed).
MIME_BY_EXTENSION = {
    "jpg": {"image/jpeg"}, "jpeg": {"image/jpeg"},
    "png": {"image/png"}, "webp": {"image/webp"},
    "gif": {"image/gif"},
    "mp4": {"video/mp4"}, "webm": {"video/webm"},
    "mov": {"video/quicktime", "video/mp4"},
    "mp3": {"audio/mpeg", "audio/mp3"},
    "wav": {"audio/wav", "audio/x-wav", "audio/wave", "audio/vnd.wave"},
    "ogg": {"audio/ogg", "application/ogg"},
    "m4a": {"audio/mp4", "audio/x-m4a", "audio/m4a", "audio/aac"},
}

# Magic byte signatures: bytes prefix -> set of extensions that may have it.
_MAGIC = (
    (b"\xff\xd8\xff", {"jpg", "jpeg"}),
    (b"\x89PNG\r\n\x1a\n", {"png"}),
    (b"RIFF", {"webp", "wav"}),  # sub-checked below
    (b"GIF87a", {"gif"}), (b"GIF89a", {"gif"}),
    (b"ftyp", None),  # ISO-BMFF container: mp4 / m4a / mov (checked at offset 4)
    (b"\x1aE\xdf\xa3", {"webm", "ogg"}),  # EBML (webm) — ogg uses OggS
    (b"OggS", {"ogg"}),
    (b"ID3", {"mp3"}),  # MP3 with ID3 header
)


def _sniff_extensions(head):
    """Return the set of extensions consistent with the file's magic bytes."""
    candidates = set()
    if head[:4] == b"RIFF":
        sub = head[8:12]
        if sub == b"WEBP":
            candidates.add("webp")
        elif sub == b"WAVE":
            candidates.add("wav")
    elif len(head) >= 12 and head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand in (b"M4A ", b"M4B ", b"mp42", b"mp41", b"isom", b"iso2"):
            # m4a and mp4 share the ISO container; both are plausible.
            candidates.update({"mp4", "m4a", "mov"})
        elif brand == b"qt  ":
            candidates.add("mov")
        else:
            candidates.update({"mp4", "mov"})
    else:
        for prefix, exts in _MAGIC:
            if prefix and head.startswith(prefix) and exts:
                candidates.update(exts)
    if not candidates:
        # Raw MPEG audio frames (no ID3) — very weak signature, allow mp3 only
        # if the first frame sync bits look right.
        if len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0:
            candidates.add("mp3")
    return candidates


def _profile_picture_limit():
    """Allow raising the avatar cap without touching the post limits."""
    return MAX_SIZES["image"]


def validate_upload_file(django_file, kind):
    """Validate an uploaded file for the given kind ('image'|'video'|'audio').

    Raises ValidationError with a user-safe message on any violation.
    """
    allowed_extensions = {
        "image": IMAGE_EXTENSIONS,
        "video": VIDEO_EXTENSIONS,
        "audio": AUDIO_EXTENSIONS,
    }[kind]
    max_size = (
        _profile_picture_limit() if kind == "image" else MAX_SIZES[kind]
    )
    name = (django_file.name or "").rsplit("/", 1)[-1]

    # 1) Extension whitelist
    extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if extension not in allowed_extensions:
        raise ValidationError(
            f"Unsupported file type “.{extension or '???'}”. "
            f"Allowed: {KIND_LABELS[kind]}."
        )

    # 2) Size cap
    if django_file.size and django_file.size > max_size:
        raise ValidationError(
            f"File is too large ({django_file.size / (1024 * 1024):.1f} MB). "
            f"Maximum for {kind} is {max_size / (1024 * 1024):.0f} MB."
        )

    # 3) Content inspection — read the head once, keep it for Pillow
    head = django_file.read(64 * 1024) or b""
    django_file.seek(0)
    if len(head) < 12:
        raise ValidationError("File appears to be empty or corrupted.")

    sniffed = _sniff_extensions(head)
    if extension not in sniffed:
        raise ValidationError(
            "File content doesn't match its extension. "
            f"Expected a real {KIND_LABELS[kind]} file."
        )

    # Declared content type must also be plausible (cheap extra layer).
    declared = (getattr(django_file, "content_type", "") or "").split(";")[0].strip().lower()
    if declared and declared not in ("application/octet-stream", "binary/octet-stream"):
        if declared not in MIME_BY_EXTENSION.get(extension, set()):
            raise ValidationError(
                f"File claims to be “{declared}” but has a .{extension} extension."
            )

    # 4) Images: full re-decode with Pillow (rejects polyglots, bombs, SVG-in-disguise…)
    if kind == "image" and Image is not None:
        django_file.seek(0)
        try:
            with Image.open(django_file) as img:
                img.verify()
            django_file.seek(0)
            with Image.open(django_file) as img:
                img.load()
                # Guard against decompression bombs on tiny files.
                if img.width * img.height > 40_000_000:  # ~40 MP
                    raise ValidationError("Image dimensions are too large.")
        except ValidationError:
            raise
        except Exception:
            raise ValidationError("File is not a valid, readable image.")
        finally:
            django_file.seek(0)


def validate_post_media(image=None, video=None, audio=None):
    """Validate all media attached to a post in one call."""
    if image:
        validate_upload_file(image, "image")
    if video:
        validate_upload_file(video, "video")
    if audio:
        validate_upload_file(audio, "audio")
