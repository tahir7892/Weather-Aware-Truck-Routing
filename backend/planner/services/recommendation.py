"""
Route risk summaries and the best-route choice.

Checkpoints are points, but the PDF ranks routes by miles. The road between two
neighbouring checkpoints is one stretch, and it takes the worse level of its
two ends. If one end has no weather data, the other end's level is used; if
neither has data, the stretch counts as "No data".

Routes are ranked strictly in this order (a later rule only breaks ties):
  0. Fewest No Travel miles (any No Travel puts a route below all others)
  1. Fewest Severe miles
  2. Fewest High miles
  3. Lowest average risk (0-4 score weighted by miles)
  4. Shortest travel time
"""

import math
from dataclasses import dataclass, field

from planner.constants import NO_DATA_LABEL, RISK_LABELS, RiskLevel

MILES_BY_LEVEL_KEYS = [*RISK_LABELS.values(), NO_DATA_LABEL]


def _checkpoint_level(checkpoint):
    return checkpoint.risk.level if checkpoint.risk is not None else None


def stretch_level(start_level, end_level):
    """The worse of two levels, ignoring missing ones. None if both are missing."""
    known = [level for level in (start_level, end_level) if level is not None]
    return max(known) if known else None


@dataclass
class RouteRiskSummary:
    distance_miles: float
    duration_seconds: float
    miles_by_level: dict = field(default_factory=dict)
    average_risk: float | None = None
    max_level: RiskLevel | None = None

    @property
    def no_travel_miles(self):
        return self.miles_by_level[RiskLevel.NO_TRAVEL.label]

    @property
    def severe_miles(self):
        return self.miles_by_level[RiskLevel.SEVERE.label]

    @property
    def high_miles(self):
        return self.miles_by_level[RiskLevel.HIGH.label]

    @property
    def no_data_miles(self):
        return self.miles_by_level[NO_DATA_LABEL]


def summarize_route(checkpoints, duration_seconds):
    """Miles at each level, average risk and worst level for one route."""
    miles_by_level = {key: 0.0 for key in MILES_BY_LEVEL_KEYS}
    weighted_score = 0.0
    known_miles = 0.0

    for start, end in zip(checkpoints, checkpoints[1:]):
        length = end.mile - start.mile
        level = stretch_level(_checkpoint_level(start), _checkpoint_level(end))
        if level is None:
            miles_by_level[NO_DATA_LABEL] += length
        else:
            miles_by_level[level.label] += length
            weighted_score += int(level) * length
            known_miles += length

    known_levels = [lvl for lvl in map(_checkpoint_level, checkpoints) if lvl is not None]
    return RouteRiskSummary(
        distance_miles=checkpoints[-1].mile if checkpoints else 0.0,
        duration_seconds=duration_seconds,
        miles_by_level=miles_by_level,
        average_risk=weighted_score / known_miles if known_miles > 0 else None,
        max_level=max(known_levels) if known_levels else None,
    )


# --- Ranking -----------------------------------------------------------------


def format_duration(seconds):
    minutes = round(seconds / 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes:02d} min" if hours else f"{minutes} min"


@dataclass(frozen=True)
class _Criterion:
    key: object  # summary -> comparable number (rounded so float noise never decides)
    describe: object  # (best value, other value) -> short reason text


def _miles_reason(label):
    return lambda best, other: f"fewer {label} miles ({best:.1f} vs {other:.1f})"


CRITERIA = (
    _Criterion(lambda s: round(s.no_travel_miles, 1), _miles_reason("No Travel")),
    _Criterion(lambda s: round(s.severe_miles, 1), _miles_reason("Severe")),
    _Criterion(lambda s: round(s.high_miles, 1), _miles_reason("High")),
    _Criterion(
        # Routes with no weather data at all rank last on this rule.
        lambda s: round(s.average_risk, 3) if s.average_risk is not None else math.inf,
        lambda best, other: f"lower average risk ({best:.2f} vs {other:.2f})"
        if other != math.inf
        else "it has weather data",
    ),
    _Criterion(
        lambda s: round(s.duration_seconds),
        lambda best, other: f"shorter travel time ({format_duration(best)} vs {format_duration(other)})",
    ),
)


def ranking_key(summary):
    return tuple(criterion.key(summary) for criterion in CRITERIA)


@dataclass
class Recommendation:
    route_id: str
    ranking: list
    reason: str
    warnings: list = field(default_factory=list)


def recommend(summaries):
    """
    Pick the best route.

    `summaries` maps route id -> RouteRiskSummary, in the order the routes were
    found. Ties keep that order, so the main route wins a full tie.
    """
    if not summaries:
        raise ValueError("At least one route is needed.")

    ranking = sorted(summaries, key=lambda route_id: ranking_key(summaries[route_id]))
    best_id = ranking[0]

    return Recommendation(
        route_id=best_id,
        ranking=ranking,
        reason=_explain(best_id, ranking, summaries),
        warnings=_warnings(best_id, summaries),
    )


def _explain(best_id, ranking, summaries):
    best = summaries[best_id]
    if len(ranking) == 1:
        return f"Route {best_id} is the only route found."

    comparisons = []
    for other_id in ranking[1:]:
        other = summaries[other_id]
        for criterion in CRITERIA:
            best_value, other_value = criterion.key(best), criterion.key(other)
            if best_value != other_value:
                comparisons.append(f"vs Route {other_id}: {criterion.describe(best_value, other_value)}")
                break
        else:
            comparisons.append(f"vs Route {other_id}: same risk and travel time")

    reason = f"Route {best_id} is recommended ({'; '.join(comparisons)})."

    fastest = min(summary.duration_seconds for summary in summaries.values())
    extra = best.duration_seconds - fastest
    if extra >= 60:
        reason += f" It takes {format_duration(extra)} longer than the fastest route, but has lower weather risk."
    return reason


def _warnings(best_id, summaries):
    warnings = []
    best = summaries[best_id]

    if all(summary.no_travel_miles > 0 for summary in summaries.values()):
        warnings.append(
            "No route is safe at this departure time: every route has No Travel conditions. "
            "Consider changing the departure time."
        )
    elif best.severe_miles > 0:
        warnings.append(f"The recommended route still has {best.severe_miles:.1f} Severe miles.")

    for route_id, summary in summaries.items():
        if summary.no_data_miles > 0:
            warnings.append(f"Weather data was missing for {summary.no_data_miles:.1f} miles of Route {route_id}.")

    return warnings
