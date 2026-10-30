# Weather-Aware Truck Routing

A React + Django app that helps a truck driver pick the safest route. It compares three
route options using the weather forecast **at the time the truck will actually reach each
point**, applies the brief's wind/rain/snow and load rules, and recommends the route with
the least dangerous weather, using travel time as the tie-breaker.

- **Live app:** _add Render URL_
- **Walkthrough (Loom):** _add link_

## What it does

1. Enter origin, destination, departure time, and load weight. Pick a checkpoint spacing
   of 10, 25, or 50 miles.
2. The API fetches **three route options**, using truck-aware routing where available.
3. Every route is sampled every N miles. Each checkpoint gets an **ETA** interpolated from
   the routing engine's per-maneuver travel times, so slow city stretches and fast
   interstates are timed correctly.
4. Hourly forecasts are fetched for every checkpoint in batched requests and interpolated
   to that checkpoint's ETA.
5. Each checkpoint is classified with the brief's risk table and load rules, and every
   route gets a summary of miles per risk level.
6. Routes are ranked and the best one is recommended, with a plain-English reason.
7. The map shows all three routes coloured by risk, every checkpoint (click one for ETA,
   weather, and why it got its level), and a **0–48 h weather-risk heatmap** over the trip
   corridor with a play/scrub slider.

## Risk rules (as specified)

| Condition | Low | Moderate | High | Severe | No Travel |
|---|---|---|---|---|---|
| Wind | < 25 mph | 25–34 | 35–44 | 45–54 | ≥ 55 mph |
| Rain | < 0.10 in/h | 0.10–0.25 | 0.25–0.50 | 0.50–1.00 | > 1.00 |
| Snow | < 0.5 in/h | 0.5–1.0 | 1.0–2.0 | 2.0–3.0 | > 3.0 |

**Load rules** only ever raise the wind level:

| Wind | Load | Result |
|---|---|---|
| ≥ 55 mph | any load | No Travel |
| 45–54 mph | > 30,000 lb | No Travel |
| 35–44 mph | > 40,000 lb | Severe |

A checkpoint's level is the worst of wind (after the load rules), rain, and snow.
Bands are lower-inclusive. The top rain and snow bands use the brief's strict
"> 1.00" and "> 3.0", so exactly 1.00 in/h of rain is still Severe. Every boundary is
unit-tested in `backend/routing/tests/test_risk.py`.

**Recommendation order** follows the brief:

1. Fewest Severe miles
2. Fewest High miles
3. Lowest distance-weighted average risk
4. Shortest travel time

**No Travel** miles are compared before all of these. A route that crosses a No Travel
zone is never ranked as safer than one that only touches Severe weather.

Each checkpoint "owns" the road between it and the previous checkpoint. Severe and High
miles are those segment lengths summed, so they are true road miles, not checkpoint
counts.

## Architecture

```
frontend/  React 19 + TypeScript + Vite, MUI, react-leaflet
backend/   Django 5.2 + DRF (stateless, no database models)
  routing/risk.py               risk table + load rules (pure functions)
  routing/geo.py                distances, polyline decoding, checkpoint sampling, ETA interpolation
  routing/planner.py            routes → checkpoints → weather at ETA → risk → ranking
  routing/heatmap.py            corridor grid × 49 hourly frames
  routing/services/directions.py  Valhalla truck routing, OSRM fallback, detour alternatives
  routing/services/weather.py     Open-Meteo hourly forecast, batched multi-point
  routing/services/geocode.py     Photon place search
```

**API**

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/geocode/?q=` | Place autocomplete |
| `POST` | `/api/v1/plan/` | `{origin, destination, departure, load_lbs, interval_mi}` → three ranked routes with checkpoints and summaries |
| `POST` | `/api/v1/heatmap/` | `{south, west, north, east, start, load_lbs, grid}` → 49 hourly risk frames |
| `GET` | `/api/v1/health/` | Health check |

### Data providers

All providers are free and need no API keys.

| Need | Provider | Notes |
|---|---|---|
| Routing | **Valhalla** `truck` costing (OpenStreetMap) | Uses gross weight (load + ~35,000 lb tractor-trailer tare) and truck-legal roads |
| Routing fallback | **OSRM** | Used for trips over Valhalla's public 1,500 km limit, or if Valhalla errors. Times are for cars. |
| Weather | **Open-Meteo** hourly forecast | Wind in mph, rain and snowfall in inches; values are per-hour amounts, i.e. in/h |
| Geocoding | **Photon** (OpenStreetMap) | Place search |

**Three routes, always.** Public routing engines often return fewer than three
alternatives, especially for long trips. The API fills the gap with detours through
waypoints pushed sideways from the direct line. It then drops candidates that overlap an
existing route by more than 85%, and drops anything more than 60% slower than the
fastest route.

### Performance choices (smooth UI)

- **Heatmap frames are rendered once, not on every slider move.** The API returns all 49
  hourly frames in one response. The browser paints each frame into a tiny image, one
  pixel per grid cell, and Leaflet stretches it over the corridor. Scrubbing or playing
  the slider only swaps the image URL, with no network calls and no redraw loops.
- **Canvas renderer with fixed panes.** Routes and checkpoints are drawn on canvas.
  Dedicated panes keep the stacking order deterministic: casing < other routes <
  selected route < checkpoints < endpoints.
- Adjacent checkpoint segments with the same risk are merged into one polyline. The route
  geometry sent to the browser is thinned to 400 points.
- Upstream responses are cached server-side: routing for 1 h, weather for 30 min,
  geocoding for 24 h. Checkpoint coordinates are rounded to about 1 km so repeat trips hit
  the cache.
- The routes appear first. The 48 h corridor forecast loads in the background, so the
  answer is never blocked by the heatmap.

## Run locally

```bash
# API
cd backend
python3 -m venv .venv && . .venv/bin/activate   # or: virtualenv .venv
pip install -r requirements.txt
python manage.py test        # 27 tests
python manage.py runserver   # http://localhost:8000

# Web
cd ../frontend
npm install
npm run dev                  # http://localhost:5173
```

No configuration is needed. Copy `.env.example` to `.env` to override defaults.

## Deploy

`render.yaml` is a Render Blueprint. Choose **New → Blueprint**, pick the repo, and it
creates the API (gunicorn + whitenoise) and the static web app. If you rename the
services, update `VITE_API_URL`, `DJANGO_ALLOWED_HOSTS` and `CORS_ALLOWED_ORIGINS`.

## Known limits

- Forecasts reach about 14 days ahead, so departures are limited to that window.
- Over 1,500 km, travel times come from OSRM's car profile, not truck routing.
- Weather is sampled at checkpoints. A short storm cell between two 50-mile checkpoints
  can be missed, which is why 10 and 25 mile spacing are offered.
- Open-Meteo hourly precipitation is the total for the preceding hour, and is treated as
  that hour's in/h rate.
