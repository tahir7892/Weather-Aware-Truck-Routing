from datetime import datetime, timezone

import pytest

from planner.constants import RiskLevel
from planner.services.checkpoints import Checkpoint
from planner.services.recommendation import (
    RouteRiskSummary,
    format_duration,
    recommend,
    stretch_level,
    summarize_route,
)
from planner.services.risk import RiskAssessment

LOW, MODERATE, HIGH, SEVERE, NO_TRAVEL = (
    RiskLevel.LOW,
    RiskLevel.MODERATE,
    RiskLevel.HIGH,
    RiskLevel.SEVERE,
    RiskLevel.NO_TRAVEL,
)
NOW = datetime(2026, 10, 12, 8, 0, tzinfo=timezone.utc)
HOUR = 3600


def make_checkpoints(levels, interval=10):
    """Checkpoints every `interval` miles with the given levels (None = no data)."""
    checkpoints = []
    for index, level in enumerate(levels):
        risk = RiskAssessment(level=level, wind_level=None, rain_level=None, snow_level=None, reason="")
        checkpoints.append(Checkpoint(index=index, lat=0, lon=0, mile=index * interval, eta=NOW, risk=risk))
    return checkpoints


def summary(no_travel=0.0, severe=0.0, high=0.0, average=0.0, hours=4.0, no_data=0.0):
    return RouteRiskSummary(
        distance_miles=100,
        duration_seconds=hours * HOUR,
        miles_by_level={
            "Low": 0.0,
            "Moderate": 0.0,
            "High": high,
            "Severe": severe,
            "No Travel": no_travel,
            "No data": no_data,
        },
        average_risk=average,
        max_level=None,
    )


# --- stretch_level -------------------------------------------------------------


@pytest.mark.parametrize(
    "start, end, expected",
    [
        (LOW, LOW, LOW),
        (LOW, SEVERE, SEVERE),
        (HIGH, MODERATE, HIGH),
        (None, HIGH, HIGH),
        (MODERATE, None, MODERATE),
        (None, None, None),
    ],
)
def test_stretch_takes_worse_end(start, end, expected):
    assert stretch_level(start, end) == expected


# --- summarize_route -----------------------------------------------------------


def test_summary_counts_miles_per_level():
    # Stretches: L-L, L-H, H-L, L-L  -> Low 20, High 20
    result = summarize_route(make_checkpoints([LOW, LOW, HIGH, LOW, LOW]), duration_seconds=HOUR)
    assert result.miles_by_level["Low"] == 20
    assert result.miles_by_level["High"] == 20
    assert result.distance_miles == 40
    assert sum(result.miles_by_level.values()) == pytest.approx(result.distance_miles)


def test_summary_average_risk_is_weighted_by_miles():
    checkpoints = make_checkpoints([LOW, LOW, SEVERE])
    checkpoints[1].mile = 30  # stretch 1 is 30 mi Low, stretch 2 is 10 mi Severe
    checkpoints[2].mile = 40
    result = summarize_route(checkpoints, duration_seconds=HOUR)
    assert result.average_risk == pytest.approx((0 * 30 + 3 * 10) / 40)


def test_summary_max_level():
    result = summarize_route(make_checkpoints([LOW, SEVERE, MODERATE]), duration_seconds=HOUR)
    assert result.max_level == SEVERE


def test_summary_no_data_stretches():
    result = summarize_route(make_checkpoints([None, None, HIGH]), duration_seconds=HOUR)
    assert result.no_data_miles == 10
    assert result.high_miles == 10
    # Average only counts miles with data.
    assert result.average_risk == pytest.approx(2.0)


def test_summary_all_no_data():
    result = summarize_route(make_checkpoints([None, None]), duration_seconds=HOUR)
    assert result.average_risk is None
    assert result.max_level is None
    assert result.no_data_miles == 10


def test_summary_last_stretch_can_be_shorter():
    checkpoints = make_checkpoints([LOW, LOW, NO_TRAVEL])
    checkpoints[2].mile = 13  # last stretch is 3 miles
    result = summarize_route(checkpoints, duration_seconds=HOUR)
    assert result.no_travel_miles == pytest.approx(3)
    assert result.distance_miles == 13


# --- Ranking rules, each one in order ------------------------------------------


def test_rule_1_fewest_severe_miles_wins_over_everything_after_it():
    result = recommend(
        {
            "A": summary(severe=10, high=0, average=0.5, hours=3),
            "B": summary(severe=0, high=50, average=2.0, hours=6),
        }
    )
    assert result.route_id == "B"


def test_rule_2_fewest_high_miles_breaks_severe_tie():
    result = recommend(
        {
            "A": summary(severe=5, high=30, average=0.5, hours=3),
            "B": summary(severe=5, high=10, average=1.5, hours=5),
        }
    )
    assert result.route_id == "B"


def test_rule_3_lowest_average_risk_breaks_high_tie():
    result = recommend(
        {
            "A": summary(severe=0, high=10, average=1.2, hours=3),
            "B": summary(severe=0, high=10, average=0.8, hours=4),
        }
    )
    assert result.route_id == "B"


def test_rule_4_shortest_time_breaks_full_risk_tie():
    result = recommend(
        {
            "A": summary(average=0.5, hours=5),
            "B": summary(average=0.5, hours=4),
        }
    )
    assert result.route_id == "B"


def test_no_travel_ranks_below_any_severe_route():
    result = recommend(
        {
            "A": summary(no_travel=1, severe=0, hours=3),
            "B": summary(no_travel=0, severe=80, high=80, average=3, hours=9),
        }
    )
    assert result.route_id == "B"
    assert result.ranking == ["B", "A"]


def test_fewer_no_travel_miles_wins_when_all_have_some():
    result = recommend(
        {
            "A": summary(no_travel=20),
            "B": summary(no_travel=5, severe=40),
        }
    )
    assert result.route_id == "B"


def test_route_without_any_weather_data_ranks_below_route_with_data():
    no_data = summary(no_data=100)
    no_data.average_risk = None
    result = recommend({"A": no_data, "B": summary(average=1.5, hours=6)})
    assert result.route_id == "B"


def test_full_tie_keeps_original_order():
    result = recommend({"A": summary(), "B": summary(), "C": summary()})
    assert result.ranking == ["A", "B", "C"]


def test_tiny_float_differences_do_not_decide():
    result = recommend(
        {
            "A": summary(severe=10.00001, hours=3),
            "B": summary(severe=10.0, hours=4),
        }
    )
    assert result.route_id == "A"  # Severe miles tie after rounding; A is faster


def test_full_ranking_of_three_routes():
    result = recommend(
        {
            "A": summary(severe=10),
            "B": summary(high=10),
            "C": summary(average=0.2),
        }
    )
    assert result.ranking == ["C", "B", "A"]


def test_recommend_needs_routes():
    with pytest.raises(ValueError):
        recommend({})


# --- Reason text -------------------------------------------------------------


def test_reason_names_the_deciding_rule_per_route():
    result = recommend(
        {
            "A": summary(severe=40, hours=4),
            "B": summary(severe=0, high=10, hours=4.25),
            "C": summary(severe=0, high=25, hours=4),
        }
    )
    assert result.reason.startswith("Route B is recommended (")
    assert "vs Route C: fewer High miles (10.0 vs 25.0)" in result.reason
    assert "vs Route A: fewer Severe miles (0.0 vs 40.0)" in result.reason
    assert "It takes 15 min longer than the fastest route" in result.reason


def test_reason_for_time_tiebreak():
    result = recommend({"A": summary(hours=5), "B": summary(hours=4.5)})
    assert "shorter travel time (4 h 30 min vs 5 h 00 min)" in result.reason
    assert "longer than the fastest" not in result.reason


def test_reason_for_full_tie():
    assert "same risk and travel time" in recommend({"A": summary(), "B": summary()}).reason


def test_reason_for_single_route():
    assert recommend({"A": summary()}).reason == "Route A is the only route found."


# --- Warnings ----------------------------------------------------------------


def test_warning_when_every_route_has_no_travel():
    result = recommend({"A": summary(no_travel=5), "B": summary(no_travel=1)})
    assert any("No route is safe" in w for w in result.warnings)


def test_warning_when_best_route_still_has_severe_miles():
    result = recommend({"A": summary(severe=12.5), "B": summary(severe=20)})
    assert "The recommended route still has 12.5 Severe miles." in result.warnings


def test_warning_for_missing_weather():
    result = recommend({"A": summary(no_data=7), "B": summary()})
    assert "Weather data was missing for 7.0 miles of Route A." in result.warnings


def test_no_warnings_for_a_clean_trip():
    assert recommend({"A": summary(), "B": summary(high=5)}).warnings == []


# --- format_duration ---------------------------------------------------------


@pytest.mark.parametrize("seconds, text", [(59 * 60, "59 min"), (3600, "1 h 00 min"), (4 * 3600 + 5 * 60, "4 h 05 min")])
def test_format_duration(seconds, text):
    assert format_duration(seconds) == text
