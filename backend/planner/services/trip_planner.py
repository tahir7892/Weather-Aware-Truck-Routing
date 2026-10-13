"""
The full "plan my trip" pipeline:

  places -> 3 routes -> checkpoints + ETAs -> weather at each ETA
         -> risk per checkpoint -> route summaries -> recommendation

The route lines are saved in the cache under a trip id so the heatmap endpoint
can find them later without the frontend sending them back.
"""

import uuid
from dataclasses import dataclass

from django.core.cache import cache

from planner.clients import geocoding_client, routing_client, weather_client
from planner.clients.geocoding_client import Place
from planner.constants import CACHE_TTL_TRIP, ROUTE_LABELS, ROUTE_SIMPLIFY_TOLERANCE_METERS
from planner.exceptions import InvalidTrip
from planner.services.checkpoints import build_checkpoints, nearest_hour
from planner.services.recommendation import recommend, summarize_route
from planner.services.risk import WeatherSample, assess
from planner.utils.geo import haversine_miles, simplify

# Origin and destination closer than this are treated as the same place.
MIN_TRIP_MILES = 0.5


@dataclass(frozen=True)
class TripSnapshot:
    """What the heatmap needs to know about a planned trip."""

    lines: tuple  # simplified route lines, (lat, lon) points
    departure: object  # datetime, UTC
    load_lb: float


def trip_cache_key(trip_id):
    return f"trip:{trip_id}"


def resolve_place(place):
    """`place` is {"text": ...} or {"lat": ..., "lon": ..., "name": optional}."""
    if "lat" in place:
        name = place.get("name") or f"{place['lat']:.4f}, {place['lon']:.4f}"
        return Place(name=name, lat=place["lat"], lon=place["lon"])
    return geocoding_client.search(place["text"])


def plan_trip(origin, destination, departure, load_lb, interval_miles):
    origin = resolve_place(origin)
    destination = resolve_place(destination)
    if haversine_miles(origin.point, destination.point) < MIN_TRIP_MILES:
        raise InvalidTrip("Origin and destination are the same place.")

    routing = routing_client.get_routes(origin.point, destination.point, load_lb)

    # Checkpoints and ETAs for every route.
    planned = []
    for route_id, route in zip(ROUTE_LABELS, routing.routes):
        checkpoints = build_checkpoints(list(route.points), route.step_timings, departure, interval_miles)
        planned.append((route_id, route, checkpoints))

    # Weather for all checkpoints of all routes, fetched together.
    all_checkpoints = [cp for _, _, checkpoints in planned for cp in checkpoints]
    _attach_weather(all_checkpoints, load_lb)

    summaries = {route_id: summarize_route(checkpoints, route.duration_seconds) for route_id, route, checkpoints in planned}
    recommendation = recommend(summaries)

    lines = {route_id: simplify(list(route.points), ROUTE_SIMPLIFY_TOLERANCE_METERS) for route_id, route, _ in planned}
    trip_id = uuid.uuid4().hex
    cache.set(
        trip_cache_key(trip_id),
        TripSnapshot(lines=tuple(tuple(line) for line in lines.values()), departure=all_checkpoints[0].eta, load_lb=load_lb),
        CACHE_TTL_TRIP,
    )

    routes = [
        _route_dict(route_id, route, checkpoints, summaries[route_id], lines[route_id], recommendation)
        for route_id, route, checkpoints in planned
    ]
    return {
        "trip_id": trip_id,
        "origin": origin.to_dict(),
        "destination": destination.to_dict(),
        "departure_time": _iso(all_checkpoints[0].eta),
        "load_weight_lb": load_lb,
        "checkpoint_interval_miles": interval_miles,
        "routes": routes,
        "recommendation": {"route_id": recommendation.route_id, "reason": recommendation.reason},
        "warnings": routing.warnings + recommendation.warnings,
    }


def _attach_weather(checkpoints, load_lb):
    """Weather at each checkpoint for the hour nearest its ETA, then its risk."""
    hours = [nearest_hour(cp.eta) for cp in checkpoints]
    forecasts = weather_client.get_forecasts([cp.point for cp in checkpoints], min(hours), max(hours))
    for checkpoint, hour in zip(checkpoints, hours):
        forecast = forecasts.get(weather_client.round_point(checkpoint.point), weather_client.EMPTY_FORECAST)
        checkpoint.forecast_time = hour
        checkpoint.weather = WeatherSample.from_forecast(forecast.at(hour))
        checkpoint.risk = assess(checkpoint.weather, load_lb)


# --- Response shape ------------------------------------------------------------


def _iso(moment):
    return moment.replace(microsecond=0).isoformat()


def _checkpoint_dict(checkpoint):
    return {
        "index": checkpoint.index,
        "lat": round(checkpoint.lat, 5),
        "lon": round(checkpoint.lon, 5),
        "mile": round(checkpoint.mile, 1),
        "eta": _iso(checkpoint.eta),
        "forecast_time": _iso(checkpoint.forecast_time),
        "weather": checkpoint.weather.to_dict(),
        "risk": checkpoint.risk.to_dict(),
    }


def _route_dict(route_id, route, checkpoints, summary, line, recommendation):
    return {
        "id": route_id,
        "via": route.via,
        "rank": recommendation.ranking.index(route_id) + 1,
        "is_recommended": route_id == recommendation.route_id,
        "geometry": [[round(lat, 5), round(lon, 5)] for lat, lon in line],
        "summary": {
            "distance_miles": round(summary.distance_miles, 1),
            "duration_minutes": round(summary.duration_seconds / 60, 1),
            "arrival_time": _iso(checkpoints[-1].eta),
            "miles_by_level": {level: round(miles, 1) for level, miles in summary.miles_by_level.items()},
            "average_risk": round(summary.average_risk, 2) if summary.average_risk is not None else None,
            "max_level": summary.max_level.label if summary.max_level is not None else None,
            "checkpoint_count": len(checkpoints),
        },
        "checkpoints": [_checkpoint_dict(cp) for cp in checkpoints],
    }
