from django.urls import path
from . import views

urlpatterns = [
    path("session/", views.session),
    path("health/", views.health),
    path("papers/", views.papers),
    path("papers/<str:pmcid>/", views.paper),
    path("conversations/", views.conversations),
    path("conversations/<uuid:pk>/", views.conversation),
    path("conversations/<uuid:pk>/messages/", views.chat),
]
