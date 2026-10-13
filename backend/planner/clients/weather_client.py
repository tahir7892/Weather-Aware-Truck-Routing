"""
Open-Meteo hourly forecasts for many points at once.

- Points are rounded (~0.1 degree) so nearby points share one lookup.
- Up to WEATHER_BATCH_SIZE points go in one request, and batches run in parallel.
- Every forecast is cached per point and hour window.
- Hours beyond Open-Meteo's forecast range are returned as missing (None),
  which the risk logic reports as "No data".
- If some batches fail, their points get no data and the rest still work;
  only if every batch fails is an error raised.

All times are UTC.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone as django_timezone

from planner.clients.http import fetch_json, make_cache_key
from planner.constants import (
    CACHE_TTL_WEATHER,
    WEATHER_BATCH_SIZE,
    WEATHER_COORD_DECIMALS,
    WEATHER_HOURLY_VARIABLES,
    WEATHER_MAX_FORECAST_DAYS,
    WEATHER_MAX_PARALLEL_REQUESTS,
)
from planner.exceptions import PlannerError, ServiceUnavailable

logger = logging.getLogger(__name__)

SERVICE = "weather"
HOUR = timedelta(hours=1)
TIME_FORMAT = "%Y-%m-%dT%H:%M"


@dataclass(frozen=True)
class HourlyForecast:
    """Hourly values for one point, starting at `start` (UTC, whole hour)."""

    start: datetime
    values: dict  # variable name -> tuple of hourly values (None where missing)

    def at(self, hour):
        """All variables at a whole UTC hour. Values are None if the hour is not covered."""
        index = round((hour - self.start) / HOUR)
        result = {}
        for name in WEATHER_HOURLY_VARIABLES:
            series = self.values.get(name, ())
            result[name] = series[index] if 0 <= index < len(series) else None
        return result


EMPTY_FORECAST = HourlyForecast(start=datetime(1970, 1, 1, tzinfo=timezone.utc), values={})


def round_point(point):
    return (round(point[0], WEATHER_COORD_DECIMALS), round(point[1], WEATHER_COORD_DECIMALS))


def floor_hour(moment):
    return moment.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)


def latest_forecast_hour():
    return floor_hour(django_timezone.now()) + timedelta(days=WEATHER_MAX_FORECAST_DAYS)


def get_forecasts(points, start, end):
    """
    Hourly forecasts from `start` to `end` (inclusive, UTC) for every point.

    Returns {rounded point: HourlyForecast}. Look up a point with round_point().
    """
    start = floor_hour(start)
    end = min(floor_hour(end), latest_forecast_hour())
    unique_points = sorted({round_point(p) for p in points})

    if end < start:
        # The whole window is beyond the forecast range.
        return {point: EMPTY_FORECAST for point in unique_points}

    # One cache entry per batch (not per point) keeps cache writes few and fast.
    batches = [tuple(unique_points[i : i + WEATHER_BATCH_SIZE]) for i in range(0, len(unique_points), WEATHER_BATCH_SIZE)]
    forecasts = {}
    missing = []
    for batch in batches:
        cached = cache.get(_cache_key(batch, start, end))
        if cached is not None:
            forecasts.update(zip(batch, cached))
        else:
            missing.append(batch)

    if missing:
        errors = []
        with ThreadPoolExecutor(max_workers=WEATHER_MAX_PARALLEL_REQUESTS) as pool:
            for batch, outcome in zip(missing, pool.map(lambda b: _try_fetch_batch(b, start, end), missing)):
                if isinstance(outcome, PlannerError):
                    # Points of a failed batch get no data; the trip still works.
                    errors.append(outcome)
                    forecasts.update((point, EMPTY_FORECAST) for point in batch)
                else:
                    forecasts.update(zip(batch, outcome))
                    cache.set(_cache_key(batch, start, end), outcome, CACHE_TTL_WEATHER)
        if len(errors) == len(batches):
            raise errors[0]

    return forecasts


def _try_fetch_batch(points, start, end):
    try:
        return _fetch_batch(points, start, end)
    except PlannerError as exc:
        logger.warning("Weather batch of %s points failed: %s", len(points), exc)
        return exc


def _cache_key(batch, start, end):
    return make_cache_key("weather", batch, start.isoformat(), end.isoformat())


def _fetch_batch(points, start, end):
    """One Open-Meteo request for up to WEATHER_BATCH_SIZE points."""
    status, body = fetch_json(
        "GET",
        settings.OPEN_METEO_BASE_URL,
        service=SERVICE,
        params={
            "latitude": ",".join(str(lat) for lat, _ in points),
            "longitude": ",".join(str(lon) for _, lon in points),
            "hourly": ",".join(WEATHER_HOURLY_VARIABLES),
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "timezone": "GMT",
            "start_hour": start.strftime(TIME_FORMAT),
            "end_hour": end.strftime(TIME_FORMAT),
        },
    )
    if status != 200:
        reason = body.get("reason") if isinstance(body, dict) else body
        logger.warning("Open-Meteo error (HTTP %s): %s", status, reason)
        raise ServiceUnavailable("The weather service could not process this request.")

    # One location returns an object, several return a list (same order as requested).
    locations = body if isinstance(body, list) else [body]
    if len(locations) != len(points):
        raise ServiceUnavailable("The weather service returned an unexpected number of locations.")
    return [parse_location(location) for location in locations]


def parse_location(data):
    hourly = data.get("hourly", {})
    times = hourly.get("time", [])
    if not times:
        return EMPTY_FORECAST
    start = datetime.strptime(times[0], TIME_FORMAT).replace(tzinfo=timezone.utc)
    values = {name: tuple(hourly.get(name, [None] * len(times))) for name in WEATHER_HOURLY_VARIABLES}
    return HourlyForecast(start=start, values=values)
