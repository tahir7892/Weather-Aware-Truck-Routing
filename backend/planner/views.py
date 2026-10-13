"""
API endpoints. Views stay thin: validate input, call a service, return JSON.
Errors are formatted by planner.exceptions.api_exception_handler.
"""

from rest_framework.response import Response
from rest_framework.views import APIView

from planner.clients import geocoding_client
from planner.serializers import GeocodeQuerySerializer, HeatmapQuerySerializer, PlanTripSerializer
from planner.services.heatmap import build_heatmap
from planner.services.trip_planner import plan_trip


class HealthView(APIView):
    """GET /api/health/ - used by the hosting platform to check the app is up."""

    throttle_classes = []

    def get(self, request):
        return Response({"status": "ok"})


class GeocodeView(APIView):
    """GET /api/geocode/?q=Chic - place suggestions while the user types."""

    throttle_scope = "geocode"

    def get(self, request):
        query = GeocodeQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        places = geocoding_client.autocomplete(query.validated_data["q"])
        return Response({"results": [place.to_dict() for place in places]})


class PlanTripView(APIView):
    """POST /api/plan-trip/ - 3 routes with checkpoints, risk and a recommendation."""

    throttle_scope = "plan_trip"

    def post(self, request):
        trip = PlanTripSerializer(data=request.data)
        trip.is_valid(raise_exception=True)
        data = trip.validated_data
        result = plan_trip(
            origin=data["origin"],
            destination=data["destination"],
            departure=data["departure_time"],
            load_lb=data["load_weight_lb"],
            interval_miles=data["checkpoint_interval_miles"],
        )
        return Response(result)


class HeatmapView(APIView):
    """GET /api/heatmap/?trip_id=... - 0-48 h weather grid along a planned trip."""

    throttle_scope = "heatmap"

    def get(self, request):
        query = HeatmapQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        return Response(build_heatmap(query.validated_data["trip_id"]))
