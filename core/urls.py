"""
URL configuration for core project.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.conf.urls.i18n import i18n_patterns
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path
from web import auth_views, views
from web.sitemaps import SITEMAPS

urlpatterns = [
    path('admin/', admin.site.urls),

    # --- JSON API: never prefixed, never part of the page index -------------
    path('api/', include('account.urls')),
    path('api/posts/', include('posts.urls')),
    path('api/posts/', include('interactions.urls')),
    path('api/', include('imagegen.urls')),
    path('api/', include('credits.urls')),
    path('api/', include('notifications.urls')),

    # --- Auth: one address each, so the PWA and shared links stay stable ----
    path('login/', auth_views.login_page, name='login'),
    path('signup/', auth_views.signup_page, name='signup'),
    path('logout/', auth_views.logout_view, name='logout'),

    # --- Crawler plumbing: a single absolute address, never prefixed -------
    path('robots.txt', views.robots_txt, name='robots'),
    path('sitemap.xml', views.sitemap_xml, name='sitemap'),

    # --- Legacy unprefixed page aliases (no namespace) ----------------------
    # Listed before the i18n resolver so an unprefixed path resolves here, while
    # the `web` namespace itself still resolves against the resolver below.
    path('', include(('web.legacy_urls', None))),

    # --- Canonical, language-addressed pages: /en/… and /fa/… --------------
    # Scoped to the `web` app on purpose. Wrapping the whole root URLconf would
    # also prefix /api/, /admin/ and /login/, which would break the mobile
    # client, the admin and the service worker precache.
] + i18n_patterns(
    path('', include('web.urls')),
    prefix_default_language=True,
)

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
