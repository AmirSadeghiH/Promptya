"""
URL configuration for core project.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from web import auth_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('account.urls')),
    path('api/posts/', include('posts.urls')),
    path('api/posts/', include('interactions.urls')),
    path('api/', include('imagegen.urls')),
    path('api/', include('credits.urls')),
    path('api/', include('notifications.urls')),
    path('login/', auth_views.login_page, name='login'),
    path('signup/', auth_views.signup_page, name='signup'),
    path('logout/', auth_views.logout_view, name='logout'),
    path('', include('web.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
