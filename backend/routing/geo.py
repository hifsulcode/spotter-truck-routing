"""Geometry helpers: distances, polyline decoding, checkpoint sampling."""

import math
from dataclasses import dataclass

EARTH_RADIUS_MI = 3958.7613


def haversine_mi(a, b):
    """Great-circle distance in miles between two (lat, lon) points."""
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_MI * math.asin(min(1.0, math.sqrt(h)))


def decode_polyline(encoded, precision=6):
    """Decode a Google-style encoded polyline (Valhalla uses precision 6)."""
    coords, index, lat, lon = [], 0, 0, 0
    factor = 10 ** precision
    while index < len(encoded):
        for axis in (0, 1):
            shift = result = 0
            while True:
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else result >> 1
            if axis == 0:
                lat += delta
            else:
                lon += delta
        coords.append((lat / factor, lon / factor))
    return coords


def cumulative_miles(points):
    """Running distance (miles) at every vertex of a polyline."""
    out = [0.0]
    for prev, cur in zip(points, points[1:]):
        out.append(out[-1] + haversine_mi(prev, cur))
    return out


def _interp(a, b, t):
    return a + (b - a) * t


@dataclass
class Checkpoint:
    lat: float
    lon: float
    mile: float          # distance from origin along the route
    seconds: float       # travel time from departure to this point
    segment_miles: float  # length of road this checkpoint represents


def sample_checkpoints(points, vertex_seconds, interval_mi):
    """Place a checkpoint every `interval_mi` along the route, plus the end.

    `vertex_seconds[i]` is the travel time from the origin to `points[i]`, so
    the ETA at a checkpoint is interpolated along the segment it falls on.
    This keeps ETAs honest on routes where speed changes (city vs interstate).

    Each checkpoint "owns" the road between it and the previous checkpoint;
    those `segment_miles` are what the route summary sums into Severe/High
    miles.
    """
    if len(points) < 2:
        raise ValueError("A route needs at least two points")
    miles = cumulative_miles(points)
    total = miles[-1]

    targets = [0.0]
    step = interval_mi
    while step < total - 1e-6:
        targets.append(step)
        step += interval_mi
    targets.append(total)

    checkpoints, seg = [], 0
    for target in targets:
        while seg < len(miles) - 2 and miles[seg + 1] < target:
            seg += 1
        span = miles[seg + 1] - miles[seg]
        t = 0.0 if span <= 0 else min(1.0, max(0.0, (target - miles[seg]) / span))
        lat = _interp(points[seg][0], points[seg + 1][0], t)
        lon = _interp(points[seg][1], points[seg + 1][1], t)
        seconds = _interp(vertex_seconds[seg], vertex_seconds[seg + 1], t)
        checkpoints.append(Checkpoint(lat, lon, target, seconds, 0.0))

    for i in range(1, len(checkpoints)):
        checkpoints[i].segment_miles = checkpoints[i].mile - checkpoints[i - 1].mile
    return checkpoints


def simplify(points, max_points=400):
    """Evenly thin a polyline for the browser; always keeps both ends."""
    if len(points) <= max_points:
        return points
    stride = (len(points) - 1) / (max_points - 1)
    return [points[round(i * stride)] for i in range(max_points)]


def bounding_box(point_lists, pad_ratio=0.15, min_pad_deg=0.3):
    lats = [p[0] for pts in point_lists for p in pts]
    lons = [p[1] for pts in point_lists for p in pts]
    south, north, west, east = min(lats), max(lats), min(lons), max(lons)
    pad_lat = max(min_pad_deg, (north - south) * pad_ratio)
    pad_lon = max(min_pad_deg, (east - west) * pad_ratio)
    return south - pad_lat, west - pad_lon, north + pad_lat, east + pad_lon


def offset_point(a, b, fraction, offset_ratio):
    """A point `fraction` of the way from a to b, pushed sideways.

    Used to generate detour waypoints when the routing engine returns fewer
    than three alternatives. `offset_ratio` is the sideways push as a share of
    the a-b distance (positive = left of travel direction).
    """
    lat = _interp(a[0], b[0], fraction)
    lon = _interp(a[1], b[1], fraction)
    # Work in a locally flat frame where 1 deg lon is shrunk by cos(lat).
    k = math.cos(math.radians(lat))
    dx, dy = (b[1] - a[1]) * k, b[0] - a[0]
    length = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / length, dx / length
    dist = math.hypot(dx, dy) * offset_ratio
    return lat + ny * dist, lon + (nx * dist) / (k or 1.0)
