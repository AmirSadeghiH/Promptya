from django.urls import path

from credits import views

app_name = "credits"

urlpatterns = [
    path("credits/challenges/<slug:slug>/claim/", views.claim_challenge, name="claim-challenge"),
]
