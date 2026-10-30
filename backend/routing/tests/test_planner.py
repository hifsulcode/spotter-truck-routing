from datetime import datetime, timedelta, timezone
from unittest import mock

from django.test import SimpleTestCase
from rest_framework.test import APIClient

from routing import planner
from routing.geo import cumulative_miles
from routing.services.directions import RouteGeometry
from routing.services.weather import Series

DEPART = datetime(2030, 1, 10, 12, tzinfo=timezone.utc)


def route(lon, miles=100, mph=60, source="test"):
    deg = miles / 69.05
    points = [(30.0 + deg * i / 99, lon) for i in range(100)]
    dist = cumulative_miles(points)
    seconds = [d / mph * 3600 for d in dist]
    return RouteGeometry(points, seconds, dist[-1], seconds[-1], source)


def series_for(points, start, end, storm_lon=None, storm_wind=50):
    """Calm weather everywhere, except a windstorm on one longitude."""
    out = []
    for lat, lon in points:
        wind = storm_wind if storm_lon is not None and abs(lon - storm_lon) < 1e-6 else 10
        out.append(Series(start=start, wind=[wind] * 60, rain=[0.0] * 60, snow=[0.0] * 60))
    return out


class RankingTests(SimpleTestCase):
    def _plan(self, routes, storm_lon=None, load=20_000):
        with mock.patch.object(planner.directions, "get_route_options", return_value=routes), \
             mock.patch.object(
                 planner.weather,
                 "forecast",
                 side_effect=lambda pts, s, e, **kw: series_for(pts, s, e, storm_lon),
             ):
            return planner.plan_trip(
                {"label": "A", "lat": 30.0, "lon": -97.0},
                {"label": "B", "lat": 31.4, "lon": -97.0},
                DEPART,
                load,
                25,
            )

    def test_faster_route_wins_when_risk_is_equal(self):
        result = self._plan([route(-97.0, mph=50), route(-96.9, mph=65)])
        self.assertEqual(result["recommended_route_id"], 1)

    def test_safer_route_wins_over_faster_route(self):
        # The fast route (lon -97.0) sits in a 50 mph windstorm = Severe.
        result = self._plan([route(-97.0, mph=70), route(-96.9, mph=50)], storm_lon=-97.0)
        self.assertEqual(result["recommended_route_id"], 1)
        fast = result["routes"][0]["summary"]
        self.assertGreater(fast["severe_miles"], 0)
        self.assertIn("Severe", result["recommendation"])

    def test_heavy_load_turns_storm_into_no_travel(self):
        result = self._plan([route(-97.0), route(-96.9, mph=40)], storm_lon=-97.0, load=35_000)
        stormy = result["routes"][0]
        self.assertEqual(stormy["summary"]["worst_label"], "No Travel")
        self.assertEqual(result["recommended_route_id"], 1)

    def test_checkpoints_carry_eta_and_weather(self):
        result = self._plan([route(-97.0)])
        cp = result["routes"][0]["checkpoints"][1]
        self.assertEqual(cp["mile"], 25.0)
        eta = datetime.fromisoformat(cp["eta"])
        self.assertAlmostEqual((eta - DEPART) / timedelta(minutes=1), 25, delta=0.5)
        self.assertEqual(cp["risk"]["label"], "Low")


class ApiTests(SimpleTestCase):
    def setUp(self):
        self.client = APIClient()

    def test_plan_validates_input(self):
        resp = self.client.post("/api/v1/plan/", {"origin": "", "load_lbs": -1}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("destination", resp.json())

    def test_plan_rejects_departure_beyond_forecast(self):
        far = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        resp = self.client.post(
            "/api/v1/plan/",
            {"origin": "Dallas", "destination": "Houston", "departure": far, "load_lbs": 1000},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("departure", resp.json())

    def test_plan_returns_ranked_routes(self):
        depart = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        with mock.patch.object(planner.directions, "get_route_options",
                               return_value=[route(-97.0), route(-96.9, mph=50)]), \
             mock.patch.object(planner.weather, "forecast",
                               side_effect=lambda p, s, e, **kw: series_for(p, s, e)):
            resp = self.client.post(
                "/api/v1/plan/",
                {
                    "origin": {"lat": 30.0, "lon": -97.0, "label": "A"},
                    "destination": {"lat": 31.4, "lon": -97.0, "label": "B"},
                    "departure": depart.isoformat(),
                    "load_lbs": 20000,
                    "interval_mi": 10,
                },
                format="json",
            )
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertEqual(len(body["routes"]), 2)
        self.assertEqual(sum(r["recommended"] for r in body["routes"]), 1)
        self.assertEqual(body["interval_mi"], 10)

    def test_heatmap_rejects_inverted_bbox(self):
        resp = self.client.post(
            "/api/v1/heatmap/",
            {"south": 32, "north": 30, "west": -97, "east": -95,
             "start": datetime.now(timezone.utc).isoformat(), "load_lbs": 1000},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
