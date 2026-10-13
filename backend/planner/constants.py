"""
The rule book: every fixed number the app uses, kept in one place.

The risk thresholds and load rules come straight from the assessment PDF.
Everything else (limits, cache times, sizes) is a tuning value chosen by us.
"""

from dataclasses import dataclass
from enum import IntEnum


# --- Risk levels --------------------------------------------------------------


class RiskLevel(IntEnum):
    """Risk levels in order. The integer value is also the risk score (0-4)."""

    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4

    @property
    def label(self):
        return RISK_LABELS[self]


RISK_LABELS = {
    RiskLevel.LOW: "Low",
    RiskLevel.MODERATE: "Moderate",
    RiskLevel.HIGH: "High",
    RiskLevel.SEVERE: "Severe",
    RiskLevel.NO_TRAVEL: "No Travel",
}

# Shown when the weather API returned no value for a checkpoint. It is not a
# risk level and is never counted as Low.
NO_DATA_LABEL = "No data"


# --- Weather thresholds (PDF "Risk Rules" table) ------------------------------


@dataclass(frozen=True)
class Threshold:
    """A value at or above `value` (or strictly above, if not inclusive) reaches `level`."""

    level: RiskLevel
    value: float
    inclusive: bool = True

    def is_reached(self, measurement):
        return measurement >= self.value if self.inclusive else measurement > self.value


# Each list is ordered from the most to the least dangerous level. The first
# threshold reached wins; if none is reached the level is Low.
#
# Border values go to the higher level (e.g. 25 mph is Moderate, 0.25 in/hr of
# rain is High). The PDF uses ">" for No Travel rain and snow, so those are
# strict: exactly 1.00 in/hr of rain is still Severe.

WIND_THRESHOLDS_MPH = (
    Threshold(RiskLevel.NO_TRAVEL, 55),
    Threshold(RiskLevel.SEVERE, 45),
    Threshold(RiskLevel.HIGH, 35),
    Threshold(RiskLevel.MODERATE, 25),
)

RAIN_THRESHOLDS_IN_PER_HR = (
    Threshold(RiskLevel.NO_TRAVEL, 1.00, inclusive=False),
    Threshold(RiskLevel.SEVERE, 0.50),
    Threshold(RiskLevel.HIGH, 0.25),
    Threshold(RiskLevel.MODERATE, 0.10),
)

SNOW_THRESHOLDS_IN_PER_HR = (
    Threshold(RiskLevel.NO_TRAVEL, 3.0, inclusive=False),
    Threshold(RiskLevel.SEVERE, 2.0),
    Threshold(RiskLevel.HIGH, 1.0),
    Threshold(RiskLevel.MODERATE, 0.5),
)


# --- Load rules (PDF "Load rules") ------------------------------------------


@dataclass(frozen=True)
class LoadRule:
    """Wind in [wind_min, wind_max) with a load strictly above `weight_over_lb` becomes `level`."""

    wind_min_mph: float
    wind_max_mph: float
    weight_over_lb: float
    level: RiskLevel

    def applies(self, wind_mph, load_lb):
        return self.wind_min_mph <= wind_mph < self.wind_max_mph and load_lb > self.weight_over_lb


# ">=55 mph -> No Travel for any load" is already covered by WIND_THRESHOLDS_MPH.
LOAD_RULES = (
    LoadRule(wind_min_mph=45, wind_max_mph=55, weight_over_lb=30_000, level=RiskLevel.NO_TRAVEL),
    LoadRule(wind_min_mph=35, wind_max_mph=45, weight_over_lb=40_000, level=RiskLevel.SEVERE),
)


# --- Trip input limits -------------------------------------------------------

CHECKPOINT_INTERVALS_MILES = (10, 25, 50)
DEFAULT_CHECKPOINT_INTERVAL_MILES = 25

MIN_LOAD_WEIGHT_LB = 1
MAX_LOAD_WEIGHT_LB = 150_000

# Weather forecasts only reach so far ahead, so departures are limited.
MAX_DEPARTURE_DAYS_AHEAD = 7
# Allows "leave now" even if the form was filled in a few minutes ago.
DEPARTURE_PAST_TOLERANCE_MINUTES = 30


# --- Units -------------------------------------------------------------------

METERS_PER_MILE = 1609.344
KG_PER_LB = 0.45359237
EARTH_RADIUS_MILES = 3958.8


# --- Routing (OpenRouteService) ----------------------------------------------

ROUTE_COUNT = 3
ORS_PROFILE = "driving-hgv"

# Map coordinates must be within this distance of a road to be routable.
ORS_SNAP_RADIUS_METERS = 5000

# Each detour via-point is chosen from these candidate spots, in order of
# preference: (position along the trip, multiplier of the sideways offset).
# All candidates are snapped to truck roads in one request and the first one
# that lands on a road is used, so via-points in empty desert or sea are avoided.
VIA_CANDIDATE_SHAPES = ((0.5, 1.0), (0.4, 1.0), (0.6, 1.0), (0.5, 0.7), (0.5, 1.3), (0.35, 0.8), (0.65, 0.8))

# A road is named in a route's "via" label only if it covers this share of the route.
VIA_LABEL_MIN_SHARE = 0.10

# Detour routes taking longer than this many times the main route are dropped.
MAX_DETOUR_DURATION_FACTOR = 1.5

# Alternative routes: the via-point is pushed sideways from the trip's midpoint
# by this fraction of the straight-line distance. Tried in left/right pairs; a
# wider pair is only tried if the narrower ones did not give 3 distinct routes
# (e.g. on coastal trips, where one side lands in the sea).
DETOUR_OFFSET_FRACTIONS = (0.15, -0.15, 0.30, -0.30, 0.45, -0.45)

# Two routes sharing more than this fraction of their path are treated as the same.
ROUTE_SIMILARITY_THRESHOLD = 0.85

# Assumed empty tractor-trailer weight. ORS gets the gross weight
# (truck + load) so it can avoid roads with weight limits.
EMPTY_TRUCK_WEIGHT_LB = 35_000

# Route lines sent to the frontend are simplified to this tolerance.
ROUTE_SIMPLIFY_TOLERANCE_METERS = 30

ROUTE_LABELS = ("A", "B", "C")


# --- Geocoding ---------------------------------------------------------------

GEOCODE_COUNTRIES = ("US",)
GEOCODE_MAX_SUGGESTIONS = 5
GEOCODE_MIN_QUERY_LENGTH = 3


# --- Weather (Open-Meteo) ----------------------------------------------------

# Rain is the sum of steady rain and showers (thunderstorm-type rain).
WEATHER_HOURLY_VARIABLES = (
    "wind_speed_10m",
    "wind_gusts_10m",
    "rain",
    "showers",
    "snowfall",
)

# Locations per Open-Meteo request, and how many requests run at the same time.
WEATHER_BATCH_SIZE = 100
WEATHER_MAX_PARALLEL_REQUESTS = 4

# Coordinates are rounded to 1 decimal (~0.1 degree, about 5-7 miles) so nearby
# points share one weather lookup.
WEATHER_COORD_DECIMALS = 1

# Open-Meteo rejects hours beyond ~15 days ahead, so requests stop there and
# later hours are reported as "No data".
WEATHER_MAX_FORECAST_DAYS = 15


# --- Heatmap -----------------------------------------------------------------

HEATMAP_HOURS = 48  # Slider runs from hour 0 (departure) to hour 48.
HEATMAP_CORRIDOR_MILES = 30
HEATMAP_MAX_POINTS = 250


# --- Cache lifetimes (seconds) -----------------------------------------------

CACHE_TTL_GEOCODE = 24 * 60 * 60
CACHE_TTL_ROUTE = 60 * 60
CACHE_TTL_WEATHER = 30 * 60
CACHE_TTL_TRIP = 60 * 60
