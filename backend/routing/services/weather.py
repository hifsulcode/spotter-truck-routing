"""Hourly forecasts from Open-Meteo (free, no key, many points per request).

Units are requested to match the risk table directly: wind in mph, rain and
snowfall in inches. Open-Meteo hourly rain/snowfall is the amount over the
preceding hour, i.e. an in/hr rate.

Open-Meteo limits free use per IP address. Free hosts (Render, etc.) share
outbound IPs between many apps, so the server's quota can be used up by
strangers. When that happens `forecast` raises `WeatherUnavailable` carrying the
exact requests it would have made; the browser runs them from the viewer's own
IP and posts the responses back as `supplied`. Risk scoring and ranking still
happen here, on the same data.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from django.conf import settings

from .http import UpstreamError, fetch_json

HOURLY_VARS = "wind_speed_10m,rain,snowfall"
CHUNK = 100  # locations per request; keeps URLs well under limits
MAX_HOURS = 24 * 17


class WeatherUnavailable(UpstreamError):
    """The server could not fetch forecasts; `requests` lets the client fetch them."""

    def __init__(self, message, requests):
        super().__init__(message)
        self.requests = requests


class SuppliedWeatherError(ValueError):
    """Client-supplied forecasts do not match the requests they answer."""


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


def build_requests(points, start, end):
    """Unique ~1 km locations and the Open-Meteo query for each batch of them.

    Coordinates are rounded to ~1 km so nearby checkpoints share a forecast and
    repeated trips hit the cache.
    """
    start_h = _floor_hour(start)
    end_h = _floor_hour(end) + timedelta(hours=1)
    unique = list(dict.fromkeys((round(lat, 2), round(lon, 2)) for lat, lon in points))
    batches = []
    for i in range(0, len(unique), CHUNK):
        chunk = unique[i : i + CHUNK]
        batches.append(
            {
                "latitude": ",".join(f"{lat}" for lat, _ in chunk),
                "longitude": ",".join(f"{lon}" for _, lon in chunk),
                "hourly": HOURLY_VARS,
                "wind_speed_unit": "mph",
                "precipitation_unit": "inch",
                "timezone": "UTC",
                "start_hour": start_h.strftime("%Y-%m-%dT%H:%M"),
                "end_hour": end_h.strftime("%Y-%m-%dT%H:%M"),
            }
        )
    return unique, batches


def _numbers(values, length):
    if not isinstance(values, list) or len(values) != length:
        raise SuppliedWeatherError("hourly arrays differ in length")
    if any(v is not None and not isinstance(v, (int, float)) for v in values):
        raise SuppliedWeatherError("hourly values must be numbers")
    return values


def _parse_batch(data, locations, check_location):
    if isinstance(data, dict) and data.get("error"):
        raise SuppliedWeatherError(f"Open-Meteo: {data.get('reason')}")
    blocks = data if isinstance(data, list) else [data]
    if len(blocks) != len(locations):
        raise SuppliedWeatherError("unexpected number of locations")
    out = []
    for block, (lat, lon) in zip(blocks, locations):
        try:
            hourly = block["hourly"]
            times = hourly["time"]
            first = datetime.fromisoformat(times[0]).replace(tzinfo=timezone.utc)
            got_lat, got_lon = float(block["latitude"]), float(block["longitude"])
        except (KeyError, TypeError, IndexError, ValueError) as exc:
            raise SuppliedWeatherError("missing hourly data") from exc
        n = len(times)
        if n > MAX_HOURS:
            raise SuppliedWeatherError("too many hours")
        # Open-Meteo snaps to its model grid, so allow a little drift.
        if check_location and (abs(got_lat - lat) > 0.5 or abs(got_lon - lon) > 0.5):
            raise SuppliedWeatherError("forecast is for a different location")
        out.append(
            Series(
                start=first,
                wind=_numbers(hourly.get("wind_speed_10m"), n),
                rain=_numbers(hourly.get("rain"), n),
                snow=_numbers(hourly.get("snowfall"), n),
            )
        )
    return out


def forecast(points, start, end, supplied=None):
    """Hourly series for each (lat, lon) covering [start, end] (UTC datetimes).

    `supplied` is the list of Open-Meteo responses, one per request, that the
    client fetched after a `WeatherUnavailable`.
    """
    if not points:
        return []
    unique, batches = build_requests(points, start, end)
    if supplied is not None and len(supplied) != len(batches):
        raise SuppliedWeatherError("expected one forecast per request")

    by_location = {}
    for i, params in enumerate(batches):
        locations = unique[i * CHUNK : (i + 1) * CHUNK]
        if supplied is None:
            try:
                data = fetch_json(settings.OPEN_METEO_URL, params=params, cache_seconds=1800)
            except UpstreamError as exc:
                raise WeatherUnavailable(
                    str(exc),
                    [{"url": settings.OPEN_METEO_URL, "params": p} for p in batches],
                ) from exc
            try:
                series = _parse_batch(data, locations, check_location=False)
            except SuppliedWeatherError as exc:
                raise UpstreamError(f"Open-Meteo returned unusable data: {exc}") from exc
        else:
            series = _parse_batch(supplied[i], locations, check_location=True)
        by_location.update(zip(locations, series))

    return [by_location[(round(lat, 2), round(lon, 2))] for lat, lon in points]
