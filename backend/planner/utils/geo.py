"""
Map math used across the app.

Convention: a point is a (lat, lon) tuple in degrees. Distances are in miles
unless a name says otherwise. Over the short pieces of a route line the
Earth is treated as flat, which is accurate to well under 1%.
"""

import math
from dataclasses import dataclass

from planner.constants import EARTH_RADIUS_MILES, METERS_PER_MILE

MILES_PER_DEGREE_LAT = math.pi * EARTH_RADIUS_MILES / 180  # ~69.1


def haversine_miles(a, b):
    """Great-circle distance between two points."""
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(min(1.0, h)))


def decode_polyline(encoded, precision=5):
    """Decode a Google-format encoded polyline (what ORS returns) into (lat, lon) points."""
    factor = 10**precision
    points = []
    index = lat = lon = 0
    length = len(encoded)

    while index < length:
        deltas = []
        for _ in range(2):
            result = shift = 0
            while True:
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            deltas.append(~(result >> 1) if result & 1 else result >> 1)
        lat += deltas[0]
        lon += deltas[1]
        points.append((lat / factor, lon / factor))

    return points


def cumulative_distances(points):
    """Miles from the first point to each point along the line. First value is 0."""
    distances = [0.0]
    for previous, current in zip(points, points[1:]):
        distances.append(distances[-1] + haversine_miles(previous, current))
    return distances


@dataclass(frozen=True)
class PathPosition:
    """A spot on a line: it lies `fraction` of the way along segment `segment_index`."""

    lat: float
    lon: float
    segment_index: int
    fraction: float

    @property
    def point(self):
        return (self.lat, self.lon)


def positions_at_distances(points, cumulative, distances):
    """
    Walk along a line and return the position at each requested mile marker.

    `cumulative` comes from cumulative_distances(points). `distances` must be in
    ascending order; values outside the line are clamped to its ends.
    """
    if len(points) < 2:
        raise ValueError("A line needs at least two points.")
    if any(later < earlier for earlier, later in zip(distances, distances[1:])):
        raise ValueError("Distances must be in ascending order.")

    total = cumulative[-1]
    last_segment = len(points) - 2
    segment = 0
    positions = []

    for distance in distances:
        distance = min(max(distance, 0.0), total)
        while segment < last_segment and cumulative[segment + 1] < distance:
            segment += 1

        segment_length = cumulative[segment + 1] - cumulative[segment]
        fraction = (distance - cumulative[segment]) / segment_length if segment_length > 0 else 0.0
        (lat1, lon1), (lat2, lon2) = points[segment], points[segment + 1]
        positions.append(
            PathPosition(
                lat=lat1 + (lat2 - lat1) * fraction,
                lon=lon1 + (lon2 - lon1) * fraction,
                segment_index=segment,
                fraction=fraction,
            )
        )

    return positions


def _to_local_xy(point, reference_lat):
    """Project a point to flat x/y miles around a reference latitude."""
    lat, lon = point
    return (
        lon * MILES_PER_DEGREE_LAT * math.cos(math.radians(reference_lat)),
        lat * MILES_PER_DEGREE_LAT,
    )


def _from_local_xy(x, y, reference_lat):
    return (
        y / MILES_PER_DEGREE_LAT,
        x / (MILES_PER_DEGREE_LAT * math.cos(math.radians(reference_lat))),
    )


def simplify(points, tolerance_meters):
    """
    Remove points that barely change the line's shape (Douglas-Peucker).

    Every removed point lies within `tolerance_meters` of the simplified line.
    The first and last points are always kept.
    """
    if len(points) < 3:
        return list(points)

    tolerance = tolerance_meters / METERS_PER_MILE
    reference_lat = sum(lat for lat, _ in points) / len(points)
    xy = [_to_local_xy(p, reference_lat) for p in points]

    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    tolerance_sq = tolerance * tolerance

    while stack:
        start, end = stack.pop()
        (ax, ay), (bx, by) = xy[start], xy[end]
        dx, dy = bx - ax, by - ay
        length_sq = dx * dx + dy * dy
        farthest, max_distance_sq = None, tolerance_sq

        # Squared distance from each point to segment start-end. Inlined: this loop is the hot path.
        for i in range(start + 1, end):
            px, py = xy[i]
            if length_sq == 0:
                ex, ey = px - ax, py - ay
            else:
                t = ((px - ax) * dx + (py - ay) * dy) / length_sq
                t = 0.0 if t < 0 else 1.0 if t > 1 else t
                ex, ey = px - ax - t * dx, py - ay - t * dy
            distance_sq = ex * ex + ey * ey
            if distance_sq > max_distance_sq:
                farthest, max_distance_sq = i, distance_sq
        if farthest is not None:
            keep[farthest] = True
            stack.append((start, farthest))
            stack.append((farthest, end))

    return [point for point, kept in zip(points, keep) if kept]


def offset_point(start, end, sideways, along=0.5):
    """
    A point `along` of the way from start to end (0.5 = midpoint), pushed
    sideways by `sideways` times the start-end distance.

    Positive `sideways` pushes to the left of the direction of travel, negative
    to the right. Used to build via-points for alternative routes.
    """
    reference_lat = (start[0] + end[0]) / 2
    (x1, y1), (x2, y2) = _to_local_xy(start, reference_lat), _to_local_xy(end, reference_lat)
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    if length == 0:
        return start

    # (-dy, dx) is the direction rotated 90 degrees to the left.
    shift = sideways * length
    x = x1 + dx * along - dy / length * shift
    y = y1 + dy * along + dx / length * shift
    return _from_local_xy(x, y, reference_lat)


def resample(points, step_miles):
    """Points every `step_miles` along a line, always including both ends."""
    if len(points) < 2:
        return list(points)
    cumulative = cumulative_distances(points)
    total = cumulative[-1]
    count = max(1, math.ceil(total / step_miles))
    distances = [total * i / count for i in range(count + 1)]
    return [position.point for position in positions_at_distances(points, cumulative, distances)]


class PointIndex:
    """Spatial hash for fast "is any indexed point within R miles of this point?" checks."""

    def __init__(self, points, radius_miles):
        self.radius = radius_miles
        reference_lat = sum(lat for lat, _ in points) / len(points) if points else 0.0
        self.cell_lat = radius_miles / MILES_PER_DEGREE_LAT
        self.cell_lon = radius_miles / (MILES_PER_DEGREE_LAT * max(math.cos(math.radians(reference_lat)), 0.01))
        self.cells = {}
        for point in points:
            self.cells.setdefault(self._cell(point), []).append(point)

    def _cell(self, point):
        return (math.floor(point[0] / self.cell_lat), math.floor(point[1] / self.cell_lon))

    def has_point_near(self, point):
        row, col = self._cell(point)
        for d_row in (-1, 0, 1):
            for d_col in (-1, 0, 1):
                for other in self.cells.get((row + d_row, col + d_col), ()):
                    if haversine_miles(point, other) <= self.radius:
                        return True
        return False


def overlap_fraction(line_a, line_b, tolerance_miles=0.25):
    """Share of line_a's length (0-1) that runs within `tolerance_miles` of line_b."""
    samples_a = resample(line_a, tolerance_miles)
    index_b = PointIndex(resample(line_b, tolerance_miles), tolerance_miles * 1.5)
    if not samples_a:
        return 0.0
    return sum(index_b.has_point_near(point) for point in samples_a) / len(samples_a)


def bounding_box(points, margin_miles=0.0):
    """(min_lat, min_lon, max_lat, max_lon) around the points, grown by a margin on every side."""
    lats = [lat for lat, _ in points]
    lons = [lon for _, lon in points]
    # Use the latitude farthest from the equator so the longitude margin is never too small.
    widest_lat = max(abs(min(lats)), abs(max(lats)))
    lat_margin = margin_miles / MILES_PER_DEGREE_LAT
    lon_margin = margin_miles / (MILES_PER_DEGREE_LAT * max(math.cos(math.radians(widest_lat)), 0.01))
    return (
        max(min(lats) - lat_margin, -90.0),
        min(lons) - lon_margin,
        min(max(lats) + lat_margin, 90.0),
        max(lons) + lon_margin,
    )
