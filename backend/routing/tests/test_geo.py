from django.test import SimpleTestCase

from routing.geo import cumulative_miles, decode_polyline, haversine_mi, sample_checkpoints


def straight_route(miles, n=200):
    """A due-north line of `miles` length driven at a constant 60 mph."""
    deg = miles / 69.05  # ~miles per degree of latitude
    points = [(30.0 + deg * i / (n - 1), -97.0) for i in range(n)]
    dist = cumulative_miles(points)
    seconds = [d / 60.0 * 3600 for d in dist]
    return points, seconds


class SamplingTests(SimpleTestCase):
    def test_checkpoints_every_interval_plus_origin_and_end(self):
        points, seconds = straight_route(120)
        cps = sample_checkpoints(points, seconds, 25)
        self.assertEqual([round(c.mile) for c in cps], [0, 25, 50, 75, 100, 120])

    def test_segment_miles_cover_the_whole_route(self):
        points, seconds = straight_route(120)
        cps = sample_checkpoints(points, seconds, 10)
        self.assertAlmostEqual(sum(c.segment_miles for c in cps), cps[-1].mile, places=6)

    def test_eta_follows_travel_time(self):
        points, seconds = straight_route(100)
        cps = sample_checkpoints(points, seconds, 50)
        # 50 miles at 60 mph = 50 minutes
        self.assertAlmostEqual(cps[1].seconds / 60, 50, delta=0.5)

    def test_eta_respects_uneven_speed(self):
        # First half crawls at 30 mph, second half flies at 60 mph.
        points, _ = straight_route(100)
        dist = cumulative_miles(points)
        seconds = [
            (d / 30 if d <= 50 else 50 / 30 + (d - 50) / 60) * 3600 for d in dist
        ]
        cps = sample_checkpoints(points, seconds, 50)
        self.assertAlmostEqual(cps[1].seconds / 3600, 50 / 30, delta=0.02)
        self.assertAlmostEqual(cps[2].seconds / 3600, 50 / 30 + 50 / 60, delta=0.02)

    def test_short_route_still_has_two_checkpoints(self):
        points, seconds = straight_route(4, n=20)
        cps = sample_checkpoints(points, seconds, 50)
        self.assertEqual(len(cps), 2)


class GeoTests(SimpleTestCase):
    def test_haversine_dallas_to_houston(self):
        self.assertAlmostEqual(haversine_mi((32.7767, -96.797), (29.7604, -95.3698)), 225, delta=3)

    def test_decode_polyline_precision_6(self):
        # Encodes (38.5, -120.2), (40.7, -120.95) at precision 5.
        self.assertEqual(
            [(round(a, 2), round(b, 2)) for a, b in decode_polyline("_p~iF~ps|U_ulLnnqC", 5)],
            [(38.5, -120.2), (40.7, -120.95)],
        )
