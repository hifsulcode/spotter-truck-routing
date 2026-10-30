"""Hourly forecasts from Open-Meteo (free, no key, many points per request).

Units are requested to match the risk table directly: wind in mph, rain and
snowfall in inches. Open-Meteo hourly rain/snowfall is the amount over the
preceding hour, i.e. an in/hr rate.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from django.conf import settings

from .http import UpstreamError, fetch_json

HOURLY_VARS = "wind_speed_10m,rain,snowfall"
CHUNK = 100  # locations per request; keeps URLs well under limits


@dataclass
class Series:
    """Hourly forecast for one location."""

    start: datetime          # UTC, on the hour
    wind: list
    rain: list
    snow: list

    def at(self, when):
        """Linearly interpolated (wind, rain, snow) at a UTC datetime."""
        hours = (when - self.start).total_seconds() / 3600.0
        last = len(self.wind) - 1
        hours = max(0.0, min(float(last), hours))
        i = int(hours)
        j = min(last, i + 1)
        t = hours - i

        def lerp(values):
            a, b = values[i] or 0.0, values[j] or 0.0
            return a + (b - a) * t

        return lerp(self.wind), lerp(self.rain), lerp(self.snow)

    def hour(self, index):
        index = max(0, min(len(self.wind) - 1, index))
        return self.wind[index] or 0.0, self.rain[index] or 0.0, self.snow[index] or 0.0


def _floor_hour(dt):
    return dt.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)


def forecast(points, start, end):
    """Hourly series for each (lat, lon) covering [start, end] (UTC datetimes).

    Coordinates are rounded to ~1 km so repeated trips hit the cache.
    """
    if not points:
        return []
    start_h = _floor_hour(start)
    end_h = _floor_hour(end) + timedelta(hours=1)
    rounded = [(round(lat, 2), round(lon, 2)) for lat, lon in points]

    out = []
    for i in range(0, len(rounded), CHUNK):
        chunk = rounded[i : i + CHUNK]
        data = fetch_json(
            settings.OPEN_METEO_URL,
            params={
                "latitude": ",".join(f"{lat}" for lat, _ in chunk),
                "longitude": ",".join(f"{lon}" for _, lon in chunk),
                "hourly": HOURLY_VARS,
                "wind_speed_unit": "mph",
                "precipitation_unit": "inch",
                "timezone": "UTC",
                "start_hour": start_h.strftime("%Y-%m-%dT%H:%M"),
                "end_hour": end_h.strftime("%Y-%m-%dT%H:%M"),
            },
            cache_seconds=1800,
        )
        if isinstance(data, dict) and data.get("error"):
            raise UpstreamError(f"Open-Meteo: {data.get('reason')}")
        blocks = data if isinstance(data, list) else [data]
        if len(blocks) != len(chunk):
            raise UpstreamError("Open-Meteo returned an unexpected number of locations")
        for block in blocks:
            hourly = block["hourly"]
            first = datetime.fromisoformat(hourly["time"][0]).replace(tzinfo=timezone.utc)
            out.append(
                Series(
                    start=first,
                    wind=hourly["wind_speed_10m"],
                    rain=hourly["rain"],
                    snow=hourly["snowfall"],
                )
            )
    return out
