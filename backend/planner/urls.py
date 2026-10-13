from django.urls import path

from planner import views

app_name = "planner"

urlpatterns = [
    path("health/", views.HealthView.as_view(), name="health"),
    path("geocode/", views.GeocodeView.as_view(), name="geocode"),
    path("plan-trip/", views.PlanTripView.as_view(), name="plan-trip"),
    path("heatmap/", views.HeatmapView.as_view(), name="heatmap"),
]
