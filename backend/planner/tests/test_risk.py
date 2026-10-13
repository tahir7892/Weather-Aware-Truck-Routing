import pytest

from planner.constants import RiskLevel
from planner.services.risk import (
    WeatherSample,
    assess,
    classify_rain,
    classify_snow,
    classify_wind,
)

LOW, MODERATE, HIGH, SEVERE, NO_TRAVEL = (
    RiskLevel.LOW,
    RiskLevel.MODERATE,
    RiskLevel.HIGH,
    RiskLevel.SEVERE,
    RiskLevel.NO_TRAVEL,
)

LIGHT_LOAD = 10_000


def sample(wind=0.0, rain=0.0, snow=0.0, gust=None):
    return WeatherSample(wind_mph=wind, rain_in_per_hr=rain, snow_in_per_hr=snow, gust_mph=gust)


# --- Wind table (light load, so no load rule applies) -------------------------


@pytest.mark.parametrize(
    "wind, expected",
    [
        (0, LOW),
        (24.9, LOW),
        (25, MODERATE),
        (34.9, MODERATE),
        (35, HIGH),
        (44.9, HIGH),
        (45, SEVERE),
        (54.9, SEVERE),
        (55, NO_TRAVEL),
        (80, NO_TRAVEL),
    ],
)
def test_wind_thresholds(wind, expected):
    level, _ = classify_wind(wind, LIGHT_LOAD)
    assert level == expected


# --- Rain table ----------------------------------------------------------------


@pytest.mark.parametrize(
    "rain, expected",
    [
        (0, LOW),
        (0.09, LOW),
        (0.10, MODERATE),
        (0.24, MODERATE),
        (0.25, HIGH),  # listed in both Moderate and High in the PDF; border goes up
        (0.49, HIGH),
        (0.50, SEVERE),
        (1.00, SEVERE),  # No Travel is strictly "> 1.00"
        (1.01, NO_TRAVEL),
    ],
)
def test_rain_thresholds(rain, expected):
    assert classify_rain(rain) == expected


# --- Snow table ----------------------------------------------------------------


@pytest.mark.parametrize(
    "snow, expected",
    [
        (0, LOW),
        (0.49, LOW),
        (0.5, MODERATE),
        (0.99, MODERATE),
        (1.0, HIGH),
        (1.99, HIGH),
        (2.0, SEVERE),
        (3.0, SEVERE),  # No Travel is strictly "> 3.0"
        (3.01, NO_TRAVEL),
    ],
)
def test_snow_thresholds(snow, expected):
    assert classify_snow(snow) == expected


# --- Load rules ----------------------------------------------------------------


@pytest.mark.parametrize(
    "wind, load, expected",
    [
        # >= 55 mph is No Travel for any load
        (55, 1, NO_TRAVEL),
        (60, 80_000, NO_TRAVEL),
        # 45-54 mph + > 30,000 lb -> No Travel
        (45, 30_000, SEVERE),
        (45, 30_001, NO_TRAVEL),
        (54.9, 30_001, NO_TRAVEL),
        (50, 80_000, NO_TRAVEL),
        # 35-44 mph + > 40,000 lb -> Severe
        (35, 40_000, HIGH),
        (35, 40_001, SEVERE),
        (44.9, 40_001, SEVERE),
        # 35-44 mph between 30,000 and 40,000 lb is not affected by the 45-54 rule
        (40, 35_000, HIGH),
        # Below 35 mph the load does not matter
        (34.9, 80_000, MODERATE),
        (10, 80_000, LOW),
    ],
)
def test_load_rules(wind, load, expected):
    level, _ = classify_wind(wind, load)
    assert level == expected


def test_load_rule_is_reported_when_it_applies():
    _, rule = classify_wind(40, 45_000)
    assert rule is not None and rule.level == SEVERE

    _, rule = classify_wind(40, 20_000)
    assert rule is None


def test_load_rules_only_affect_wind():
    result = assess(sample(wind=10, rain=0.3), load_lb=80_000)
    assert result.level == HIGH
    assert result.wind_level == LOW


# --- Overall level = worst of wind, rain, snow -------------------------------


@pytest.mark.parametrize(
    "wind, rain, snow, expected",
    [
        (0, 0, 0, LOW),
        (30, 0, 0, MODERATE),
        (10, 0.3, 0, HIGH),
        (10, 0, 2.5, SEVERE),
        (30, 0.3, 2.5, SEVERE),
        (10, 1.5, 0.6, NO_TRAVEL),
    ],
)
def test_overall_is_worst_condition(wind, rain, snow, expected):
    assert assess(sample(wind, rain, snow), LIGHT_LOAD).level == expected


def test_heavy_load_wind_beats_lighter_rain():
    result = assess(sample(wind=47, rain=0.3), load_lb=35_000)
    assert result.level == NO_TRAVEL
    assert (result.wind_level, result.rain_level, result.snow_level) == (NO_TRAVEL, HIGH, LOW)


def test_gusts_do_not_change_the_level():
    assert assess(sample(wind=10, gust=70), LIGHT_LOAD).level == LOW


# --- Missing data --------------------------------------------------------------


@pytest.mark.parametrize(
    "weather",
    [
        WeatherSample(wind_mph=None, rain_in_per_hr=0.0, snow_in_per_hr=0.0),
        WeatherSample(wind_mph=10, rain_in_per_hr=None, snow_in_per_hr=0.0),
        WeatherSample(wind_mph=10, rain_in_per_hr=0.0, snow_in_per_hr=None),
        WeatherSample(wind_mph=None, rain_in_per_hr=None, snow_in_per_hr=None),
    ],
)
def test_missing_values_give_no_data_not_low(weather):
    result = assess(weather, LIGHT_LOAD)
    assert result.level is None
    assert not result.has_data
    assert result.score is None
    assert result.label == "No data"


def test_no_data_reason_names_missing_fields():
    result = assess(WeatherSample(wind_mph=None, rain_in_per_hr=0.0, snow_in_per_hr=None), LIGHT_LOAD)
    assert result.reason == "No data: forecast missing wind, snow"


def test_missing_gust_is_fine():
    assert assess(sample(wind=10, gust=None), LIGHT_LOAD).has_data


# --- WeatherSample.from_forecast (Open-Meteo hour -> sample) ------------------


def test_from_forecast_adds_rain_and_showers():
    weather = WeatherSample.from_forecast(
        {"wind_speed_10m": 12.0, "wind_gusts_10m": 30.0, "rain": 0.08, "showers": 0.2, "snowfall": 0.1}
    )
    assert weather.rain_in_per_hr == pytest.approx(0.28)
    assert (weather.wind_mph, weather.gust_mph, weather.snow_in_per_hr) == (12.0, 30.0, 0.1)
    assert assess(weather, LIGHT_LOAD).level == HIGH  # showers push it over 0.25


@pytest.mark.parametrize(
    "rain, showers, expected",
    [(0.3, None, 0.3), (None, 0.3, 0.3), (None, None, None), (0.0, 0.0, 0.0)],
)
def test_from_forecast_missing_rain_parts(rain, showers, expected):
    weather = WeatherSample.from_forecast({"wind_speed_10m": 5.0, "rain": rain, "showers": showers, "snowfall": 0.0})
    assert weather.rain_in_per_hr == expected


def test_from_forecast_empty_hour_is_no_data():
    assert not assess(WeatherSample.from_forecast({}), LIGHT_LOAD).has_data


# --- Label, score and reason --------------------------------------------------


def test_label_and_score():
    result = assess(sample(rain=0.6), LIGHT_LOAD)
    assert result.label == "Severe"
    assert result.score == 3


def test_reason_for_low():
    assert assess(sample(), LIGHT_LOAD).reason == "Low: no significant wind, rain or snow"


def test_reason_names_the_cause():
    assert assess(sample(wind=10, rain=0.31), LIGHT_LOAD).reason == "High: rain 0.31 in/hr"


def test_reason_names_every_cause_at_the_top_level():
    reason = assess(sample(wind=40, rain=0.3, snow=0.2), LIGHT_LOAD).reason
    assert reason == "High: wind 40.0 mph, rain 0.30 in/hr"


def test_reason_mentions_load_rule():
    reason = assess(sample(wind=40), load_lb=45_000).reason
    assert reason == "Severe: wind 40.0 mph with 45,000 lb load (over 40,000 lb)"
