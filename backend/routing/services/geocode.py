"""Place search via Photon (OpenStreetMap data, free, no key)."""

from django.conf import settings

from .http import UpstreamError, fetch_json


def _label(props):
    parts = [props.get("name"), props.get("city"), props.get("state"), props.get("country")]
    seen, out = set(), []
    for part in parts:
        if part and part not in seen:
            seen.add(part)
            out.append(part)
    return ", ".join(out)


def search(query, limit=6):
    data = fetch_json(
        settings.PHOTON_URL,
        params={"q": query, "limit": limit, "lang": "en"},
        cache_seconds=24 * 3600,
    )
    # Photon often returns the same city several times (node, boundary, place);
    # keep the first match per label so the dropdown has no look-alikes.
    results, seen = [], set()
    for feature in data.get("features", []):
        lon, lat = feature["geometry"]["coordinates"]
        label = _label(feature.get("properties", {}))
        if not label or label in seen:
            continue
        seen.add(label)
        results.append({"label": label, "lat": lat, "lon": lon})
    return results


def resolve(place):
    """Accept {"lat","lon"} or a free-text string and return {"label","lat","lon"}."""
    if isinstance(place, dict) and "lat" in place and "lon" in place:
        return {
            "label": place.get("label") or f"{place['lat']:.4f}, {place['lon']:.4f}",
            "lat": float(place["lat"]),
            "lon": float(place["lon"]),
        }
    text = place.get("label") if isinstance(place, dict) else place
    matches = search(str(text), limit=1)
    if not matches:
        raise UpstreamError(f"Could not find a location for '{text}'")
    return matches[0]
