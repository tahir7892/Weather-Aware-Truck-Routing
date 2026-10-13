from datetime import datetime, timedelta, timezone

import pytest

from planner.services.checkpoints import (
    build_checkpoints,
    checkpoint_miles,
    nearest_hour,
    vertex_times,
)
from planner.utils.geo import MILES_PER_DEGREE_LAT, cumulative_distances

DEPARTURE = datetime(2026, 10, 12, 8, 0, tzinfo=timezone.utc)

# Straight line north, 4 points, each segment ~69.1 miles.
LINE = [(40.0, -90.0), (41.0, -90.0), (42.0, -90.0), (43.0, -90.0)]
SEGMENT = MILES_PER_DEGREE_LAT


# --- checkpoint_miles ----------------------------------------------------------


def test_miles_include_start_every_interval_and_end():
    assert checkpoint_miles(95, 25) == [0, 25, 50, 75, 95]


def test_miles_when_route_is_exact_multiple():
    assert checkpoint_miles(100, 25) == [0, 25, 50, 75, 100]


def test_miles_for_route_shorter_than_interval():
    assert checkpoint_miles(7.5, 10) == [0, 7.5]


def test_miles_tiny_leftover_is_merged_into_end():
    assert checkpoint_miles(50.005, 25) == [0, 25, 50.005]


@pytest.mark.parametrize("interval", [10, 25, 50])
def test_miles_spacing(interval):
    miles = checkpoint_miles(333, interval)
    gaps = [b - a for a, b in zip(miles, miles[1:])]
    assert all(gap == pytest.approx(interval) for gap in gaps[:-1])
    assert 0 < gaps[-1] <= interval


def test_miles_reject_bad_interval():
    with pytest.raises(ValueError):
        checkpoint_miles(100, 0)


# --- vertex_times --------------------------------------------------------------


def test_vertex_times_spread_by_distance_inside_a_step():
    cumulative = [0, 10, 30, 40]
    # One step over the whole line taking 400 s -> 10 s per mile.
    assert vertex_times(cumulative, [(0, 3, 400)]) == pytest.approx([0, 100, 300, 400])


def test_vertex_times_follow_each_step_speed():
    cumulative = [0, 10, 20]
    # First 10 miles slow (city), next 10 miles fast (highway).
    assert vertex_times(cumulative, [(0, 1, 1200), (1, 2, 600)]) == pytest.approx([0, 1200, 1800])


def test_vertex_times_handle_zero_length_steps():
    cumulative = [0, 10, 10]
    assert vertex_times(cumulative, [(0, 1, 600), (1, 2, 0), (2, 2, 0)]) == pytest.approx([0, 600, 600])


# --- build_checkpoints ---------------------------------------------------------


def test_checkpoints_positions_and_etas_at_constant_speed():
    # 3 segments, each 1 hour.
    steps = [(0, 1, 3600), (1, 2, 3600), (2, 3, 3600)]
    checkpoints = build_checkpoints(LINE, steps, DEPARTURE, interval_miles=50)

    assert [round(c.mile, 3) for c in checkpoints] == [0, 50, 100, 150, 200, round(3 * SEGMENT, 3)]
    assert checkpoints[0].point == pytest.approx((40.0, -90.0))
    assert checkpoints[-1].point == pytest.approx((43.0, -90.0))
    assert checkpoints[0].eta == DEPARTURE
    assert checkpoints[-1].eta == DEPARTURE + timedelta(hours=3)
    # Mile 100 is 100 / 69.1 segments in -> that many hours.
    expected = DEPARTURE + timedelta(hours=100 / SEGMENT)
    assert abs(checkpoints[2].eta - expected) < timedelta(seconds=1)


def test_checkpoints_use_step_speeds_not_an_average():
    # First segment takes 2 hours (slow), the other two 30 minutes each.
    steps = [(0, 1, 7200), (1, 2, 1800), (2, 3, 1800)]
    checkpoints = build_checkpoints(LINE, steps, DEPARTURE, interval_miles=10)
    by_mile = {round(c.mile): c for c in checkpoints}

    end_of_slow_part = DEPARTURE + timedelta(hours=2)
    assert by_mile[60].eta < end_of_slow_part < by_mile[70].eta
    assert checkpoints[-1].eta == DEPARTURE + timedelta(hours=3)


def test_checkpoints_are_indexed_in_order():
    steps = [(0, 3, 3 * 3600)]
    checkpoints = build_checkpoints(LINE, steps, DEPARTURE, interval_miles=25)
    assert [c.index for c in checkpoints] == list(range(len(checkpoints)))
    assert all(a.eta <= b.eta for a, b in zip(checkpoints, checkpoints[1:]))


def test_checkpoints_convert_departure_to_utc():
    chicago_time = timezone(timedelta(hours=-5))
    local_departure = datetime(2026, 10, 12, 3, 0, tzinfo=chicago_time)  # = 08:00 UTC
    checkpoints = build_checkpoints(LINE, [(0, 3, 3600)], local_departure, interval_miles=50)
    assert checkpoints[0].eta == DEPARTURE
    assert checkpoints[0].eta.tzinfo == timezone.utc


def test_checkpoints_reject_naive_departure():
    with pytest.raises(ValueError):
        build_checkpoints(LINE, [(0, 3, 3600)], datetime(2026, 10, 12, 8, 0), interval_miles=50)


def test_checkpoint_count_matches_interval():
    total = cumulative_distances(LINE)[-1]  # ~207 miles
    checkpoints = build_checkpoints(LINE, [(0, 3, 3600)], DEPARTURE, interval_miles=10)
    assert len(checkpoints) == int(total // 10) + 2


# --- nearest_hour --------------------------------------------------------------


@pytest.mark.parametrize(
    "minute, expected_hour",
    [(0, 8), (29, 8), (30, 9), (55, 9)],
)
def test_nearest_hour(minute, expected_hour):
    moment = datetime(2026, 10, 12, 8, minute, 15, tzinfo=timezone.utc)
    assert nearest_hour(moment) == datetime(2026, 10, 12, expected_hour, 0, tzinfo=timezone.utc)
