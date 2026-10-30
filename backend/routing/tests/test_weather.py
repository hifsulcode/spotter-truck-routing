from datetime import datetime, timedelta, timezone
from unittest import mock

from django.test import SimpleTestCase
from rest_framework.test import APIClient

from routing.services import weather
from routing.services.http import UpstreamError
from routing.services.weather import SuppliedWeatherError, WeatherUnavailable

START = datetime(2030, 1, 10, 12, tzinfo=timezone.utc)
END = START + timedelta(hours=3)


def open_meteo_block(lat, lon, wind=10.0, hours=5):
    return {
        "latitude": lat,
        "longitude": lon,
        "hourly": {
            "time": [(START + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(hours)],
            "wind_speed_10m": [wind] * hours,
            "rain": [0.0] * hours,
            "snowfall": [None] * hours,
        },
    }


def answer(params, wind=10.0):
    """What Open-Meteo would return for one request's params."""
    lats = [float(x) for x in params["latitude"].split(",")]
    lons = [float(x) for x in params["longitude"].split(",")]
    blocks = [open_meteo_block(a, b, wind) for a, b in zip(lats, lons)]
    return blocks if len(blocks) > 1 else blocks[0]


class ForecastTests(SimpleTestCase):
    points = [(41.8781, -87.6298), (41.8779, -87.6301), (39.7392, -104.9903)]

    def test_nearby_points_share_one_forecast(self):
        unique, batches = weather.build_requests(self.points, START, END)
        self.assertEqual(unique, [(41.88, -87.63), (39.74, -104.99)])
        self.assertEqual(len(batches), 1)
        self.assertEqual(batches[0]["start_hour"], "2030-01-10T12:00")
        self.assertEqual(batches[0]["end_hour"], "2030-01-10T16:00")

    def test_server_fetch_maps_back_to_every_point(self):
        with mock.patch.object(weather, "fetch_json", side_effect=lambda url, params, **kw: answer(params)):
            series = weather.forecast(self.points, START, END)
        self.assertEqual(len(series), 3)
        self.assertIs(series[0], series[1])
        self.assertEqual(series[2].at(START + timedelta(minutes=30)), (10.0, 0.0, 0.0))

    def test_provider_refusal_hands_requests_to_the_client(self):
        with mock.patch.object(weather, "fetch_json", side_effect=UpstreamError("HTTP 429")):
            with self.assertRaises(WeatherUnavailable) as ctx:
                weather.forecast(self.points, START, END)
        _, batches = weather.build_requests(self.points, START, END)
        self.assertEqual([r["params"] for r in ctx.exception.requests], batches)

    def test_client_supplied_forecasts_are_used(self):
        _, batches = weather.build_requests(self.points, START, END)
        supplied = [answer(p, wind=40.0) for p in batches]
        with mock.patch.object(weather, "fetch_json") as fetch:
            series = weather.forecast(self.points, START, END, supplied=supplied)
        fetch.assert_not_called()
        self.assertEqual(series[0].hour(0)[0], 40.0)

    def test_supplied_forecasts_must_match_the_request(self):
        _, batches = weather.build_requests(self.points, START, END)
        with self.assertRaises(SuppliedWeatherError):
            weather.forecast(self.points, START, END, supplied=[])
        wrong_place = [[open_meteo_block(10.0, 10.0), open_meteo_block(39.74, -104.99)]]
        with self.assertRaises(SuppliedWeatherError):
            weather.forecast(self.points, START, END, supplied=wrong_place)
        bad_values = answer(batches[0])
        bad_values[0]["hourly"]["rain"] = ["lots"] * 5
        with self.assertRaises(SuppliedWeatherError):
            weather.forecast(self.points, START, END, supplied=[bad_values])


class WeatherFallbackApiTests(SimpleTestCase):
    def setUp(self):
        self.client = APIClient()
        self.body = {
            "south": 39.0,
            "west": -105.0,
            "north": 42.0,
            "east": -87.0,
            "start": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            "load_lbs": 42000,
            "grid": 4,
        }

    def test_heatmap_asks_the_client_then_accepts_its_forecasts(self):
        with mock.patch.object(weather, "fetch_json", side_effect=UpstreamError("HTTP 429")):
            first = self.client.post("/api/v1/heatmap/", self.body, format="json")
        self.assertEqual(first.status_code, 503)
        self.assertEqual(first.json()["code"], "weather_unavailable")
        requests = first.json()["weather_requests"]

        supplied = [answer(r["params"]) for r in requests]
        second = self.client.post("/api/v1/heatmap/", {**self.body, "weather": supplied}, format="json")
        self.assertEqual(second.status_code, 200)
        self.assertEqual(len(second.json()["levels"][0]), 16)

    def test_mismatched_forecasts_are_a_400(self):
        resp = self.client.post(
            "/api/v1/heatmap/", {**self.body, "weather": [{"error": True, "reason": "x"}]}, format="json"
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("weather", resp.json())
