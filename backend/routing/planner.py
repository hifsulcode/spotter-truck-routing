"""Trip planning: routes -> checkpoints -> weather at ETA -> risk -> ranking."""

from datetime import timedelta

from .geo import bounding_box, sample_checkpoints, simplify
from .risk import Risk, assess
from .services import directions, weather

ROUTE_NAMES = ["Route A", "Route B", "Route C", "Route D"]


def _summarize(checkpoints):
    """Miles per risk level and distance-weighted average risk for one route."""
    miles = {level: 0.0 for level in Risk}
    for cp in checkpoints:
        miles[Risk(cp["risk"]["level"])] += cp["segment_miles"]
    total = sum(miles.values()) or 1.0
    avg = sum(int(level) * m for level, m in miles.items()) / total
    worst = max((cp["risk"]["level"] for cp in checkpoints), default=0)
    return {
        "miles_by_level": {level.label: round(m, 1) for level, m in miles.items()},
        "no_travel_miles": round(miles[Risk.NO_TRAVEL], 1),
        "severe_miles": round(miles[Risk.SEVERE], 1),
        "high_miles": round(miles[Risk.HIGH], 1),
        "average_risk": round(avg, 3),
        "worst_level": worst,
        "worst_label": Risk(worst).label,
    }


def ranking_key(route):
    """The brief's order: Severe miles, High miles, average risk, travel time.

    No Travel miles are compared first: a route that crosses a No Travel zone
    is never safer than one that only touches Severe weather.
    """
    s = route["summary"]
    return (
        s["no_travel_miles"],
        s["severe_miles"],
        s["high_miles"],
        s["average_risk"],
        route["duration_s"],
    )


def _explain(best, others):
    s = best["summary"]
    if not others:
        return f"{best['name']} is the only route available."
    parts = []
    for other in others:
        o = other["summary"]
        if o["no_travel_miles"] > s["no_travel_miles"]:
            parts.append(f"avoids {o['no_travel_miles'] - s['no_travel_miles']:.0f} No Travel miles on {other['name']}")
        elif o["severe_miles"] > s["severe_miles"]:
            parts.append(f"{o['severe_miles'] - s['severe_miles']:.0f} fewer Severe miles than {other['name']}")
        elif o["high_miles"] > s["high_miles"]:
            parts.append(f"{o['high_miles'] - s['high_miles']:.0f} fewer High miles than {other['name']}")
        elif o["average_risk"] > s["average_risk"] + 1e-9:
            parts.append(f"lower average risk than {other['name']}")
        else:
            mins = (other["duration_s"] - best["duration_s"]) / 60
            parts.append(f"equal risk to {other['name']} but {mins:.0f} min faster")
    return f"{best['name']} recommended: " + "; ".join(parts) + "."


def plan_trip(origin, destination, departure, load_lbs, interval_mi):
    """Build every route option with weather-at-ETA checkpoints and rank them."""
    options = directions.get_route_options(
        (origin["lat"], origin["lon"]), (destination["lat"], destination["lon"]), load_lbs
    )

    sampled = [sample_checkpoints(o.points, o.vertex_seconds, interval_mi) for o in options]
    all_points = [(c.lat, c.lon) for cps in sampled for c in cps]
    latest = max(o.duration_s for o in options)
    series = weather.forecast(all_points, departure, departure + timedelta(seconds=latest))

    routes, cursor = [], 0
    for idx, (option, cps) in enumerate(zip(options, sampled)):
        checkpoints = []
        for cp in cps:
            eta = departure + timedelta(seconds=cp.seconds)
            wind, rain, snow = series[cursor].at(eta)
            cursor += 1
            checkpoints.append(
                {
                    "lat": round(cp.lat, 5),
                    "lon": round(cp.lon, 5),
                    "mile": round(cp.mile, 1),
                    "segment_miles": round(cp.segment_miles, 2),
                    "eta": eta.isoformat(),
                    "hours_from_departure": round(cp.seconds / 3600, 2),
                    "weather": {
                        "wind_mph": round(wind, 1),
                        "rain_in_hr": round(rain, 3),
                        "snow_in_hr": round(snow, 3),
                    },
                    "risk": assess(wind, rain, snow, load_lbs).as_dict(),
                }
            )
        routes.append(
            {
                "id": idx,
                "name": ROUTE_NAMES[idx],
                "source": option.source,
                "distance_mi": round(option.distance_mi, 1),
                "duration_s": round(option.duration_s),
                "arrival": (departure + timedelta(seconds=option.duration_s)).isoformat(),
                "geometry": [[round(lat, 5), round(lon, 5)] for lat, lon in simplify(option.points)],
                "checkpoints": checkpoints,
                "summary": _summarize(checkpoints),
            }
        )

    ranked = sorted(routes, key=ranking_key)
    best = ranked[0]
    for rank, route in enumerate(ranked, start=1):
        route["rank"] = rank
        route["recommended"] = route is best
    south, west, north, east = bounding_box([r["geometry"] for r in routes])

    return {
        "origin": origin,
        "destination": destination,
        "departure": departure.isoformat(),
        "load_lbs": load_lbs,
        "interval_mi": interval_mi,
        "recommended_route_id": best["id"],
        "recommendation": _explain(best, ranked[1:]),
        "bbox": {"south": south, "west": west, "north": north, "east": east},
        "routes": routes,
    }
