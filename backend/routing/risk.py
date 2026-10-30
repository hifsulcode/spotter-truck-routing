"""Weather risk classification, exactly as specified in the assessment brief.

Thresholds (lower bound inclusive, upper bound exclusive, so every value falls
into exactly one band):

    Condition   Low        Moderate     High        Severe      No Travel
    Wind (mph)  < 25       25 - 34      35 - 44     45 - 54     >= 55
    Rain (in/h) < 0.10     0.10 - 0.25  0.25 - 0.50 0.50 - 1.00 > 1.00
    Snow (in/h) < 0.5      0.5 - 1.0    1.0 - 2.0   2.0 - 3.0   > 3.0

The brief writes the top rain/snow band as "> 1.00" / "> 3.0", so exactly
1.00 in/h of rain is Severe and only values above it are No Travel.

Load rules (wind + gross weight) can only raise a level, never lower it:
    wind >= 55 mph                 -> No Travel for any load
    wind 45-54 mph and > 30,000 lb -> No Travel
    wind 35-44 mph and > 40,000 lb -> Severe
"""

from dataclasses import dataclass, field
from enum import IntEnum


class Risk(IntEnum):
    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4

    @property
    def label(self):
        return {
            Risk.LOW: "Low",
            Risk.MODERATE: "Moderate",
            Risk.HIGH: "High",
            Risk.SEVERE: "Severe",
            Risk.NO_TRAVEL: "No Travel",
        }[self]


def wind_level(mph):
    if mph >= 55:
        return Risk.NO_TRAVEL
    if mph >= 45:
        return Risk.SEVERE
    if mph >= 35:
        return Risk.HIGH
    if mph >= 25:
        return Risk.MODERATE
    return Risk.LOW


def rain_level(in_per_hr):
    if in_per_hr > 1.00:
        return Risk.NO_TRAVEL
    if in_per_hr >= 0.50:
        return Risk.SEVERE
    if in_per_hr >= 0.25:
        return Risk.HIGH
    if in_per_hr >= 0.10:
        return Risk.MODERATE
    return Risk.LOW


def snow_level(in_per_hr):
    if in_per_hr > 3.0:
        return Risk.NO_TRAVEL
    if in_per_hr >= 2.0:
        return Risk.SEVERE
    if in_per_hr >= 1.0:
        return Risk.HIGH
    if in_per_hr >= 0.5:
        return Risk.MODERATE
    return Risk.LOW


def load_adjusted_wind_level(mph, load_lbs):
    """Wind level after the load rules are applied."""
    level = wind_level(mph)
    if mph >= 55:
        return Risk.NO_TRAVEL
    if 45 <= mph < 55 and load_lbs > 30_000:
        return Risk.NO_TRAVEL
    if 35 <= mph < 45 and load_lbs > 40_000:
        return max(level, Risk.SEVERE)
    return level


@dataclass
class Assessment:
    level: Risk
    wind: Risk
    rain: Risk
    snow: Risk
    reasons: list = field(default_factory=list)

    def as_dict(self):
        return {
            "level": int(self.level),
            "label": self.level.label,
            "wind": self.wind.label,
            "rain": self.rain.label,
            "snow": self.snow.label,
            "reasons": self.reasons,
        }


def assess(wind_mph, rain_in_hr, snow_in_hr, load_lbs):
    """Overall risk at one point = the worst of wind (load-adjusted), rain, snow."""
    wind_mph = max(0.0, wind_mph or 0.0)
    rain_in_hr = max(0.0, rain_in_hr or 0.0)
    snow_in_hr = max(0.0, snow_in_hr or 0.0)

    raw_wind = wind_level(wind_mph)
    wind = load_adjusted_wind_level(wind_mph, load_lbs)
    rain = rain_level(rain_in_hr)
    snow = snow_level(snow_in_hr)
    level = max(wind, rain, snow)

    reasons = []
    if wind > Risk.LOW:
        reasons.append(f"Wind {wind_mph:.0f} mph ({wind.label})")
    if wind > raw_wind:
        reasons.append(f"Raised from {raw_wind.label} by {load_lbs:,.0f} lb load")
    if rain > Risk.LOW:
        reasons.append(f"Rain {rain_in_hr:.2f} in/h ({rain.label})")
    if snow > Risk.LOW:
        reasons.append(f"Snow {snow_in_hr:.2f} in/h ({snow.label})")

    return Assessment(level=level, wind=wind, rain=rain, snow=snow, reasons=reasons)
