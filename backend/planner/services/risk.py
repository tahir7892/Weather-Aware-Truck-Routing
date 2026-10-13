"""
Weather risk for one place at one moment.

Rules (from the assessment PDF, numbers live in planner.constants):
1. Wind, rain and snow are each rated with their own threshold table.
2. Load rules can raise the wind rating for heavy trucks.
3. The overall level is the worst of the three ratings.

Missing weather values are never treated as Low: if wind, rain or snow is
missing, the result is "No data".
"""

from dataclasses import dataclass

from planner.constants import (
    LOAD_RULES,
    NO_DATA_LABEL,
    RAIN_THRESHOLDS_IN_PER_HR,
    SNOW_THRESHOLDS_IN_PER_HR,
    WIND_THRESHOLDS_MPH,
    RiskLevel,
)


@dataclass(frozen=True)
class WeatherSample:
    """Weather at one place and hour. Any value can be None if the API had no data."""

    wind_mph: float | None
    rain_in_per_hr: float | None  # steady rain + showers
    snow_in_per_hr: float | None
    gust_mph: float | None = None  # shown to the user only, not used in the rules

    @property
    def is_complete(self):
        return None not in (self.wind_mph, self.rain_in_per_hr, self.snow_in_per_hr)

    @classmethod
    def from_forecast(cls, values):
        """
        Build a sample from one hour of Open-Meteo values.

        Rain is steady rain plus showers. Some weather models leave one of the
        two empty, so a missing part counts as 0 unless both are missing.
        """
        rain, showers = values.get("rain"), values.get("showers")
        total_rain = None if rain is None and showers is None else (rain or 0.0) + (showers or 0.0)
        return cls(
            wind_mph=values.get("wind_speed_10m"),
            rain_in_per_hr=total_rain,
            snow_in_per_hr=values.get("snowfall"),
            gust_mph=values.get("wind_gusts_10m"),
        )

    def to_dict(self):
        return {
            "wind_mph": _round(self.wind_mph, 1),
            "gust_mph": _round(self.gust_mph, 1),
            "rain_in_per_hr": _round(self.rain_in_per_hr, 3),
            "snow_in_per_hr": _round(self.snow_in_per_hr, 3),
        }


def _round(value, digits):
    return round(value, digits) if value is not None else None


@dataclass(frozen=True)
class RiskAssessment:
    """The result of rating one WeatherSample. `level` is None when data is missing."""

    level: RiskLevel | None
    wind_level: RiskLevel | None
    rain_level: RiskLevel | None
    snow_level: RiskLevel | None
    reason: str

    @property
    def has_data(self):
        return self.level is not None

    @property
    def label(self):
        return self.level.label if self.has_data else NO_DATA_LABEL

    @property
    def score(self):
        return int(self.level) if self.has_data else None

    def to_dict(self):
        def label(level):
            return level.label if level is not None else None

        return {
            "level": self.label,
            "score": self.score,
            "wind": label(self.wind_level),
            "rain": label(self.rain_level),
            "snow": label(self.snow_level),
            "reason": self.reason,
        }


def level_from_thresholds(value, thresholds):
    """Return the first (most dangerous) level whose threshold the value reaches."""
    for threshold in thresholds:
        if threshold.is_reached(value):
            return threshold.level
    return RiskLevel.LOW


def classify_wind(wind_mph, load_lb):
    """Rate wind, then apply the load rules. Returns (level, load rule that applied or None)."""
    level = level_from_thresholds(wind_mph, WIND_THRESHOLDS_MPH)
    for rule in LOAD_RULES:
        if rule.applies(wind_mph, load_lb) and rule.level > level:
            return rule.level, rule
    return level, None


def classify_rain(rain_in_per_hr):
    return level_from_thresholds(rain_in_per_hr, RAIN_THRESHOLDS_IN_PER_HR)


def classify_snow(snow_in_per_hr):
    return level_from_thresholds(snow_in_per_hr, SNOW_THRESHOLDS_IN_PER_HR)


def assess(sample, load_lb):
    """Rate a weather sample for a truck carrying `load_lb` pounds."""
    if not sample.is_complete:
        missing = [
            name
            for name, value in (
                ("wind", sample.wind_mph),
                ("rain", sample.rain_in_per_hr),
                ("snow", sample.snow_in_per_hr),
            )
            if value is None
        ]
        return RiskAssessment(
            level=None,
            wind_level=None,
            rain_level=None,
            snow_level=None,
            reason=f"{NO_DATA_LABEL}: forecast missing {', '.join(missing)}",
        )

    wind_level, load_rule = classify_wind(sample.wind_mph, load_lb)
    rain_level = classify_rain(sample.rain_in_per_hr)
    snow_level = classify_snow(sample.snow_in_per_hr)
    overall = max(wind_level, rain_level, snow_level)

    return RiskAssessment(
        level=overall,
        wind_level=wind_level,
        rain_level=rain_level,
        snow_level=snow_level,
        reason=_explain(sample, load_lb, overall, wind_level, rain_level, snow_level, load_rule),
    )


def _explain(sample, load_lb, overall, wind_level, rain_level, snow_level, load_rule):
    """Short human-readable reason, naming every condition that set the overall level."""
    if overall == RiskLevel.LOW:
        return "Low: no significant wind, rain or snow"

    causes = []
    if wind_level == overall:
        cause = f"wind {sample.wind_mph:.1f} mph"
        if load_rule is not None:
            cause += f" with {load_lb:,.0f} lb load (over {load_rule.weight_over_lb:,.0f} lb)"
        causes.append(cause)
    if rain_level == overall:
        causes.append(f"rain {sample.rain_in_per_hr:.2f} in/hr")
    if snow_level == overall:
        causes.append(f"snow {sample.snow_in_per_hr:.2f} in/hr")
    return f"{overall.label}: {', '.join(causes)}"
