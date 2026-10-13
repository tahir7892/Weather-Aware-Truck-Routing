from datetime import datetime, timedelta, timezone

import pytest
from django.core.cache import cache

from planner.clients import weather_client
from planner.clients.weather_client import HourlyForecast
from planner.constants import HEATMAP_HOURS, WEATHER_HOURLY_VARIABLES
from planner.exceptions import TripNotFound
from planner.services import heatmap
from planner.services.heatmap import build_heatmap, corridor_grid
from planner.services.trip_planner import TripSnapshot, trip_cache_key
from planner.utils.geo import haversine_miles, resample

# ~207 miles straight north.
LINE = ((40.0, -90.0), (41.0, -90.0), (42.0, -90.0), (43.0, -90.0))
DEPARTURE = datetime(2026, 10, 12, 8, 20, tzinfo=timezone.utc)


def distance_to_line(point, line):
    return min(haversine_miles(point, p) for p in resample(list(line), 1))


# --- corridor_grid ------------------------------------------------------------


def test_grid_points_stay_inside_corridor():
    points, _ = corridor_grid([LINE], corridor_miles=30, max_points=250)
    assert points
    # Corridor samples are every 5 miles, so allow a few miles of slack.
    assert all(distance_to_line(p, LINE) <= 30 + 3 for p in points)


def test_grid_covers_whole_route():
    points, spacing = corridor_grid([LINE], corridor_miles=30, max_points=250)
    for route_point in resample(list(LINE), 20):
        assert min(haversine_miles(route_point, p) for p in points) <= spacing


@pytest.mark.parametrize("max_points", [50, 120, 250])
def test_grid_respects_point_limit(max_points):
    points, _ = corridor_grid([LINE], corridor_miles=30, max_points=max_points)
    assert 0 < len(points) <= max_points


def test_grid_spacing_never_below_minimum():
    short_line = ((40.0, -90.0), (40.1, -90.0))
    _, spacing = corridor_grid([short_line], corridor_miles=30, max_points=10_000)
    assert spacing >= heatmap.MIN_GRID_SPACING_MILES


def test_grid_covers_all_routes():
    west = ((40.0, -91.5), (43.0, -91.5))
    points, _ = corridor_grid([LINE, west], corridor_miles=20, max_points=250)
    assert any(distance_to_line(p, west) < 10 for p in points)
    assert any(distance_to_line(p, LINE) < 10 for p in points)


# --- build_heatmap ------------------------------------------------------------


def save_trip(trip_id="a" * 32, load_lb=45_000):
    cache.set(trip_cache_key(trip_id), TripSnapshot(lines=(LINE,), departure=DEPARTURE, load_lb=load_lb), 60)
    return trip_id


def fake_forecasts(values, missing_after_hour=None):
    """Patchable get_forecasts returning the same hourly values for every point."""
    calls = []

    def get_forecasts(points, start, end):
        calls.append((len(points), start, end))
        hours = HEATMAP_HOURS + 1
        series = {}
        for name in WEATHER_HOURLY_VARIABLES:
            value = values.get(name, 0.0)
            series[name] = tuple(value if missing_after_hour is None or h <= missing_after_hour else None for h in range(hours))
        forecast = HourlyForecast(start=start, values=series)
        return {weather_client.round_point(p): forecast for p in points}

    get_forecasts.calls = calls
    return get_forecasts


def test_missing_trip_raises():
    with pytest.raises(TripNotFound):
        build_heatmap("b" * 32)


def test_heatmap_shape_and_hours(monkeypatch):
    fake = fake_forecasts({"wind_speed_10m": 10.0})
    monkeypatch.setattr(weather_client, "get_forecasts", fake)
    result = build_heatmap(save_trip())

    assert result["hours"] == list(range(49))
    assert len(result["times"]) == len(result["frames"]) == 49
    # Hour 0 is the departure rounded to the nearest hour (08:20 -> 08:00).
    assert result["start_time"] == "2026-10-12T08:00:00+00:00"
    assert result["times"][48] == "2026-10-14T08:00:00+00:00"
    for frame in result["frames"]:
        for values in frame.values():
            assert len(values) == len(result["points"])
    _, start, end = fake.calls[0]
    assert end - start == timedelta(hours=48)


def test_heatmap_uses_same_risk_rules_and_load(monkeypatch):
    # 40 mph wind is High, but Severe for loads over 40,000 lb.
    monkeypatch.setattr(weather_client, "get_forecasts", fake_forecasts({"wind_speed_10m": 40.0}))
    heavy = build_heatmap(save_trip("c" * 32, load_lb=45_000))
    light = build_heatmap(save_trip("d" * 32, load_lb=20_000))
    assert set(heavy["frames"][0]["risk"]) == {3}
    assert set(light["frames"][0]["risk"]) == {2}


def test_heatmap_rain_includes_showers(monkeypatch):
    monkeypatch.setattr(weather_client, "get_forecasts", fake_forecasts({"rain": 0.2, "showers": 0.1}))
    result = build_heatmap(save_trip())
    assert set(result["frames"][0]["rain_in_per_hr"]) == {0.3}
    assert set(result["frames"][0]["risk"]) == {2}  # 0.30 in/hr is High


def test_heatmap_missing_hours_are_null(monkeypatch):
    monkeypatch.setattr(weather_client, "get_forecasts", fake_forecasts({"wind_speed_10m": 5.0}, missing_after_hour=10))
    result = build_heatmap(save_trip())
    assert set(result["frames"][10]["risk"]) == {0}
    assert set(result["frames"][11]["risk"]) == {None}


def test_heatmap_is_cached(monkeypatch):
    fake = fake_forecasts({})
    monkeypatch.setattr(weather_client, "get_forecasts", fake)
    trip_id = save_trip()
    first = build_heatmap(trip_id)
    second = build_heatmap(trip_id)
    assert first == second
    assert len(fake.calls) == 1
