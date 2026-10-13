"""
OpenRouteService truck routing: up to 3 distinct routes between two points.

1. The main (fastest) route and two detour routes are requested in parallel.
   A detour goes through a via-point pushed left or right of the trip's
   midpoint, which makes ORS find a genuinely different road. Via-points are
   snapped to truck roads first, so they never sit in empty desert or sea.
2. Detours that mostly follow an existing route, or take far longer than the
   main route, are dropped. If fewer than 3 routes remain, wider detours are
   tried (all at once).

ORS's built-in "alternative routes" are not used: on the free API they only
work for trips under ~100 km, take ~10 s, and often return near-duplicates.

The truck's gross weight is sent to ORS so it avoids weight-restricted roads.
If no route respects that weight, routes without the restriction are returned
with a warning.
"""

import logging
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from django.conf import settings
from django.core.cache import cache

from planner.clients.http import fetch_json, make_cache_key, ors_headers
from planner.constants import (
    CACHE_TTL_ROUTE,
    DETOUR_OFFSET_FRACTIONS,
    EMPTY_TRUCK_WEIGHT_LB,
    KG_PER_LB,
    MAX_DETOUR_DURATION_FACTOR,
    METERS_PER_MILE,
    ORS_PROFILE,
    ORS_SNAP_RADIUS_METERS,
    ROUTE_COUNT,
    ROUTE_SIMILARITY_THRESHOLD,
    VIA_CANDIDATE_SHAPES,
    VIA_LABEL_MIN_SHARE,
)
from planner.exceptions import NoRouteFound, PlannerError, ServiceUnavailable
from planner.utils.geo import decode_polyline, offset_point, overlap_fraction

logger = logging.getLogger(__name__)

SERVICE = "routing"

# ORS error codes (https://giscience.github.io/openrouteservice/api-reference/error-codes)
ORS_LIMITS_EXCEEDED = 2004
ORS_ROUTE_NOT_FOUND = 2009
ORS_POINT_NOT_FOUND = 2010

# Interstate and US highway names, e.g. "I 65", "US 41".
HIGHWAY_NAME = re.compile(r"^(I|US)[ -]?\d+[A-Z]?$")


@dataclass(frozen=True)
class Route:
    points: tuple  # full route line as (lat, lon) points
    distance_miles: float
    duration_seconds: float
    step_timings: tuple  # (start_index, end_index, duration_seconds) per ORS step
    via: str  # main roads, e.g. "I-65 / I-94"


@dataclass
class RoutingResult:
    routes: list
    warnings: list = field(default_factory=list)


class OrsError(Exception):
    """An ORS 4xx answer; the caller decides what it means for the user."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


# --- Public entry point --------------------------------------------------------


def get_routes(origin, destination, load_lb):
    """Up to ROUTE_COUNT distinct truck routes between (lat, lon) points, main route first."""
    key = make_cache_key("routes", _rounded(origin), _rounded(destination), round(load_lb))
    result = cache.get(key)
    if result is not None:
        return result

    warnings = []
    try:
        routes = find_routes(origin, destination, gross_weight_tonnes(load_lb))
    except OrsError as exc:
        if exc.code != ORS_ROUTE_NOT_FOUND:
            raise _user_error(exc)
        # Retry without the weight limit: the trip may only be possible on restricted roads.
        try:
            routes = find_routes(origin, destination, None)
        except OrsError as retry_exc:
            raise _user_error(retry_exc)
        warnings.append("No route respects the truck's gross weight limits; showing routes without weight restrictions.")

    if len(routes) < ROUTE_COUNT:
        warnings.append(f"Only {len(routes)} distinct route(s) could be found for this trip.")

    result = RoutingResult(routes=routes, warnings=warnings)
    cache.set(key, result, CACHE_TTL_ROUTE)
    return result


def gross_weight_tonnes(load_lb):
    return (EMPTY_TRUCK_WEIGHT_LB + load_lb) * KG_PER_LB / 1000


def _rounded(point):
    return (round(point[0], 5), round(point[1], 5))


def _user_error(exc):
    """Turn an ORS error into an error the user can understand."""
    if exc.code == ORS_POINT_NOT_FOUND:
        return NoRouteFound("The origin or destination is not near a road trucks can use.")
    if exc.code == ORS_LIMITS_EXCEEDED:
        return NoRouteFound("This trip is too long for the routing service.")
    if exc.code == ORS_ROUTE_NOT_FOUND:
        return NoRouteFound()
    logger.warning("ORS error %s: %s", exc.code, exc.message)
    return ServiceUnavailable("The routing service could not process this trip.")


# --- Finding distinct routes ---------------------------------------------------


def find_routes(origin, destination, weight_tonnes):
    """
    Main route plus detours. Raises OrsError if the main route fails; failed
    detours are simply skipped.

    Round 1 (in parallel): the main route, snapping the via-points, then the
    two narrowest detours. Round 2 (only if needed): all wider detours at once.
    """
    with ThreadPoolExecutor(max_workers=4) as pool:
        main_future = pool.submit(request_routes, [origin, destination], weight_tonnes)
        vias = detour_vias(origin, destination)

        def detour(via):
            return detour_route(origin, destination, weight_tonnes, via)

        first_detours = [pool.submit(detour, via) for via in vias[:2]]
        main = main_future.result()
        if not main:
            raise OrsError(ORS_ROUTE_NOT_FOUND, "No route returned.")
        routes = add_distinct(main[:1], [future.result() for future in first_detours])

        if len(routes) < ROUTE_COUNT and len(vias) > 2:
            routes = add_distinct(routes, list(pool.map(detour, vias[2:])))

    return routes


def detour_vias(origin, destination):
    """
    One via-point per DETOUR_OFFSET_FRACTIONS entry, on a truck road when possible.

    Several candidate spots around each ideal via-point are snapped to the road
    network in a single request; the first candidate that reaches a road wins.
    If snapping is unavailable, the ideal (unsnapped) points are used. A via is
    None when no candidate reached a road (e.g. all of them are at sea).
    """
    groups = [
        [offset_point(origin, destination, fraction * scale, along) for along, scale in VIA_CANDIDATE_SHAPES]
        for fraction in DETOUR_OFFSET_FRACTIONS
    ]
    snapped = snap_points([point for group in groups for point in group])
    if snapped is None:
        return [group[0] for group in groups]

    vias = []
    for i, group in enumerate(groups):
        group_snapped = snapped[i * len(group) : (i + 1) * len(group)]
        vias.append(next((point for point in group_snapped if point is not None), None))
    return vias


def snap_points(points):
    """Nearest truck-road point for each (lat, lon), None where no road is near. None if the call fails."""
    try:
        status, data = fetch_json(
            "POST",
            f"{settings.ORS_BASE_URL}/v2/snap/{ORS_PROFILE}",
            service=SERVICE,
            headers={**ors_headers(), "Content-Type": "application/json"},
            json={"locations": [[lon, lat] for lat, lon in points], "radius": ORS_SNAP_RADIUS_METERS},
        )
    except PlannerError as exc:
        logger.info("Snapping via-points failed: %s", exc)
        return None
    locations = data.get("locations") if status == 200 and isinstance(data, dict) else None
    if not isinstance(locations, list) or len(locations) != len(points):
        logger.info("Snapping via-points returned HTTP %s; using unsnapped points.", status)
        return None
    return [(loc["location"][1], loc["location"][0]) if loc else None for loc in locations]


def detour_route(origin, destination, weight_tonnes, via):
    """A route forced through `via`, or None if there is no via or ORS can't make the route."""
    if via is None:
        return None
    try:
        routes = request_routes([origin, via, destination], weight_tonnes)
    except (OrsError, PlannerError) as exc:
        logger.info("Detour via %s skipped: %s", via, exc)
        return None
    return routes[0] if routes else None


def is_distinct(route, others):
    """True if `route` does not mostly follow the same roads as any of `others`."""
    for other in others:
        shared = max(overlap_fraction(route.points, other.points), overlap_fraction(other.points, route.points))
        if shared > ROUTE_SIMILARITY_THRESHOLD:
            return False
    return True


def add_distinct(routes, candidates):
    """Add candidates that are distinct and not much slower than the main route, up to ROUTE_COUNT."""
    routes = list(routes)
    max_duration = routes[0].duration_seconds * MAX_DETOUR_DURATION_FACTOR
    for candidate in candidates:
        if len(routes) >= ROUTE_COUNT:
            break
        if candidate is not None and candidate.duration_seconds <= max_duration and is_distinct(candidate, routes):
            routes.append(candidate)
    return routes


# --- One ORS request -----------------------------------------------------------


def request_routes(coordinates, weight_tonnes=None):
    """One ORS directions call through (lat, lon) `coordinates`. Raises OrsError on a 4xx answer."""
    options = {"vehicle_type": "hgv"}
    if weight_tonnes is not None:
        options["profile_params"] = {"restrictions": {"weight": round(weight_tonnes, 1)}}

    # Via-points (everything but the ends) may snap to a road at any distance.
    radiuses = [ORS_SNAP_RADIUS_METERS] + [-1] * (len(coordinates) - 2) + [ORS_SNAP_RADIUS_METERS]
    body = {
        "coordinates": [[lon, lat] for lat, lon in coordinates],
        "instructions": True,
        "geometry": True,
        "radiuses": radiuses,
        "options": options,
    }

    status, data = fetch_json(
        "POST",
        f"{settings.ORS_BASE_URL}/v2/directions/{ORS_PROFILE}",
        service=SERVICE,
        headers={**ors_headers(), "Content-Type": "application/json"},
        json=body,
    )
    if status != 200:
        error = data.get("error", {}) if isinstance(data, dict) else {}
        if isinstance(error, dict):
            raise OrsError(error.get("code"), error.get("message", "Unknown routing error"))
        raise OrsError(None, str(error))

    return [parse_route(route) for route in data.get("routes", [])]


def parse_route(data):
    """Turn one ORS route object into a Route."""
    points = tuple(decode_polyline(data["geometry"]))
    steps = [step for segment in data.get("segments", []) for step in segment.get("steps", [])]
    summary = data.get("summary", {})
    return Route(
        points=points,
        distance_miles=summary.get("distance", 0.0) / METERS_PER_MILE,
        duration_seconds=summary.get("duration", 0.0),
        step_timings=tuple((s["way_points"][0], s["way_points"][1], s["duration"]) for s in steps),
        via=via_label(steps),
    )


def via_label(steps, count=2):
    """
    The main roads of a route by distance, e.g. "I-65 / I-94".

    Only roads covering at least VIA_LABEL_MIN_SHARE of the route are named
    (ORS leaves some highway stretches unnamed, so a short named piece must not
    become the label). Interstates and US highways are preferred.
    """
    total = sum(step.get("distance", 0.0) for step in steps)
    by_name = defaultdict(float)
    for step in steps:
        for name in (step.get("name") or "").split(","):
            name = name.strip()
            if name and name != "-":
                by_name[name] += step.get("distance", 0.0)
    by_name = {name: d for name, d in by_name.items() if total and d / total >= VIA_LABEL_MIN_SHARE}

    highways = {name: d for name, d in by_name.items() if HIGHWAY_NAME.match(name)}
    pool = highways or by_name
    top = sorted(pool, key=pool.get, reverse=True)[:count]
    return " / ".join(name.replace(" ", "-") if name in highways else name for name in top)
