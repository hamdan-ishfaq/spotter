"""API endpoint tests."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory

from planning.constants import HOME_TERMINAL_TZ
from planning.types import PlanResult
from planning.views import HealthView, PlanView

TZ = ZoneInfo(HOME_TERMINAL_TZ)


class ApiTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    def test_health(self):
        req = self.factory.get("/api/health/")
        resp = HealthView.as_view()(req)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], "ok")

    def test_plan_validation(self):
        req = self.factory.post(
            "/api/plan/",
            {
                "current_location": "Dallas, TX",
                "pickup_location": "Dallas, TX",
                "dropoff_location": "Houston, TX",
                "current_cycle_used_hours": 80,
            },
            format="json",
        )
        resp = PlanView.as_view()(req)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["error"]["code"], "VALIDATION_ERROR")

    def test_plan_rejects_bool_cycle(self):
        req = self.factory.post(
            "/api/plan/",
            {
                "current_location": "Dallas, TX",
                "pickup_location": "Dallas, TX",
                "dropoff_location": "Houston, TX",
                "current_cycle_used_hours": True,
            },
            format="json",
        )
        resp = PlanView.as_view()(req)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["error"]["code"], "VALIDATION_ERROR")

    def test_plan_rejects_same_pickup_dropoff_fields_shape(self):
        with patch("planning.views.plan_trip") as mocked:
            from planning.exceptions import ValidationFailed

            mocked.side_effect = ValidationFailed(
                "Pickup and dropoff must be different locations",
                fields={
                    "dropoff_location": [
                        "Pickup and dropoff must be different locations."
                    ]
                },
            )
            req = self.factory.post(
                "/api/plan/",
                {
                    "current_location": "Dallas, TX",
                    "pickup_location": "Dallas, TX",
                    "dropoff_location": "Dallas, TX",
                    "current_cycle_used_hours": 10,
                },
                format="json",
            )
            resp = PlanView.as_view()(req)
            self.assertEqual(resp.status_code, 400)
            fields = resp.data["error"]["fields"]
            self.assertIsInstance(fields["dropoff_location"], list)
            self.assertTrue(fields["dropoff_location"][0])


    def test_plan_happy_path_mocked(self):
        fake = PlanResult(
            summary={"total_miles": 100, "days": 1, "inserted_34h_restart": False},
            places={},
            route={"geometry": [], "stops": []},
            instructions=[],
            timeline=[],
            daily_logs=[],
            assumptions=["test"],
        )
        with patch("planning.views.plan_trip", return_value=fake):
            req = self.factory.post(
                "/api/plan/",
                {
                    "current_location": "Dallas, TX",
                    "pickup_location": "Dallas, TX",
                    "dropoff_location": "Houston, TX",
                    "current_cycle_used_hours": 10,
                    "start_datetime": datetime(2026, 8, 10, 6, 0, tzinfo=TZ).isoformat(),
                },
                format="json",
            )
            resp = PlanView.as_view()(req)
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.data["summary"]["total_miles"], 100)
            self.assertIn("assumptions", resp.data)
