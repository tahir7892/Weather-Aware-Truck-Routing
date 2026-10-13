"""
Weather heatmap along the trip corridor for hours 0-48 after departure.

1. Load the planned trip (route lines, departure, load) from the cache.
2. Lay a grid over the area and keep only points within HEATMAP_CORRIDOR_MILES
   of any route (the "corridor"). The grid gets coarser until there are at
   most HEATMAP_MAX_POINTS points.
3. Fetch 49 hours of weather (hour 0 = departure hour) for all points at once.
4. Rate every point at every hour with the same risk rules and load as the
   checkpoints, so the heatmap and the routes always agree.

The whole result is returned in one response, so the frontend slider never
has to wait for the network.
"""

import math
from datetime import timedelta

from django.core.cache import cache

from planner.clients import weather_client
from planner.constants import CACHE_TTL_TRIP, HEATMAP_CORRIDOR_MILES, HEATMAP_HOURS, HEATMAP_MAX_POINTS
from planner.exceptions import TripNotFound
from planner.services.checkpoints import nearest_hour
from planner.services.risk import WeatherSample, assess
from planner.services.trip_planner import trip_cache_key
from planner.utils.geo import MILES_PER_DEGREE_LAT, PointIndex, bounding_box, cumulative_distances, resample

# Route lines are sampled this often when testing whether a grid point is in the corridor.
CORRIDOR_SAMPLE_MILES = 5
MIN_GRID_SPACING_MILES = 5
GRID_GROWTH = 1.15


def heatmap_cache_key(trip_id):
    return f"heatmap:{trip_id}"


def corridor_grid(lines, corridor_miles=HEATMAP_CORRIDOR_MILES, max_points=HEATMAP_MAX_POINTS):
    """
    Evenly spaced points within `corridor_miles` of any line.

    Returns (points, spacing_miles). The spacing starts from an estimate of the
    corridor's area and grows until the point count fits `max_points`.
    """
    samples = [point for line in lines for point in resample(list(line), CORRIDOR_SAMPLE_MILES)]
    corridor = PointIndex(samples, corridor_miles)
    min_lat, min_lon, max_lat, max_lon = bounding_box(samples, corridor_miles)
    mid_lat = (min_lat + max_lat) / 2
    miles_per_degree_lon = MILES_PER_DEGREE_LAT * max(math.cos(math.radians(mid_lat)), 0.01)

    longest_miles = max(cumulative_distances(list(line))[-1] for line in lines)
    estimated_area = longest_miles * 2 * corridor_miles + math.pi * corridor_miles**2
    spacing = max(MIN_GRID_SPACING_MILES, math.sqrt(estimated_area / max_points))

    while True:
        lat_step = spacing / MILES_PER_DEGREE_LAT
        lon_step = spacing / miles_per_degree_lon
        rows = int((max_lat - min_lat) / lat_step) + 1
        cols = int((max_lon - min_lon) / lon_step) + 1
        points = [
            (min_lat + row * lat_step, min_lon + col * lon_step)
            for row in range(rows)
            for col in range(cols)
            if corridor.has_point_near((min_lat + row * lat_step, min_lon + col * lon_step))
        ]
        if len(points) <= max_points:
            return points, spacing
        spacing *= GRID_GROWTH


def build_heatmap(trip_id):
    cached = cache.get(heatmap_cache_key(trip_id))
    if cached is not None:
        return cached

    trip = cache.get(trip_cache_key(trip_id))
    if trip is None:
        raise TripNotFound()

    points, spacing = corridor_grid(trip.lines)
    start = nearest_hour(trip.departure)
    hours = [start + timedelta(hours=h) for h in range(HEATMAP_HOURS + 1)]
    forecasts = weather_client.get_forecasts(points, hours[0], hours[-1])
    point_forecasts = [forecasts.get(weather_client.round_point(p), weather_client.EMPTY_FORECAST) for p in points]

    frames = []
    for hour in hours:
        frame = {"risk": [], "wind_mph": [], "rain_in_per_hr": [], "snow_in_per_hr": []}
        for forecast in point_forecasts:
            sample = WeatherSample.from_forecast(forecast.at(hour))
            weather = sample.to_dict()
            frame["risk"].append(assess(sample, trip.load_lb).score)
            frame["wind_mph"].append(weather["wind_mph"])
            frame["rain_in_per_hr"].append(weather["rain_in_per_hr"])
            frame["snow_in_per_hr"].append(weather["snow_in_per_hr"])
        frames.append(frame)

    result = {
        "trip_id": trip_id,
        "start_time": start.isoformat(),
        "hours": list(range(HEATMAP_HOURS + 1)),
        "times": [hour.isoformat() for hour in hours],
        "grid_spacing_miles": round(spacing, 1),
        "corridor_miles": HEATMAP_CORRIDOR_MILES,
        "points": [[round(lat, 4), round(lon, 4)] for lat, lon in points],
        "frames": frames,
    }
    cache.set(heatmap_cache_key(trip_id), result, CACHE_TTL_TRIP)
    return result
