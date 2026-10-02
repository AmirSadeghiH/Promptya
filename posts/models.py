from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models

# A collection page (tag hub, listing) needs at least this many items before it
# is worth a place in the index. Shared with web.seo so the sitemap, the robots
# directive and the page itself always agree on the threshold.
MIN_INDEXABLE_COLLECTION_ITEMS = 2


class Category(models.Model):
    name = models.CharField(
        max_length=100,
        unique=True,
    )

    slug = models.SlugField(
        max_length=120,
        unique=True,
    )

    description = models.TextField(
        blank=True,
        default="",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["slug"]),
        ]

    def __str__(self):
        return self.name

    @property
    def public_post_count(self):
        return self.posts.count()

    @property
    def is_indexable(self):
        """An empty category hub is a thin page with nothing to rank for."""
        return self.public_post_count > 0


class Tag(models.Model):
    name = models.CharField(
        max_length=50,
        unique=True,
    )

    slug = models.SlugField(
        max_length=60,
        unique=True,
    )

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["slug"]),
        ]

    def __str__(self):
        return self.name

    @property
    def post_count(self):
        return self.posts.count()

    @property
    def is_indexable(self):
        """Tag pages need more than a single post to be worth indexing.

        One post behind a tag is a duplicate of that post's own page with a
        thinner title, so it is still served (posts link to their tags) but kept
        ``noindex`` until the tag has some depth.
        """
        return self.post_count >= MIN_INDEXABLE_COLLECTION_ITEMS


class Post(models.Model):

    class PostType(models.TextChoices):
        PROMPT = "prompt", "Prompt"
        IMAGE = "image", "Image"
        VIDEO = "video", "Video"
        AUDIO = "audio", "Audio"

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="posts",
    )

    post_type = models.CharField(
        max_length=20,
        choices=PostType.choices,
    )

    title = models.CharField(
        max_length=200,
    )

    description = models.TextField(
        blank=True,
        default="",
    )

    prompt = models.TextField(
        blank=True,
        default="",
    )

    image = models.ImageField(
        upload_to="posts/images/",
        blank=True,
        null=True,
        help_text="Generated image attached to an image post.",
    )

    # Intrinsic size of `image`, read once at save time by posts.signals.
    # Rendering a post card then needs no filesystem access, which is what lets
    # every <img> carry width/height (no layout shift) without the LCP image
    # being lazy-loaded, and what keeps `width`/`height` honest for Open Graph.
    image_width = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Intrinsic width of `image` in pixels, captured on save.",
    )

    image_height = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Intrinsic height of `image` in pixels, captured on save.",
    )

    # A lossy WebP derivative of `image`, produced once at save time. Browsers
    # that support it download roughly half the bytes; the original stays in
    # place so the download action and any re-encode keep working.
    image_webp = models.ImageField(
        upload_to="posts/images/",
        blank=True,
        null=True,
        help_text="WebP derivative of `image`, generated automatically.",
    )

    video = models.FileField(
        upload_to="posts/videos/",
        blank=True,
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=["mp4", "webm", "mov"])],
        help_text="Generated video attached to a video post.",
    )

    audio = models.FileField(
        upload_to="posts/audio/",
        blank=True,
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=["mp3", "wav", "ogg", "m4a"])],
        help_text="Generated audio attached to an audio post.",
    )

    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="posts",
    )

    tags = models.ManyToManyField(
        Tag,
        blank=True,
        related_name="posts",
    )

    ai_model = models.CharField(
        max_length=100,
        blank=True,
        default="",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["post_type", "-created_at"],
            ),
            models.Index(
                fields=["category", "-created_at"],
            ),
            models.Index(
                fields=["author", "-created_at"],
            ),
            models.Index(
                fields=["-created_at"],
            ),
        ]

    def __str__(self):
        return self.title

    # -- SEO / indexability -------------------------------------------------
    # A post earns an index entry when it carries something a reader (and a
    # crawler) can actually use: a title plus either the prompt text or the
    # media it produced.  A row with nothing but a title is a thin page, and
    # thin pages at scale are a quality problem, not a traffic problem.

    #: Shortest prompt/body that makes a post worth indexing on its own.
    MIN_MEANINGFUL_LENGTH = 20

    @property
    def meaningful_text(self):
        """The author's own words: description if present, else the prompt."""
        for value in (self.description, self.prompt):
            collapsed = " ".join((value or "").split())
            if len(collapsed) >= self.MIN_MEANINGFUL_LENGTH:
                return collapsed
        return " ".join((self.description or self.prompt or "").split())

    @property
    def has_media(self):
        return bool(self.image or self.video or self.audio)

    @property
    def is_indexable(self):
        """Whether this post may be indexed, and appear in the sitemap."""
        if not self.title or not self.title.strip():
            return False
        if len(self.meaningful_text) >= self.MIN_MEANINGFUL_LENGTH:
            return True
        # A short caption plus real media is still a useful result page: the
        # media is the content and it is described by the title.
        return self.has_media

    @property
    def seo_image(self):
        """Best available image for this post, preferring the WebP derivative.

        Returns a ``FieldFile`` or ``None``.  Falls back to the original upload
        when the derivative was not produced (a GIF, or a Pillow failure).
        """
        if self.image_webp:
            return self.image_webp
        return self.image or None
