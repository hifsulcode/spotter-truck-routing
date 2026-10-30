from django.urls import path

from .views import GeocodeView, HealthView, HeatmapView, PlanView

urlpatterns = [
    path("health/", HealthView.as_view()),
    path("geocode/", GeocodeView.as_view()),
    path("plan/", PlanView.as_view()),
    path("heatmap/", HeatmapView.as_view()),
]
