"""Route options from public routing engines.

Primary: Valhalla with the `truck` costing model (respects truck weight and
truck-legal roads, gives truck travel times). Fallback: OSRM car profile.

Public engines often return fewer than three alternatives for long trips, so
`get_route_options` fills the gap with detours through sideways waypoints and
drops near-duplicates. Every route comes back as a list of (lat, lon) points
plus the cumulative travel time at each point, which is what the ETA sampling
needs.
"""

import logging
from dataclasses import dataclass

from django.conf import settings

from ..geo import cumulative_miles, decode_polyline, haversine_mi, offset_point
from .http import UpstreamError, fetch_json

log = logging.getLogger(__name__)

# Typical empty weight of a tractor + 53 ft dry van, used for truck costing.
TRACTOR_TRAILER_TARE_LBS = 35_000
LBS_PER_METRIC_TON = 2204.62


@dataclass
class RouteGeometry:
    points: list            # [(lat, lon), ...]
    vertex_seconds: list    # travel time from origin to each point
    distance_mi: float
    duration_s: float
    source: str             # "valhalla-truck" | "osrm" | "+detour"


def _spread_time(points, start_idx, end_idx, seconds, out):
    """Spread a maneuver's duration across its vertices by distance."""
    seg_miles = cumulative_miles(points[start_idx : end_idx + 1])
    span = seg_miles[-1] or 1.0
    base = out[start_idx]
    for k in range(1, len(seg_miles)):
        out[start_idx + k] = base + seconds * (seg_miles[k] / span)


def _valhalla(locations, load_lbs, alternates):
    gross_tons = min(36.0, (load_lbs + TRACTOR_TRAILER_TARE_LBS) / LBS_PER_METRIC_TON)
    body = {
        "locations": [
            {"lat": lat, "lon": lon, "type": "break" if i in (0, len(locations) - 1) else "through"}
            for i, (lat, lon) in enumerate(locations)
        ],
        "costing": "truck",
        "costing_options": {"truck": {"weight": round(gross_tons, 1)}},
        "units": "miles",
        "directions_type": "maneuvers",
    }
    if alternates:
        body["alternates"] = alternates
    data = fetch_json(
        f"{settings.VALHALLA_URL}/route", body=body, method="POST", cache_seconds=3600
    )
    trips = [data["trip"]] + [alt["trip"] for alt in data.get("alternates", [])]
    routes = []
    for trip in trips:
        points, seconds = [], []
        for leg in trip["legs"]:
            leg_points = decode_polyline(leg["shape"], 6)
            leg_seconds = [0.0] * len(leg_points)
            for m in leg.get("maneuvers", []):
                b, e = m["begin_shape_index"], m["end_shape_index"]
                if e > b:
                    _spread_time(leg_points, b, e, float(m.get("time", 0)), leg_seconds)
            offset = seconds[-1] if seconds else 0.0
            if points:  # legs share their joining vertex
                leg_points, leg_seconds = leg_points[1:], leg_seconds[1:]
            points.extend(leg_points)
            seconds.extend(s + offset for s in leg_seconds)
        routes.append(
            RouteGeometry(
                points=points,
                vertex_seconds=seconds,
                distance_mi=float(trip["summary"]["length"]),
                duration_s=float(trip["summary"]["time"]),
                source="valhalla-truck",
            )
        )
    return routes


def _osrm(locations, alternates):
    coords = ";".join(f"{lon},{lat}" for lat, lon in locations)
    data = fetch_json(
        f"{settings.OSRM_URL}/route/v1/driving/{coords}",
        params={
            "overview": "full",
            "geometries": "geojson",
            "annotations": "duration",
            "alternatives": str(alternates) if alternates else "false",
        },
        cache_seconds=3600,
    )
    if data.get("code") != "Ok":
        raise UpstreamError(f"OSRM: {data.get('message', data.get('code'))}")
    routes = []
    for route in data["routes"]:
        points = [(lat, lon) for lon, lat in route["geometry"]["coordinates"]]
        seconds = [0.0]
        for leg in route["legs"]:
            for d in leg["annotation"]["duration"]:
                seconds.append(seconds[-1] + d)
        # Annotation and geometry lengths match for overview=full; guard anyway.
        if len(seconds) != len(points):
            total = float(route["duration"])
            miles = cumulative_miles(points)
            seconds = [total * m / (miles[-1] or 1.0) for m in miles]
        routes.append(
            RouteGeometry(
                points=points,
                vertex_seconds=seconds,
                distance_mi=float(route["distance"]) / 1609.344,
                duration_s=float(route["duration"]),
                source="osrm",
            )
        )
    return routes


def _engine(locations, load_lbs, alternates=0):
    try:
        return _valhalla(locations, load_lbs, alternates)
    except (UpstreamError, KeyError, ValueError) as exc:
        log.warning("Valhalla failed (%s), falling back to OSRM", exc)
        return _osrm(locations, alternates)


def _overlap_ratio(a, b, sample=60):
    """Share of route `a` that lies within ~1 mile of route `b`."""
    if not a.points or not b.points:
        return 0.0
    step = max(1, len(a.points) // sample)
    probe = a.points[::step]
    b_pts = b.points[:: max(1, len(b.points) // 400)]
    close = sum(1 for p in probe if min(haversine_mi(p, q) for q in b_pts) < 1.0)
    return close / len(probe)


def _is_distinct(candidate, chosen, max_overlap=0.85):
    return all(_overlap_ratio(candidate, r) < max_overlap for r in chosen)


def get_route_options(origin, destination, load_lbs, wanted=3):
    """Return up to `wanted` distinct routes between two (lat, lon) points."""
    if haversine_mi(origin, destination) < 1.0:
        raise UpstreamError("Origin and destination are less than a mile apart")

    routes = _engine([origin, destination], load_lbs, alternates=wanted - 1)
    chosen = [routes[0]]
    for r in routes[1:]:
        if len(chosen) < wanted and _is_distinct(r, chosen):
            chosen.append(r)

    # Detours: push the midpoint (or the thirds) sideways by growing amounts.
    detour_plan = [
        [(0.5, 0.12)], [(0.5, -0.12)],
        [(0.5, 0.22)], [(0.5, -0.22)],
        [(0.33, 0.15), (0.66, 0.15)], [(0.33, -0.15), (0.66, -0.15)],
    ]
    for plan in detour_plan:
        if len(chosen) >= wanted:
            break
        vias = [offset_point(origin, destination, f, o) for f, o in plan]
        try:
            candidate = _engine([origin, *vias, destination], load_lbs)[0]
        except UpstreamError as exc:
            log.info("Detour %s failed: %s", plan, exc)
            continue
        # Reject silly detours (more than 60% longer than the fastest route).
        if candidate.duration_s > chosen[0].duration_s * 1.6:
            continue
        if _is_distinct(candidate, chosen):
            candidate.source += "+detour"
            chosen.append(candidate)
    return chosen
