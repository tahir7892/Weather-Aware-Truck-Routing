import pytest

from planner.utils.geo import (
    MILES_PER_DEGREE_LAT,
    PointIndex,
    bounding_box,
    cumulative_distances,
    decode_polyline,
    haversine_miles,
    offset_point,
    overlap_fraction,
    positions_at_distances,
    resample,
    simplify,
)

CHICAGO = (41.8781, -87.6298)
INDIANAPOLIS = (39.7684, -86.1581)


# --- haversine_miles ---------------------------------------------------------


def test_distance_chicago_to_indianapolis():
    # Straight-line distance is about 165 miles.
    assert haversine_miles(CHICAGO, INDIANAPOLIS) == pytest.approx(165, rel=0.01)


def test_distance_same_point_is_zero():
    assert haversine_miles(CHICAGO, CHICAGO) == 0


def test_one_degree_of_latitude():
    assert haversine_miles((40.0, -90.0), (41.0, -90.0)) == pytest.approx(MILES_PER_DEGREE_LAT, rel=1e-6)


def test_distance_is_symmetric():
    assert haversine_miles(CHICAGO, INDIANAPOLIS) == pytest.approx(haversine_miles(INDIANAPOLIS, CHICAGO))


# --- decode_polyline ---------------------------------------------------------


def test_decode_reference_polyline():
    # Example from Google's polyline algorithm documentation.
    points = decode_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@")
    assert points == pytest.approx([(38.5, -120.2), (40.7, -120.95), (43.252, -126.453)])


def test_decode_empty_polyline():
    assert decode_polyline("") == []


# --- cumulative_distances ----------------------------------------------------


def test_cumulative_distances():
    points = [(40.0, -90.0), (41.0, -90.0), (42.0, -90.0)]
    assert cumulative_distances(points) == pytest.approx([0, MILES_PER_DEGREE_LAT, 2 * MILES_PER_DEGREE_LAT])


def test_cumulative_distances_single_point():
    assert cumulative_distances([(40.0, -90.0)]) == [0.0]


# --- positions_at_distances --------------------------------------------------

# Straight north-south line, 3 segments of 1 degree (~69.1 mi) each.
LINE = [(40.0, -90.0), (41.0, -90.0), (42.0, -90.0), (43.0, -90.0)]
LINE_CUMULATIVE = cumulative_distances(LINE)
SEGMENT = MILES_PER_DEGREE_LAT


def test_positions_at_start_middle_and_end():
    start, middle, end = positions_at_distances(LINE, LINE_CUMULATIVE, [0, 1.5 * SEGMENT, 3 * SEGMENT])
    assert start.point == pytest.approx((40.0, -90.0))
    assert middle.point == pytest.approx((41.5, -90.0))
    assert end.point == pytest.approx((43.0, -90.0))


def test_position_reports_segment_and_fraction():
    (position,) = positions_at_distances(LINE, LINE_CUMULATIVE, [1.25 * SEGMENT])
    assert position.segment_index == 1
    assert position.fraction == pytest.approx(0.25)


def test_position_on_a_vertex_stays_on_earlier_segment():
    (position,) = positions_at_distances(LINE, LINE_CUMULATIVE, [SEGMENT])
    assert position.segment_index == 0
    assert position.fraction == pytest.approx(1.0)


def test_positions_are_clamped_to_line_ends():
    before, after = positions_at_distances(LINE, LINE_CUMULATIVE, [-5, 10_000])
    assert before.point == pytest.approx((40.0, -90.0))
    assert after.point == pytest.approx((43.0, -90.0))
    assert after.segment_index == 2


def test_positions_handle_zero_length_segments():
    line = [(40.0, -90.0), (40.0, -90.0), (41.0, -90.0)]
    (position,) = positions_at_distances(line, cumulative_distances(line), [SEGMENT / 2])
    assert position.point == pytest.approx((40.5, -90.0))


def test_positions_require_ascending_distances():
    with pytest.raises(ValueError):
        positions_at_distances(LINE, LINE_CUMULATIVE, [50, 10])


def test_positions_require_two_points():
    with pytest.raises(ValueError):
        positions_at_distances([(40.0, -90.0)], [0.0], [0])


# --- simplify ----------------------------------------------------------------


def test_simplify_removes_points_on_a_straight_line():
    line = [(40.0 + i * 0.01, -90.0) for i in range(101)]
    assert simplify(line, tolerance_meters=10) == [line[0], line[-1]]


def test_simplify_keeps_real_corners():
    line = [(40.0, -90.0), (40.5, -90.0), (41.0, -90.0), (41.0, -89.5), (41.0, -89.0)]
    assert simplify(line, tolerance_meters=30) == [(40.0, -90.0), (41.0, -90.0), (41.0, -89.0)]


def test_simplify_drops_tiny_wiggles_but_keeps_big_ones():
    tiny = 0.0001  # ~11 m sideways
    big = 0.01  # ~1 km sideways
    line = [(40.0, -90.0), (40.1, -90.0 + tiny), (40.2, -90.0), (40.3, -90.0 + big), (40.4, -90.0)]
    # The 40.1 wiggle goes; 40.2 stays because it is the corner where the big wiggle starts.
    assert simplify(line, tolerance_meters=30) == [(40.0, -90.0), (40.2, -90.0), (40.3, -90.0 + big), (40.4, -90.0)]


def test_simplify_short_lines_are_unchanged():
    line = [(40.0, -90.0), (41.0, -90.0)]
    assert simplify(line, tolerance_meters=30) == line


# --- offset_point ------------------------------------------------------------


def test_offset_left_and_right_when_driving_north():
    start, end = (40.0, -90.0), (42.0, -90.0)
    left = offset_point(start, end, 0.15)
    right = offset_point(start, end, -0.15)
    # Driving north, left is west (smaller longitude).
    assert left[0] == pytest.approx(41.0) and left[1] < -90.0
    assert right[0] == pytest.approx(41.0) and right[1] > -90.0


def test_offset_distance_is_fraction_of_trip():
    start, end = CHICAGO, INDIANAPOLIS
    midpoint = offset_point(start, end, 0.0)
    pushed = offset_point(start, end, 0.3)
    assert haversine_miles(midpoint, pushed) == pytest.approx(0.3 * haversine_miles(start, end), rel=0.02)


def test_offset_along_the_trip():
    start, end = (40.0, -90.0), (42.0, -90.0)
    assert offset_point(start, end, 0.0, along=0.0) == pytest.approx(start)
    assert offset_point(start, end, 0.0, along=0.25) == pytest.approx((40.5, -90.0))
    assert offset_point(start, end, 0.0, along=1.0) == pytest.approx(end)


def test_offset_of_same_point_returns_it():
    assert offset_point(CHICAGO, CHICAGO, 0.3) == CHICAGO


# --- resample / PointIndex / overlap_fraction ---------------------------------


def test_resample_spacing_and_ends():
    line = [(40.0, -90.0), (41.0, -90.0)]  # ~69.1 miles
    points = resample(line, step_miles=10)
    assert points[0] == pytest.approx((40.0, -90.0))
    assert points[-1] == pytest.approx((41.0, -90.0))
    gaps = [haversine_miles(a, b) for a, b in zip(points, points[1:])]
    assert all(gap <= 10 + 1e-9 for gap in gaps)
    assert len(points) == 8


def test_point_index_finds_only_close_points():
    index = PointIndex([(40.0, -90.0), (45.0, -100.0)], radius_miles=5)
    assert index.has_point_near((40.05, -90.0))  # ~3.5 miles away
    assert not index.has_point_near((40.2, -90.0))  # ~14 miles away


def test_overlap_of_identical_lines_is_full():
    line = [(40.0, -90.0), (40.5, -90.0), (41.0, -90.0)]
    assert overlap_fraction(line, line) == pytest.approx(1.0)


def test_overlap_of_far_apart_lines_is_zero():
    assert overlap_fraction([(40.0, -90.0), (41.0, -90.0)], [(40.0, -89.0), (41.0, -89.0)]) == 0


def test_overlap_of_half_shared_lines():
    shared = [(40.0, -90.0), (40.5, -90.0)]
    line_a = shared + [(41.0, -90.0)]
    line_b = shared + [(40.5, -89.5)]
    assert overlap_fraction(line_a, line_b) == pytest.approx(0.5, abs=0.05)


def test_overlap_is_measured_from_the_first_line():
    short = [(40.0, -90.0), (40.5, -90.0)]
    long = [(40.0, -90.0), (41.0, -90.0)]
    assert overlap_fraction(short, long) == pytest.approx(1.0)
    assert overlap_fraction(long, short) == pytest.approx(0.5, abs=0.05)


# --- bounding_box ------------------------------------------------------------


def test_bounding_box_without_margin():
    assert bounding_box([CHICAGO, INDIANAPOLIS]) == (39.7684, -87.6298, 41.8781, -86.1581)


def test_bounding_box_margin_is_in_miles_on_every_side():
    min_lat, min_lon, max_lat, max_lon = bounding_box([CHICAGO, INDIANAPOLIS], margin_miles=30)
    assert haversine_miles((min_lat, -87.0), (39.7684, -87.0)) == pytest.approx(30, rel=0.01)
    assert haversine_miles((max_lat, -87.0), (41.8781, -87.0)) == pytest.approx(30, rel=0.01)
    # Longitude margin is measured at the northern edge, so it is at least 30 miles there.
    assert haversine_miles((41.8781, min_lon), (41.8781, -87.6298)) >= 30 * 0.99
    assert haversine_miles((41.8781, max_lon), (41.8781, -86.1581)) >= 30 * 0.99
