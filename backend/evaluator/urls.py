from django.urls import path

from . import views

urlpatterns = [
    path("evaluate", views.evaluate_view, name="evaluate"),
    path("rate-limit", views.rate_limit_view, name="rate-limit"),
]
