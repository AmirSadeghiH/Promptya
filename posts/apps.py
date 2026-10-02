from django.apps import AppConfig


class PostsConfig(AppConfig):
    name = 'posts'

    def ready(self):
        # Attaches the pre_save/post_save receivers that capture an image's
        # intrinsic size and build its WebP derivative. Imported for the side
        # effect, so it must never be a plain `import` at module level.
        from posts import signals  # noqa: F401
