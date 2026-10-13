"""Input validation for the API endpoints."""

import math
from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from planner.constants import (
    CHECKPOINT_INTERVALS_MILES,
    DEFAULT_CHECKPOINT_INTERVAL_MILES,
    DEPARTURE_PAST_TOLERANCE_MINUTES,
    GEOCODE_MIN_QUERY_LENGTH,
    MAX_DEPARTURE_DAYS_AHEAD,
    MAX_LOAD_WEIGHT_LB,
    MIN_LOAD_WEIGHT_LB,
)


class PlaceField(serializers.Field):
    """
    A place given either as text ("Chicago, IL") or as coordinates from the
    autocomplete: {"lat": 41.88, "lon": -87.63, "name": "Chicago, IL"}.
    """

    default_error_messages = {
        "invalid": 'Enter a place name, or an object with "lat" and "lon".',
        "too_short": "Place name is too short.",
        "bad_coordinates": "Latitude must be between -90 and 90 and longitude between -180 and 180.",
    }

    def to_internal_value(self, data):
        if isinstance(data, str):
            text = " ".join(data.split())
            if len(text) < 2:
                self.fail("too_short")
            return {"text": text}

        if isinstance(data, dict):
            try:
                lat, lon = float(data["lat"]), float(data["lon"])
            except (KeyError, TypeError, ValueError):
                self.fail("invalid")
            if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
                self.fail("bad_coordinates")
            name = data.get("name")
            return {"lat": lat, "lon": lon, "name": str(name).strip() if name else None}

        self.fail("invalid")

    def to_representation(self, value):
        return value


class PlanTripSerializer(serializers.Serializer):
    origin = PlaceField()
    destination = PlaceField()
    departure_time = serializers.DateTimeField(
        help_text="ISO 8601 with a time zone, e.g. 2026-10-12T14:00:00Z. Times without a zone are read as UTC."
    )
    load_weight_lb = serializers.FloatField(min_value=MIN_LOAD_WEIGHT_LB, max_value=MAX_LOAD_WEIGHT_LB)
    checkpoint_interval_miles = serializers.ChoiceField(
        choices=CHECKPOINT_INTERVALS_MILES, default=DEFAULT_CHECKPOINT_INTERVAL_MILES
    )

    def validate_departure_time(self, value):
        now = timezone.now()
        if value < now - timedelta(minutes=DEPARTURE_PAST_TOLERANCE_MINUTES):
            raise serializers.ValidationError("Departure time is in the past.")
        if value > now + timedelta(days=MAX_DEPARTURE_DAYS_AHEAD):
            raise serializers.ValidationError(
                f"Departure must be within {MAX_DEPARTURE_DAYS_AHEAD} days (weather forecasts do not reach further)."
            )
        return value

    def validate_load_weight_lb(self, value):
        if not math.isfinite(value):
            raise serializers.ValidationError("A valid number is required.")
        return value

    def validate(self, attrs):
        origin, destination = attrs["origin"], attrs["destination"]
        if "text" in origin and "text" in destination and origin["text"].lower() == destination["text"].lower():
            raise serializers.ValidationError({"destination": "Destination must be different from the origin."})
        return attrs


class GeocodeQuerySerializer(serializers.Serializer):
    q = serializers.CharField(min_length=GEOCODE_MIN_QUERY_LENGTH, max_length=200, trim_whitespace=True)


class HeatmapQuerySerializer(serializers.Serializer):
    trip_id = serializers.RegexField(r"^[0-9a-f]{32}$", error_messages={"invalid": "Invalid trip id."})
