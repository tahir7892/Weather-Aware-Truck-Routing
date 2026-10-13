from datetime import datetime, timedelta, timezone

import pytest
import requests

from planner.clients import geocoding_client, routing_client, weather_client
from planner.clients.http import fetch_json
from planner.exceptions import (
    LocationNotFound,
    NoRouteFound,
    ServiceRateLimited,
    ServiceUnavailable,
)
from planner.services.checkpoints import build_checkpoints
from planner.tests.conftest import load_fixture

CHICAGO = (41.8781, -87.6298)
JOLIET = (41.525, -88.0817)


# --- HTTP helper ----------------------------------------------------------------


@pytest.mark.parametrize(
    "status, error",
    [(429, ServiceRateLimited), (401, ServiceUnavailable), (403, ServiceUnavailable), (500, ServiceUnavailable)],
)
def test_fetch_json_maps_http_errors(fake_http, status, error):
    fake_http.add(status, {"error": "nope"})
    with pytest.raises(error):
        fetch_json("GET", "https://example.test", service="test")


def test_fetch_json_maps_network_errors(fake_http):
    fake_http.add(0, requests.Timeout("slow"))
    with pytest.raises(ServiceUnavailable, match="took too long"):
        fetch_json("GET", "https://example.test", service="test")


def test_fetch_json_rejects_non_json(fake_http):
    fake_http.add(200, "<html>")
    with pytest.raises(ServiceUnavailable, match="invalid response"):
        fetch_json("GET", "https://example.test", service="test")


def test_fetch_json_returns_client_errors_to_caller(fake_http):
    fake_http.add(404, {"error": {"code": 2010}})
    assert fetch_json("GET", "https://example.test", service="test") == (404, {"error": {"code": 2010}})


def test_ors_key_missing(settings, fake_http):
    settings.ORS_API_KEY = ""
    with pytest.raises(ServiceUnavailable, match="not configured"):
        geocoding_client.search("Chicago")


# --- Geocoding ----------------------------------------------------------------


def test_autocomplete_parses_places(fake_http):
    fake_http.add(200, load_fixture("ors_autocomplete_chicago.json"))
    places = geocoding_client.autocomplete("Chicag")
    assert places[0].name == "Chicago, IL, USA"
    assert places[0].lat == pytest.approx(41.88, abs=0.05)
    assert places[0].lon == pytest.approx(-87.66, abs=0.05)
    call = fake_http.calls[0]
    assert call["params"]["boundary.country"] == "US"
    assert call["headers"]["Authorization"] == "test-key"
    assert "test-key" not in call["url"]


def test_search_returns_best_match_and_caches(fake_http):
    fake_http.add(200, load_fixture("ors_autocomplete_chicago.json"))
    first = geocoding_client.search("  Chicago,   IL ")
    second = geocoding_client.search("chicago, il")
    assert first == second
    assert len(fake_http.calls) == 1
    assert fake_http.calls[0]["params"]["text"] == "Chicago, IL"


def test_search_not_found(fake_http):
    fake_http.add(200, {"type": "FeatureCollection", "features": []})
    with pytest.raises(LocationNotFound, match="Could not find location: Nowhere"):
        geocoding_client.search("Nowhere")


# --- Routing: parsing ----------------------------------------------------------


def test_parse_real_route():
    route = routing_client.parse_route(load_fixture("ors_route_chicago_joliet.json")["routes"][0])
    assert route.points[0] == pytest.approx(CHICAGO, abs=0.01)
    assert route.points[-1] == pytest.approx(JOLIET, abs=0.01)
    assert 30 < route.distance_miles < 60
    assert route.duration_seconds > 0
    # Steps cover the whole line, in order, and add up to the route time.
    assert route.step_timings[0][0] == 0
    assert route.step_timings[-1][1] == len(route.points) - 1
    assert sum(duration for _, _, duration in route.step_timings) == pytest.approx(route.duration_seconds, rel=0.01)


def test_real_route_checkpoints_end_at_route_duration():
    route = routing_client.parse_route(load_fixture("ors_route_chicago_joliet.json")["routes"][0])
    departure = datetime(2026, 10, 12, 8, tzinfo=timezone.utc)
    checkpoints = build_checkpoints(list(route.points), route.step_timings, departure, 10)
    travel = (checkpoints[-1].eta - departure).total_seconds()
    assert travel == pytest.approx(route.duration_seconds, abs=60)
    assert checkpoints[-1].mile == pytest.approx(route.distance_miles, rel=0.02)


def test_via_label_prefers_highways_by_distance():
    steps = [
        {"name": "-", "distance": 50_000},
        {"name": "Main Street", "distance": 40_000},
        {"name": "I 65", "distance": 30_000},
        {"name": "Dan Ryan Expressway, I 94", "distance": 20_000},
        {"name": "US 41", "distance": 5_000},  # under 10% of the route: not named
    ]
    assert routing_client.via_label(steps) == "I-65 / I-94"


def test_via_label_falls_back_to_road_names():
    steps = [{"name": "Main Street", "distance": 100}, {"name": "Oak Road", "distance": 300}]
    assert routing_client.via_label(steps) == "Oak Road / Main Street"


def test_via_label_ignores_short_named_pieces():
    # Mostly unnamed highway; a short named stretch must not become the label.
    steps = [{"name": "-", "distance": 400_000}, {"name": "I 80", "distance": 10_000}]
    assert routing_client.via_label(steps) == ""


# --- Routing: via-points ---------------------------------------------------------


def test_snap_points_parses_locations(fake_http):
    fake_http.add(200, {"locations": [{"location": [-90.01, 40.02], "snapped_distance": 900}, None]})
    assert routing_client.snap_points([(40.0, -90.0), (30.0, -60.0)]) == [(40.02, -90.01), None]
    body = fake_http.calls[0]["json"]
    assert body["locations"] == [[-90.0, 40.0], [-60.0, 30.0]]
    assert "/v2/snap/driving-hgv" in fake_http.calls[0]["url"]


@pytest.mark.parametrize("status, body", [(500, {}), (400, {"error": "bad"}), (200, {"locations": []})])
def test_snap_points_failure_returns_none(fake_http, status, body):
    fake_http.add(status, body)
    assert routing_client.snap_points([(40.0, -90.0)]) is None


def test_detour_vias_use_first_candidate_on_a_road(monkeypatch):
    shapes = len(routing_client.VIA_CANDIDATE_SHAPES)

    def fake_snap(points):
        assert len(points) == shapes * len(routing_client.DETOUR_OFFSET_FRACTIONS)
        result = []
        for group in range(len(routing_client.DETOUR_OFFSET_FRACTIONS)):
            if group == 0:  # ideal spot off-road, second candidate on a road
                result += [None, (1.0, 1.0)] + [(9.0, 9.0)] * (shapes - 2)
            elif group == 1:  # nothing near a road (e.g. at sea)
                result += [None] * shapes
            else:
                result += [(float(group), 0.0)] * shapes
        return result

    monkeypatch.setattr(routing_client, "snap_points", fake_snap)
    vias = routing_client.detour_vias((40.0, -90.0), (41.0, -90.0))
    assert vias[0] == (1.0, 1.0)
    assert vias[1] is None
    assert vias[2] == (2.0, 0.0)


def test_detour_vias_fall_back_to_ideal_points(monkeypatch):
    monkeypatch.setattr(routing_client, "snap_points", lambda points: None)
    vias = routing_client.detour_vias((40.0, -90.0), (42.0, -90.0))
    assert vias[0][0] == pytest.approx(41.0)  # midpoint latitude
    assert vias[0][1] < -90.0  # first fraction is to the left (west)


def test_detour_route_without_via_is_skipped():
    assert routing_client.detour_route(CHICAGO, JOLIET, None, None) is None


# --- Routing: requests, distinct routes, errors ---------------------------------


def _route(points, duration=3600):
    return routing_client.Route(points=tuple(points), distance_miles=50, duration_seconds=duration, step_timings=(), via="")


EAST = _route([(40.0, -90.0), (40.5, -89.5), (41.0, -90.0)])
DIRECT = _route([(40.0, -90.0), (40.5, -90.0), (41.0, -90.0)])
WEST = _route([(40.0, -90.0), (40.5, -90.5), (41.0, -90.0)])


def test_is_distinct():
    assert routing_client.is_distinct(EAST, [DIRECT, WEST])
    assert not routing_client.is_distinct(_route(DIRECT.points), [DIRECT])


def test_add_distinct_skips_duplicates_slow_routes_and_failures():
    slow = _route(EAST.points, duration=3600 * 2)  # more than 1.5x the main route
    routes = routing_client.add_distinct([DIRECT], [None, _route(DIRECT.points), slow, WEST, EAST])
    assert routes == [DIRECT, WEST, EAST]


def test_request_body_sends_truck_weight_and_radiuses(fake_http):
    fake_http.add(200, load_fixture("ors_route_chicago_joliet.json"))
    routing_client.request_routes([CHICAGO, (41.7, -87.9), JOLIET], weight_tonnes=36.29)
    body = fake_http.calls[0]["json"]
    assert body["coordinates"][0] == [CHICAGO[1], CHICAGO[0]]  # ORS wants [lon, lat]
    assert body["options"] == {"vehicle_type": "hgv", "profile_params": {"restrictions": {"weight": 36.3}}}
    assert body["radiuses"] == [5000, -1, 5000]


def test_gross_weight():
    # 35,000 lb truck + 45,000 lb load = 80,000 lb = 36.29 t
    assert routing_client.gross_weight_tonnes(45_000) == pytest.approx(36.29, abs=0.01)


def test_get_routes_point_not_found(fake_http):
    # Main route, via-point snapping and two detours all get the same 404.
    for _ in range(4):
        fake_http.add(404, load_fixture("ors_error_point_not_found.json"))
    with pytest.raises(NoRouteFound, match="not near a road"):
        routing_client.get_routes(CHICAGO, (30.0, -60.0), 20_000)


def test_get_routes_retries_without_weight_limit(monkeypatch):
    weights = []

    def fake_find(origin, destination, weight_tonnes):
        weights.append(weight_tonnes)
        if weight_tonnes is not None:
            raise routing_client.OrsError(routing_client.ORS_ROUTE_NOT_FOUND, "no route")
        return [DIRECT, EAST, WEST]

    monkeypatch.setattr(routing_client, "find_routes", fake_find)
    result = routing_client.get_routes(CHICAGO, JOLIET, 100_000)
    assert weights[1] is None
    assert len(result.routes) == 3
    assert "without weight restrictions" in result.warnings[0]


def test_get_routes_warns_when_fewer_than_three(monkeypatch):
    monkeypatch.setattr(routing_client, "find_routes", lambda *a: [DIRECT])
    result = routing_client.get_routes(CHICAGO, JOLIET, 20_000)
    assert result.warnings == ["Only 1 distinct route(s) could be found for this trip."]


def test_get_routes_is_cached(monkeypatch):
    calls = []
    monkeypatch.setattr(routing_client, "find_routes", lambda *a: calls.append(a) or [DIRECT, EAST, WEST])
    routing_client.get_routes(CHICAGO, JOLIET, 20_000)
    routing_client.get_routes(CHICAGO, JOLIET, 20_000)
    assert len(calls) == 1


@pytest.fixture
def no_snapping(monkeypatch):
    monkeypatch.setattr(routing_client, "snap_points", lambda points: points)


def test_find_routes_adds_left_and_right_detours(monkeypatch, no_snapping):
    requested = []

    def fake_request(coordinates, weight_tonnes=None):
        requested.append(coordinates)
        if len(coordinates) == 2:
            return [DIRECT]
        # Driving north, a via-point west of the line is the left detour.
        return [WEST if coordinates[1][1] < -90.0 else EAST]

    monkeypatch.setattr(routing_client, "request_routes", fake_request)
    routes = routing_client.find_routes((40.0, -90.0), (41.0, -90.0), None)
    assert routes == [DIRECT, WEST, EAST]
    assert len(requested) == 3  # no second round needed


def test_find_routes_tries_wider_detours_when_needed(monkeypatch, no_snapping):
    requested = []

    def fake_request(coordinates, weight_tonnes=None):
        requested.append(coordinates)
        if len(coordinates) == 2:
            return [DIRECT]
        via_lon = coordinates[1][1]
        if abs(via_lon + 90.0) < 0.25:  # the narrow +-15% detours (~0.2 deg) just rejoin the direct road
            return [DIRECT]
        return [WEST if via_lon < -90.0 else EAST]

    monkeypatch.setattr(routing_client, "request_routes", fake_request)
    routes = routing_client.find_routes((40.0, -90.0), (41.0, -90.0), None)
    assert routes == [DIRECT, WEST, EAST]
    assert len(requested) == 1 + len(routing_client.DETOUR_OFFSET_FRACTIONS)


def test_find_routes_raises_when_main_route_fails(monkeypatch, no_snapping):
    def fake_request(coordinates, weight_tonnes=None):
        raise routing_client.OrsError(routing_client.ORS_ROUTE_NOT_FOUND, "no route")

    monkeypatch.setattr(routing_client, "request_routes", fake_request)
    with pytest.raises(routing_client.OrsError):
        routing_client.find_routes((40.0, -90.0), (41.0, -90.0), None)


# --- Weather --------------------------------------------------------------------


def _weather_window():
    fixture = load_fixture("open_meteo_two_locations.json")
    start = datetime.strptime(fixture[0]["hourly"]["time"][0], "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)
    return fixture, start


def test_forecasts_for_two_points(fake_http):
    fixture, start = _weather_window()
    chicago, joliet = fixture  # fixture was saved as (41.9, -87.6), (41.5, -88.1)
    # The client requests rounded points in sorted order; Open-Meteo answers in that order.
    fake_http.add(200, [joliet, chicago])
    forecasts = weather_client.get_forecasts([(41.91, -87.62), (41.52, -88.08)], start, start + timedelta(hours=3))

    assert set(forecasts) == {(41.9, -87.6), (41.5, -88.1)}
    assert forecasts[(41.9, -87.6)].at(start)["wind_speed_10m"] == chicago["hourly"]["wind_speed_10m"][0]
    assert forecasts[(41.5, -88.1)].at(start)["wind_speed_10m"] == joliet["hourly"]["wind_speed_10m"][0]
    params = fake_http.calls[0]["params"]
    assert params["latitude"] == "41.5,41.9"
    assert params["longitude"] == "-88.1,-87.6"
    assert params["wind_speed_unit"] == "mph"
    assert params["precipitation_unit"] == "inch"
    assert params["timezone"] == "GMT"
    assert "showers" in params["hourly"]


def test_forecast_hours_outside_window_are_missing(fake_http):
    fixture, start = _weather_window()
    fake_http.add(200, fixture)
    forecast = weather_client.get_forecasts([(41.9, -87.6), (41.5, -88.1)], start, start + timedelta(hours=3))[(41.9, -87.6)]
    assert forecast.at(start + timedelta(hours=10))["rain"] is None
    assert forecast.at(start - timedelta(hours=1))["rain"] is None


def test_forecasts_are_cached(fake_http):
    fixture, start = _weather_window()
    fake_http.add(200, fixture)
    points = [(41.9, -87.6), (41.5, -88.1)]
    weather_client.get_forecasts(points, start, start + timedelta(hours=3))
    weather_client.get_forecasts(points, start, start + timedelta(hours=3))
    assert len(fake_http.calls) == 1


def test_forecasts_are_batched(fake_http, monkeypatch):
    monkeypatch.setattr(weather_client, "WEATHER_BATCH_SIZE", 1)
    fixture, start = _weather_window()
    fake_http.add(200, fixture[0])  # single location -> object, not list
    fake_http.add(200, fixture[1])
    forecasts = weather_client.get_forecasts([(41.9, -87.6), (41.5, -88.1)], start, start + timedelta(hours=3))
    assert len(fake_http.calls) == 2
    assert len(forecasts) == 2


def test_nearby_points_share_one_lookup(fake_http):
    fixture, start = _weather_window()
    fake_http.add(200, fixture[0])
    forecasts = weather_client.get_forecasts([(41.91, -87.61), (41.94, -87.58)], start, start)
    assert list(forecasts) == [(41.9, -87.6)]


def test_window_beyond_forecast_range_gives_no_data(fake_http):
    far = datetime.now(timezone.utc) + timedelta(days=30)
    forecasts = weather_client.get_forecasts([(41.9, -87.6)], far, far + timedelta(hours=5))
    assert fake_http.calls == []
    assert forecasts[(41.9, -87.6)].at(far.replace(minute=0, second=0, microsecond=0))["rain"] is None


def test_weather_error_is_reported(fake_http):
    fake_http.add(400, {"reason": "bad", "error": True})
    start = datetime.now(timezone.utc)
    with pytest.raises(ServiceUnavailable):
        weather_client.get_forecasts([(41.9, -87.6)], start, start + timedelta(hours=1))


def test_weather_rate_limit_is_reported(fake_http):
    fake_http.add(429, {"reason": "slow down"})
    start = datetime.now(timezone.utc)
    with pytest.raises(ServiceRateLimited):
        weather_client.get_forecasts([(41.9, -87.6)], start, start + timedelta(hours=1))


def test_one_failed_batch_gives_no_data_for_its_points_only(fake_http, monkeypatch):
    monkeypatch.setattr(weather_client, "WEATHER_BATCH_SIZE", 1)
    monkeypatch.setattr(weather_client, "WEATHER_MAX_PARALLEL_REQUESTS", 1)  # deterministic order
    fixture, start = _weather_window()
    fake_http.add(200, fixture[1])  # (41.5, -88.1) is requested first
    fake_http.add(0, requests.ConnectionError("network down"))
    forecasts = weather_client.get_forecasts([(41.9, -87.6), (41.5, -88.1)], start, start + timedelta(hours=3))

    assert forecasts[(41.5, -88.1)].at(start)["wind_speed_10m"] is not None
    assert forecasts[(41.9, -87.6)].at(start)["wind_speed_10m"] is None


def test_failed_batches_are_not_cached(fake_http):
    fixture, start = _weather_window()
    points = [(41.9, -87.6), (41.5, -88.1)]
    fake_http.add(0, requests.ConnectionError("network down"))
    with pytest.raises(ServiceUnavailable):
        weather_client.get_forecasts(points, start, start + timedelta(hours=3))
    fake_http.add(200, [fixture[1], fixture[0]])
    assert weather_client.get_forecasts(points, start, start + timedelta(hours=3))[(41.9, -87.6)].values
