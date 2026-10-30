"""Weather-risk heatmap over the trip corridor for the next 0-48 hours.

The corridor's bounding box is covered by a regular grid. For every grid point
we fetch 49 hourly forecasts once and classify each hour with the same
load-aware risk rules used for checkpoints. The browser gets every frame in a
single response, so moving the hour slider never waits on the network.
"""

from datetime import timedelta

from .risk import assess
from .services import weather

HOURS = 48
MAX_GRID = 24


def grid_points(south, west, north, east, size):
    lat_step = (north - south) / (size - 1)
    lon_step = (east - west) / (size - 1)
    return [
        (round(south + r * lat_step, 3), round(west + c * lon_step, 3))
        for r in range(size)
        for c in range(size)
    ]


def build(south, west, north, east, start, load_lbs, size=14):
    size = max(4, min(MAX_GRID, size))
    points = grid_points(south, west, north, east, size)
    series = weather.forecast(points, start, start + timedelta(hours=HOURS))

    frames, wind = [], []
    for h in range(HOURS + 1):
        levels, winds = [], []
        for s in series:
            w, r, sn = s.hour(h)
            levels.append(int(assess(w, r, sn, load_lbs).level))
            winds.append(round(w))
        frames.append(levels)
        wind.append(winds)

    start_hour = series[0].start if series else start
    return {
        "grid_size": size,
        "points": [[lat, lon] for lat, lon in points],
        "hours": [(start_hour + timedelta(hours=h)).isoformat() for h in range(HOURS + 1)],
        "levels": frames,   # levels[hour][point] in 0..4
        "wind_mph": wind,   # wind_mph[hour][point], for the tooltip legend
    }
