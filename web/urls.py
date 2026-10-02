"""Server-rendered page routes.

Every pattern here is mounted twice by ``core/urls.py``:

* once behind ``i18n_patterns(..., prefix_default_language=True)``, which is the
  canonical, crawlable address — ``/en/explore/`` and ``/fa/explore/``;
* once by ``web.legacy_urls`` at the unprefixed path, so every URL that worked
  before the bilingual SEO work still resolves with no redirect.

The API, ``/admin/``, the auth pages, static/media, ``robots.txt`` and
``sitemap.xml`` are deliberately *not* in this list: they are not page content,
they must keep exactly one address, and prefixing them would break the mobile
client, the service worker precache and the sitemap's own absolute URLs.
"""

from django.urls import path

from web import views

app_name = "web"

urlpatterns = [
    path("", views.home, name="home"),
    path("explore/", views.explore_page, name="explore"),
    path("search/", views.search_page, name="search"),
    path("tag/<str:slug>/", views.tag_page, name="tag"),
    path("create/", views.create_post_page, name="create"),
    path("studio/", views.studio_page, name="studio"),
    path("saved/", views.saved_page, name="saved"),
    path("notifications/", views.notifications_page, name="notifications"),
    path("profile/<str:username>/", views.profile_page, name="profile"),
    path("settings/profile/", views.profile_edit_page, name="profile-edit"),
    path("category/<str:slug>/", views.category_page, name="category"),
    path("post/<int:pk>/", views.post_detail_legacy_page, name="post-detail-legacy"),
    path("post/<str:slug>/", views.post_detail_page, name="post-detail"),
    path("feed/<str:feed>/", views.feed_page, name="feed"),
    path("offline/", views.offline_page, name="offline"),
]
