from django.urls import path

from moderation import views

app_name = "moderation"

urlpatterns = [
    path("reports/", views.create_report, name="create-report"),
    path("blocks/", views.list_blocks, name="list-blocks"),
    path("blocks/<str:username>/", views.block_toggle, name="block-user"),
]
