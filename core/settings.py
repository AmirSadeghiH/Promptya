from pathlib import Path
import os

from django.core.management.utils import get_random_secret_key

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


def _env_bool(name, default=False):
    return os.environ.get(name, str(default)).lower() in {"1", "true", "yes", "on"}


# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY") or get_random_secret_key()

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = _env_bool("DJANGO_DEBUG", default=True)

ALLOWED_HOSTS = [h for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",") if h] or ["*"]

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

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
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

MAILERS = {
    'default': {
        'BACKEND': 'django.core.mail.backends.console.EmailBackend',
    },
}

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- Production hardening (activated when DJANGO_DEBUG is not "true") ---

CSRF_TRUSTED_ORIGINS = [
    o for o in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o
]

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
