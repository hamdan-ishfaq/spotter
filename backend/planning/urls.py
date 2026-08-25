from django.urls import path

from .views import AutocompleteView, HealthView, PlanView

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("autocomplete/", AutocompleteView.as_view(), name="autocomplete"),
    path("plan/", PlanView.as_view(), name="plan"),
]
