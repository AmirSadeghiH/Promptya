from pathlib import Path
import os

from django.core.management.utils import get_random_secret_key

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


def _env_bool(name, default=False):
    return os.environ.get(name, str(default)).lower() in {"1", "true", "yes", "on"}


def _env_required(name: str) -> str:
    """Get required environment variable or raise ImproperlyConfigured."""
    from django.core.exceptions import ImproperlyConfigured
    value = os.environ.get(name)
    if not value:
        raise ImproperlyConfigured(f"Missing required environment variable: {name}")
    return value


def _is_testing() -> bool:
    """Check if running under test runner."""
    import sys
    return "test" in sys.argv and "runserver" not in sys.argv


# SECURITY WARNING: keep the secret key used in production secret!
# In production (DEBUG=False), DJANGO_SECRET_KEY must be set in the environment.
# In development, a random key is generated if not provided.
if _env_bool("DJANGO_DEBUG", default=True):
    SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY") or get_random_secret_key()
else:
    SECRET_KEY = _env_required("DJANGO_SECRET_KEY")

# SECURITY WARNING: don't run with debug turned on in production!
# Default to False for fail-closed behavior.
DEBUG = _env_bool("DJANGO_DEBUG", default=True)

# ALLOWED_HOSTS: empty by default in production (fail closed).
# In development/test, allow testserver and localhost for convenience.
_allowed_hosts = [h for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",") if h]
if DEBUG or _is_testing():
    _allowed_hosts += ["testserver", "localhost", "127.0.0.1"]
ALLOWED_HOSTS = _allowed_hosts

# --- Canonical site identity -------------------------------------------------
# Every absolute URL the site emits for search engines (canonical links,
# hreflang, Open Graph, JSON-LD, robots.txt, the XML sitemap) is built from this
# one value, never from the incoming Host header.  That makes canonical tags
# impossible to poison through a spoofed Host, keeps http/www/host variants from
# fragmenting the index, and guarantees the sitemap advertises one origin.
#
# Leave it empty in development: the helpers then fall back to the request so
# `runserver` on 127.0.0.1 keeps working.  `web.checks.site_url_check` raises a
# deployment error when DEBUG is off and this is still unset.  The test suite
# supplies its own origin per-test class; see `web/test_seo.py`.
SITE_URL = os.environ.get("PROMPTYA_SITE_URL", "").strip().rstrip("/")


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sitemaps',
    'core',
    'account',
    'posts',
    'credits',
    'imagegen',
    'interactions',
    'notifications',
    'web',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'core.middleware.MediaRangeMiddleware',
    'core.middleware.ApiCompatMiddleware',
    # 301s http/www/alternate-host requests onto SITE_URL before anything else
    # can echo the Host header into a canonical, og:url or sitemap entry.
    'web.middleware.CanonicalHostMiddleware',
    # Must run before CommonMiddleware so the active language is known by the
    # time URL resolution picks between the /en/ and /fa/ resolvers.
    'web.middleware.LanguageMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'web.context_processors.ui_prefs',
                'web.context_processors.seo_prefs',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'


# Database
# https://docs.djangoproject.com/en/6.1/ref/settings/#databases

# Use PostgreSQL in production, SQLite in development.
# Set DATABASE_URL or individual PG* vars for production.
_database_url = os.environ.get("DATABASE_URL")
if _database_url:
    import dj_database_url
    DATABASES = {
        "default": dj_database_url.parse(
            _database_url,
            conn_max_age=60,
            conn_health_checks=True,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


# Password validation
# https://docs.djangoproject.com/en/6.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
# https://docs.djangoproject.com/en/6.1/topics/i18n/

LANGUAGE_CODE = 'en'

# Order matters: the first entry is the default language, and therefore the
# language the sitemap points x-default at and the one unprefixed URLs resolve
# to.  Both are server-rendered; neither depends on JavaScript.
LANGUAGES = [
    ('en', 'English'),
    ('fa', 'Persian / فارسی'),
]

# UI language only.  Server-rendered text comes from web.i18n_strings, so Django's
# own catalogs are intentionally empty and no .po files ship with the project.
LOCALE_PATHS = []

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.1/howto/static-files/

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Public pages are mounted with an explicit trailing slash.  APPEND_SLASH turns a
# slash-less request into a single 301 to the slashed form, which is what keeps
# /post/1 and /post/1/ from being two crawlable addresses.
APPEND_SLASH = True

# User-uploaded media (images / videos attached to posts, profile pictures)
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': (
            'whitenoise.storage.CompressedManifestStaticFilesStorage'
            if not _env_bool('DJANGO_DEBUG', default=True)
            else 'django.contrib.staticfiles.storage.StaticFilesStorage'
        ),
    },
}

# Email
# https://docs.djangoproject.com/en/6.1/topics/email/#topic-email-configuration
AUTH_USER_MODEL = 'account.CustomUser'

# Email backend: console in development, SMTP in production (required).
if DEBUG:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
else:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = _env_required("EMAIL_HOST")
    EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
    EMAIL_HOST_USER = _env_required("EMAIL_HOST_USER")
    EMAIL_HOST_PASSWORD = _env_required("EMAIL_HOST_PASSWORD")
    EMAIL_USE_TLS = _env_bool("EMAIL_USE_TLS", default=True)
    DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "Promptya <noreply@promptya.app>")

# Email verification code (OTP): a short numeric code is emailed at signup and
# entered on the standalone /verify-email/ page. It is valid for exactly
# TTL seconds, after which a new one may be requested.
EMAIL_VERIFICATION_CODE_LENGTH = 6
EMAIL_VERIFICATION_CODE_TTL_SECONDS = 120
EMAIL_VERIFICATION_CODE_MAX_ATTEMPTS = 5

# Cache configuration: Redis in production, local memory in development.
# Set REDIS_URL for production (e.g., redis://:password@host:6379/0).
_redis_url = os.environ.get("REDIS_URL")
if _redis_url:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": _redis_url,
            "KEY_PREFIX": "promptya",
            "OPTIONS": {
                "health_check_interval": 30,
            },
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }

# Session engine: cache-backed in production for scalability, DB in development.
if not DEBUG and _redis_url:
    SESSION_ENGINE = "django.contrib.sessions.backends.cache"
    SESSION_CACHE_ALIAS = "default"
else:
    SESSION_ENGINE = "django.contrib.sessions.backends.db"

# Logging configuration: structured JSON in production, console in development.
# Never logs secrets, passwords, or sensitive user data.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s",
        },
    },
    "filters": {
        "require_debug_false": {
            "()": "django.utils.log.RequireDebugFalse",
        },
        "require_debug_true": {
            "()": "django.utils.log.RequireDebugTrue",
        },
        "redact_secrets": {
            "()": "core.logging.RedactSecretsFilter",
        },
    },
    "handlers": {
        "console": {
            "level": "INFO",
            "filters": ["require_debug_true", "redact_secrets"],
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "console_json": {
            "level": "INFO",
            "filters": ["require_debug_false", "redact_secrets"],
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
    },
    "root": {
        "level": "INFO",
        "handlers": ["console", "console_json"],
    },
    "loggers": {
        "django": {
            "level": "INFO",
            "handlers": ["console", "console_json"],
            "propagate": False,
        },
        "django.request": {
            "level": "WARNING",
            "handlers": ["console", "console_json"],
            "propagate": False,
        },
        "django.security": {
            "level": "WARNING",
            "handlers": ["console", "console_json"],
            "propagate": False,
        },
        "imagegen": {
            "level": "INFO",
            "handlers": ["console", "console_json"],
            "propagate": False,
        },
        "credits": {
            "level": "INFO",
            "handlers": ["console", "console_json"],
            "propagate": False,
        },
    },
}

# Media storage: local filesystem in development, S3-compatible in production.
# Set AWS_S3_ENDPOINT_URL, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY,
# AWS_STORAGE_BUCKET_NAME, and AWS_S3_REGION_NAME for production.
if not DEBUG and os.environ.get("AWS_STORAGE_BUCKET_NAME"):
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
            "OPTIONS": {
                "bucket_name": os.environ["AWS_STORAGE_BUCKET_NAME"],
                "region_name": os.environ.get("AWS_S3_REGION_NAME", "us-east-1"),
                "endpoint_url": os.environ.get("AWS_S3_ENDPOINT_URL"),
                "access_key": os.environ.get("AWS_ACCESS_KEY_ID"),
                "secret_key": os.environ.get("AWS_SECRET_ACCESS_KEY"),
                "default_acl": "private",
                "querystring_auth": True,
                "querystring_expire": 3600,
                "file_overwrite": False,
            },
        },
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
    }
else:
    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": (
                "whitenoise.storage.CompressedManifestStaticFilesStorage"
                if not DEBUG
                else "django.contrib.staticfiles.storage.StaticFilesStorage"
            ),
        },
    }

CSRF_TRUSTED_ORIGINS = [
    o for o in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o
]

# How many reverse proxies sit in front of Django (nginx = 1). Used to find the
# real client IP in X-Forwarded-For. Leave at 0 when Django is not behind a
# proxy, otherwise the header is attacker-controlled. See core.ratelimit.
TRUSTED_PROXY_COUNT = int(os.environ.get("DJANGO_TRUSTED_PROXY_COUNT", "0") or 0)

if not DEBUG:
    SECURE_SSL_REDIRECT = _env_bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    X_FRAME_OPTIONS = "DENY"
    SECURE_CONTENT_TYPE_NOSNIFF = True
    # Keeps internal URLs carrying tracking-ish parameters (?source=, ?ref=)
    # out of third-party Referer headers.
    SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
