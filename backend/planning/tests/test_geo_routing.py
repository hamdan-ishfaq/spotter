"""Tests for geocode/routing with mocked HTTP."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from planning.exceptions import GeocodeFailed
from planning.geocode import geocode_place
from planning.routing import build_route
from planning.types import LatLng, Place


class GeocodeRoutingTests(SimpleTestCase):
    def test_geocode_ors_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "features": [
                {
                    "geometry": {"coordinates": [-96.7970, 32.7767]},
                    "properties": {"label": "Dallas, Texas, United States", "region_a": "TX", "locality": "Dallas"},
                }
            ]
        }

        with patch("planning.geocode._ors_key", return_value="test-key"), patch(
            "planning.geocode.httpx.Client"
        ) as client_cls:
            client = MagicMock()
            client.__enter__.return_value = client
            client.get.return_value = mock_resp
            client_cls.return_value = client
            # clear cache side effects by unique query
            place = geocode_place("Dallas Test City XYZ")
            self.assertEqual(place.point.lat, 32.7767)
            self.assertIn("Dallas", place.label)

    def test_geocode_failure(self):
        with patch("planning.geocode._ors_key", return_value=""), patch(
            "planning.geocode._geocode_nominatim", return_value=None
        ), patch("planning.geocode._geocode_known", return_value=None):
            with self.assertRaises(GeocodeFailed):
                geocode_place("Nowherezz Fakeplace")

    def test_route_osrm_fallback(self):
        origin = Place("a", "Dallas, TX", LatLng(32.78, -96.8))
        dest = Place("b", "Houston, TX", LatLng(29.76, -95.37))
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "routes": [
                {
                    "distance": 385000,
                    "duration": 14400,
                    "geometry": {
                        "coordinates": [[-96.8, 32.78], [-95.37, 29.76]]
                    },
                }
            ]
        }
        with patch("planning.routing._ors_key", return_value=""), patch(
            "planning.routing.httpx.Client"
        ) as client_cls:
            client = MagicMock()
            client.__enter__.return_value = client
            client.get.return_value = mock_resp
            client_cls.return_value = client
            leg, used_car = build_route(origin, dest)
            self.assertTrue(used_car)
            self.assertGreater(leg.distance_miles, 200)
            self.assertEqual(len(leg.geometry), 2)
