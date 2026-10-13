"""
Checkpoints along a route and the truck's ETA at each one.

A checkpoint is placed at mile 0, then every `interval_miles`, and at the
destination. The ETA uses the travel time ORS gives for each step of the road
(not one average speed), so slow city streets and fast highways are both
reflected. All times are timezone-aware UTC.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from planner.utils.geo import cumulative_distances, positions_at_distances

# A final stretch shorter than this is not given its own checkpoint.
MIN_LAST_STRETCH_MILES = 0.01


@dataclass
class Checkpoint:
    index: int
    lat: float
    lon: float
    mile: float
    eta: datetime
    # Filled in after the weather lookup.
    forecast_time: datetime | None = None
    weather: object | None = None  # planner.services.risk.WeatherSample
    risk: object | None = None  # planner.services.risk.RiskAssessment

    @property
    def point(self):
        return (self.lat, self.lon)


def checkpoint_miles(total_miles, interval_miles):
    """Mile markers 0, interval, 2*interval, ... and the end of the route."""
    if interval_miles <= 0:
        raise ValueError("Interval must be positive.")
    miles = []
    mile = 0.0
    while mile < total_miles:
        miles.append(mile)
        mile += interval_miles
    if not miles or total_miles - miles[-1] > MIN_LAST_STRETCH_MILES:
        miles.append(total_miles)
    else:
        miles[-1] = total_miles
    return miles


def vertex_times(cumulative_miles, step_timings):
    """
    Seconds from departure to each point of the route line.

    `step_timings` is a list of (start_index, end_index, duration_seconds), one
    per ORS step, covering the line in order. Inside a step the time is spread
    over its points in proportion to distance.
    """
    times = [0.0] * len(cumulative_miles)
    elapsed = 0.0
    for start, end, duration in step_timings:
        step_miles = cumulative_miles[end] - cumulative_miles[start]
        for i in range(start + 1, end + 1):
            if step_miles > 0:
                share = (cumulative_miles[i] - cumulative_miles[start]) / step_miles
            else:
                share = 1.0
            times[i] = elapsed + duration * share
        elapsed += duration
    # Points after the last step (should not happen with ORS data) keep the final time.
    for i in range(1, len(times)):
        times[i] = max(times[i], times[i - 1])
    return times


def build_checkpoints(points, step_timings, departure, interval_miles):
    """Place checkpoints along a route line and give each one an ETA."""
    if departure.tzinfo is None:
        raise ValueError("Departure time must be timezone-aware.")
    departure = departure.astimezone(timezone.utc)

    cumulative = cumulative_distances(points)
    times = vertex_times(cumulative, step_timings)
    miles = checkpoint_miles(cumulative[-1], interval_miles)
    positions = positions_at_distances(points, cumulative, miles)

    checkpoints = []
    for index, (mile, position) in enumerate(zip(miles, positions)):
        i = position.segment_index
        seconds = times[i] + (times[i + 1] - times[i]) * position.fraction
        checkpoints.append(
            Checkpoint(
                index=index,
                lat=position.lat,
                lon=position.lon,
                mile=mile,
                eta=departure + timedelta(seconds=seconds),
            )
        )
    return checkpoints


def nearest_hour(moment):
    """Round a datetime to the nearest whole hour (08:29 -> 08:00, 08:30 -> 09:00)."""
    floored = moment.replace(minute=0, second=0, microsecond=0)
    return floored + timedelta(hours=1) if moment - floored >= timedelta(minutes=30) else floored
