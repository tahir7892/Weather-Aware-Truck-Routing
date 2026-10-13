"""
Endpoint tests. External services are replaced with fakes, so these run
offline and check request validation, the response shape, the whole
plan-trip pipeline and error formatting.
"""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from planner import views
from planner.clients import geocoding_client, routing_client, weather_client
from planner.clients.geocoding_client import Place
from planner.clients.routing_client import Route, RoutingResult
from planner.clients.weather_client import HourlyForecast
from planner.constants import WEATHER_HOURLY_VARIABLES
from planner.exceptions import NoRouteFound, ServiceUnavailable
from planner.utils.geo import cumulative_distances


@pytest.fixture
def client():
    return APIClient()


def departure(hours=1):
    return (timezone.now() + timedelta(hours=hours)).isoformat()


def valid_body(**overrides):
    body = {
        "origin": "Chicago, IL",
        "destination": "Indianapolis, IN",
        "departure_time": departure(),
        "load_weight_lb": 45_000,
        "checkpoint_interval_miles": 25,
    }
    body.update(overrides)
    return body


# --- Fake world ---------------------------------------------------------------
# Three straight north-south routes at different longitudes. Route A (lon -90)
# is fastest but has heavy rain; B (lon -89) is dry; C (lon -88) is dry but slow.


def straight_route(lon, hours, via):
    points = tuple((40.0 + i * 0.1, lon) for i in range(21))  # ~138 miles
    return Route(
        points=points,
        distance_miles=cumulative_distances(points)[-1],
        duration_seconds=hours * 3600,
        step_timings=((0, len(points) - 1, hours * 3600),),
        via=via,
    )


ROUTES = [straight_route(-90.0, 2.0, "I-1"), straight_route(-89.0, 2.5, "US-2"), straight_route(-88.0, 3.0, "US-3")]


def fake_get_forecasts(points, start, end):
    hours = int((end - start) / timedelta(hours=1)) + 1
    result = {}
    for point in points:
        rain = 0.6 if point[1] < -89.5 else 0.0  # heavy rain only near route A
        values = {name: (0.0,) * hours for name in WEATHER_HOURLY_VARIABLES}
        values["rain"] = (rain,) * hours
        values["wind_speed_10m"] = (8.0,) * hours
        result[weather_client.round_point(point)] = HourlyForecast(start=weather_client.floor_hour(start), values=values)
    return result


@pytest.fixture
def fake_world(monkeypatch):
    monkeypatch.setattr(geocoding_client, "search", lambda text: Place(name=f"{text}, USA", lat=40.0, lon=-89.0) if "Chicago" in text else Place(name=f"{text}, USA", lat=42.0, lon=-89.0))
    monkeypatch.setattr(geocoding_client, "autocomplete", lambda text: [Place(name="Chicago, IL, USA", lat=41.88, lon=-87.66)])
    monkeypatch.setattr(routing_client, "get_routes", lambda origin, destination, load_lb: RoutingResult(routes=list(ROUTES)))
    monkeypatch.setattr(weather_client, "get_forecasts", fake_get_forecasts)


# --- Health -------------------------------------------------------------------


def test_health(client):
    response = client.get("/api/health/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# --- Plan trip: the full pipeline -----------------------------------------------


def test_plan_trip_recommends_the_dry_route(client, fake_world):
    response = client.post("/api/plan-trip/", valid_body(), format="json")
    assert response.status_code == 200
    data = response.json()

    assert len(data["trip_id"]) == 32
    assert data["origin"]["name"] == "Chicago, IL, USA"
    assert data["checkpoint_interval_miles"] == 25
    assert [r["id"] for r in data["routes"]] == ["A", "B", "C"]

    # A has Severe rain, so the dry route B wins over the faster A; B beats C on time.
    assert data["recommendation"]["route_id"] == "B"
    assert "vs Route A: fewer Severe miles" in data["recommendation"]["reason"]
    assert "vs Route C: shorter travel time" in data["recommendation"]["reason"]
    ranks = {r["id"]: r["rank"] for r in data["routes"]}
    assert ranks == {"B": 1, "C": 2, "A": 3}
    assert [r["is_recommended"] for r in data["routes"]] == [False, True, False]
    assert "The recommended route still has" not in " ".join(data["warnings"])


def test_plan_trip_route_and_checkpoint_shape(client, fake_world):
    data = client.post("/api/plan-trip/", valid_body(), format="json").json()
    route_a = data["routes"][0]

    assert route_a["via"] == "I-1"
    assert route_a["geometry"][0] == [40.0, -90.0]
    summary = route_a["summary"]
    assert summary["duration_minutes"] == 120.0
    assert summary["max_level"] == "Severe"
    assert summary["average_risk"] == 3.0
    assert summary["miles_by_level"]["Severe"] == summary["distance_miles"]
    assert set(summary["miles_by_level"]) == {"Low", "Moderate", "High", "Severe", "No Travel", "No data"}

    checkpoints = route_a["checkpoints"]
    assert summary["checkpoint_count"] == len(checkpoints) == 7  # 0, 25, ..., 125, ~138
    assert [c["mile"] for c in checkpoints[:3]] == [0.0, 25.0, 50.0]
    first = checkpoints[0]
    assert set(first) == {"index", "lat", "lon", "mile", "eta", "forecast_time", "weather", "risk"}
    assert first["weather"] == {"wind_mph": 8.0, "gust_mph": 0.0, "rain_in_per_hr": 0.6, "snow_in_per_hr": 0.0}
    assert first["risk"]["level"] == "Severe"
    assert first["risk"]["rain"] == "Severe"
    assert first["risk"]["reason"] == "Severe: rain 0.60 in/hr"
    assert first["forecast_time"].endswith(":00:00+00:00")
    # The last checkpoint is reached after the full route time.
    assert summary["arrival_time"] == checkpoints[-1]["eta"]


def test_plan_trip_accepts_coordinates_without_geocoding(client, fake_world, monkeypatch):
    def fail(text):
        raise AssertionError("geocoding should not be called")

    monkeypatch.setattr(geocoding_client, "search", fail)
    body = valid_body(origin={"lat": 40.0, "lon": -89.0, "name": "Start"}, destination={"lat": 42.0, "lon": -89.0})
    data = client.post("/api/plan-trip/", body, format="json").json()
    assert data["origin"] == {"name": "Start", "lat": 40.0, "lon": -89.0}
    assert data["destination"]["name"] == "42.0000, -89.0000"


def test_plan_trip_rejects_same_place_after_geocoding(client, fake_world, monkeypatch):
    monkeypatch.setattr(geocoding_client, "search", lambda text: Place(name=text, lat=40.0, lon=-89.0))
    response = client.post("/api/plan-trip/", valid_body(destination="Chicago downtown"), format="json")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_trip"


def test_plan_trip_passes_routing_warnings(client, fake_world, monkeypatch):
    monkeypatch.setattr(
        routing_client, "get_routes", lambda *a: RoutingResult(routes=ROUTES[1:2], warnings=["Only 1 distinct route(s) could be found for this trip."])
    )
    data = client.post("/api/plan-trip/", valid_body(), format="json").json()
    assert len(data["routes"]) == 1
    assert "Only 1 distinct route(s) could be found for this trip." in data["warnings"]
    assert data["recommendation"]["reason"] == "Route A is the only route found."


# --- Plan trip: validation --------------------------------------------------------


@pytest.mark.parametrize(
    "overrides, field",
    [
        ({"origin": ""}, "origin"),
        ({"origin": 42}, "origin"),
        ({"origin": {"lat": 95, "lon": 0}}, "origin"),
        ({"destination": {"lat": "x", "lon": 0}}, "destination"),
        ({"destination": "chicago, il"}, "destination"),  # same as origin
        ({"departure_time": "not a date"}, "departure_time"),
        ({"departure_time": departure(hours=-2)}, "departure_time"),
        ({"departure_time": departure(hours=24 * 8)}, "departure_time"),
        ({"load_weight_lb": 0}, "load_weight_lb"),
        ({"load_weight_lb": -5}, "load_weight_lb"),
        ({"load_weight_lb": 200_000}, "load_weight_lb"),
        ({"load_weight_lb": "heavy"}, "load_weight_lb"),
        ({"checkpoint_interval_miles": 15}, "checkpoint_interval_miles"),
    ],
)
def test_plan_trip_validation(client, overrides, field):
    response = client.post("/api/plan-trip/", valid_body(**overrides), format="json")
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "invalid_input"
    assert field in error["fields"]


def test_plan_trip_missing_fields(client):
    response = client.post("/api/plan-trip/", {}, format="json")
    assert response.status_code == 400
    assert set(response.json()["error"]["fields"]) == {"origin", "destination", "departure_time", "load_weight_lb"}


def test_plan_trip_default_interval_and_small_past_tolerance(client, fake_world):
    body = valid_body(departure_time=departure(hours=-0.25))
    del body["checkpoint_interval_miles"]
    response = client.post("/api/plan-trip/", body, format="json")
    assert response.status_code == 200
    assert response.json()["checkpoint_interval_miles"] == 25


def test_plan_trip_interval_as_string(client, fake_world):
    response = client.post("/api/plan-trip/", valid_body(checkpoint_interval_miles="10"), format="json")
    assert response.status_code == 200
    assert response.json()["checkpoint_interval_miles"] == 10


# --- Plan trip: service errors ----------------------------------------------------


@pytest.mark.parametrize(
    "error, status, code",
    [
        (NoRouteFound(), 422, "no_route"),
        (ServiceUnavailable("The weather service is having problems."), 502, "service_unavailable"),
    ],
)
def test_plan_trip_service_errors(client, monkeypatch, error, status, code):
    def fail(**kwargs):
        raise error

    monkeypatch.setattr(views, "plan_trip", fail)
    response = client.post("/api/plan-trip/", valid_body(), format="json")
    assert response.status_code == status
    assert response.json()["error"]["code"] == code


def test_unexpected_error_returns_clean_json(client, monkeypatch):
    def crash(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(views, "plan_trip", crash)
    response = client.post("/api/plan-trip/", valid_body(), format="json")
    assert response.status_code == 500
    assert response.json() == {"error": {"code": "server_error", "message": "Something went wrong on our side."}}


def test_plan_trip_is_throttled(client):
    statuses = [client.post("/api/plan-trip/", {}, format="json").status_code for _ in range(21)]
    assert statuses[:20] == [400] * 20
    assert statuses[20] == 429
    error = client.post("/api/plan-trip/", {}, format="json").json()["error"]
    assert error["code"] == "throttled"


# --- Geocode ------------------------------------------------------------------------


def test_geocode(client, fake_world):
    response = client.get("/api/geocode/", {"q": "Chic"})
    assert response.status_code == 200
    assert response.json() == {"results": [{"name": "Chicago, IL, USA", "lat": 41.88, "lon": -87.66}]}


@pytest.mark.parametrize("params", [{}, {"q": "Ch"}, {"q": "x" * 201}])
def test_geocode_validation(client, params):
    response = client.get("/api/geocode/", params)
    assert response.status_code == 400
    assert "q" in response.json()["error"]["fields"]


# --- Heatmap ------------------------------------------------------------------------


def test_heatmap_after_planning(client, fake_world):
    trip_id = client.post("/api/plan-trip/", valid_body(), format="json").json()["trip_id"]
    response = client.get("/api/heatmap/", {"trip_id": trip_id})
    assert response.status_code == 200
    data = response.json()
    assert data["trip_id"] == trip_id
    assert len(data["frames"]) == 49
    assert len(data["points"]) <= 250
    # Grid points near route A (lon -90) see the Severe rain, points near C don't.
    risks = dict(zip(map(tuple, data["points"]), data["frames"][0]["risk"]))
    assert max(risks.values()) == 3 and min(risks.values()) == 0


def test_heatmap_unknown_trip(client):
    response = client.get("/api/heatmap/", {"trip_id": "f" * 32})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "trip_not_found"


@pytest.mark.parametrize("params", [{}, {"trip_id": "not-a-trip"}, {"trip_id": "A" * 32}])
def test_heatmap_validation(client, params):
    response = client.get("/api/heatmap/", params)
    assert response.status_code == 400
    assert "trip_id" in response.json()["error"]["fields"]


def test_unknown_url_returns_404(client):
    assert client.get("/api/nope/").status_code == 404
