"""Planner + logs builder integration tests (live geocode/route)."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase

from planning.constants import (
    BREAK_AFTER_DRIVE_HOURS,
    CYCLE_LIMIT_HOURS,
    DAILY_DRIVE_LIMIT_HOURS,
    DUTY_WINDOW_HOURS,
    HOME_TERMINAL_TZ,
)
from planning.hos_planner import Planner, plan_trip
from planning.hos_verifier import verify
from planning.logs_builder import build_daily_logs
from planning.types import LatLng

TZ = ZoneInfo(HOME_TERMINAL_TZ)


def _hours(seg) -> float:
    return (seg.end - seg.start).total_seconds() / 3600.0


def _assert_timeline_hos_limits(testcase, timeline, *, msg: str = "") -> None:
    """Planner-side limits — fails if drive/window/break enforcement regresses."""
    window_start = None
    driving_since_break = 0.0

    for seg in timeline:
        h = _hours(seg)

        if seg.stop_type in ("rest_off", "rest_sb", "restart_34"):
            window_start = None
            driving_since_break = 0.0
            continue

        if seg.status in ("OFF", "SB"):
            if seg.stop_type == "break_30" or h + 1e-6 >= 0.5:
                driving_since_break = 0.0
            continue

        if seg.status in ("D", "ON"):
            if window_start is None:
                window_start = seg.start
            elapsed = (seg.start - window_start).total_seconds() / 3600.0
            detail = f"{msg} at {seg.start.isoformat()}"
            if seg.status == "D":
                testcase.assertLessEqual(
                    h,
                    DAILY_DRIVE_LIMIT_HOURS + 0.02,
                    msg=f"drive chunk {h:.2f}h > 11h {detail}",
                )
                testcase.assertLessEqual(
                    driving_since_break + h,
                    BREAK_AFTER_DRIVE_HOURS + 0.02,
                    msg=f"break cumulative {driving_since_break + h:.2f}h > 8h {detail}",
                )
                driving_since_break += h
            testcase.assertLessEqual(
                elapsed + h,
                DUTY_WINDOW_HOURS + 0.02,
                msg=f"duty window {elapsed + h:.2f}h > 14h {detail}",
            )


class PlannerFixtureTests(SimpleTestCase):
    def test_fixture_a_short_dallas_houston(self):
        result = plan_trip(
            current_location="Dallas, TX",
            pickup_location="Dallas, TX",
            dropoff_location="Houston, TX",
            current_cycle_used_hours=10,
            start_datetime=datetime(2026, 8, 10, 6, 0, tzinfo=TZ),
        )
        self.assertGreater(result.summary["total_miles"], 100)
        pickup_stops = [s for s in result.route["stops"] if s["type"] == "pickup"]
        drop_stops = [s for s in result.route["stops"] if s["type"] == "dropoff"]
        self.assertEqual(len(pickup_stops), 1)
        self.assertEqual(len(drop_stops), 1)
        self.assertAlmostEqual(pickup_stops[0]["duration_hours"], 1.0, places=1)
        self.assertAlmostEqual(drop_stops[0]["duration_hours"], 1.0, places=1)

        violations = verify(result.timeline, 10)
        self.assertEqual(violations, [], msg=str(violations))

        for log in result.daily_logs:
            self.assertAlmostEqual(sum(log.totals.values()), 24.0, delta=0.05)

        _assert_timeline_hos_limits(self, result.timeline, msg="fixture_a")

    def test_fixture_c_cycle_pressure_inserts_34h(self):
        result = plan_trip(
            current_location="Dallas, TX",
            pickup_location="Dallas, TX",
            dropoff_location="Houston, TX",
            current_cycle_used_hours=68,
            start_datetime=datetime(2026, 8, 10, 6, 0, tzinfo=TZ),
        )
        self.assertTrue(
            result.summary["inserted_34h_restart"]
            or any(s.stop_type == "restart_34" for s in result.timeline)
        )
        violations = verify(result.timeline, 68)
        self.assertEqual(violations, [], msg=str(violations))

    def test_fixture_d_multiday_day24_raw_verifier(self):
        result = plan_trip(
            "Chicago, IL",
            "Chicago, IL",
            "Los Angeles, CA",
            15,
            datetime(2026, 8, 10, 6, 0, tzinfo=TZ),
        )
        self.assertGreaterEqual(result.summary["days"], 2)
        violations = verify(result.timeline, 15)
        day24 = [v for v in violations if v.code == "DAY_24"]
        self.assertEqual(day24, [], msg=str(day24))
        other = [v for v in violations if v.code != "DAY_24"]
        self.assertEqual(other, [], msg=str(other))

    def test_empty_reposition_leg(self):
        result = plan_trip(
            current_location="Denver, CO",
            pickup_location="Chicago, IL",
            dropoff_location="Houston, TX",
            current_cycle_used_hours=8,
            start_datetime=datetime(2026, 8, 10, 6, 0, tzinfo=TZ),
        )
        pickup_start = next(
            s.start for s in result.timeline if s.stop_type == "pickup"
        )
        reposition = [
            s
            for s in result.timeline
            if s.status == "D" and s.end <= pickup_start + timedelta(seconds=1)
        ]
        self.assertGreater(len(reposition), 0, "expected empty reposition drive leg")
        self.assertGreater(result.summary["total_miles"], 500)
        violations = verify(result.timeline, 8)
        self.assertEqual(violations, [], msg=str(violations))

    def test_restart_resets_cycle_pool_to_70(self):
        planner = Planner(65.0, datetime(2026, 8, 10, 6, 0, tzinfo=TZ))
        self.assertAlmostEqual(planner.state.cycle_remaining, 5.0)
        planner._restart_34(LatLng(41.88, -87.63), "Chicago, IL")
        self.assertAlmostEqual(planner.state.cycle_remaining, CYCLE_LIMIT_HOURS)
        self.assertTrue(planner.inserted_34h)

    def test_logs_sum_24(self):
        result = plan_trip(
            "Chicago, IL",
            "Chicago, IL",
            "Denver, CO",
            15,
            datetime(2026, 8, 10, 6, 0, tzinfo=TZ),
        )
        logs = build_daily_logs(result.timeline, 15)
        self.assertGreaterEqual(len(logs), 1)
        for log in logs:
            self.assertAlmostEqual(sum(log.totals.values()), 24.0, delta=0.05)
            self.assertIn("on_duty_today", log.recap)
            self.assertIn("cycle_remaining_end", log.recap)

    def test_planner_respects_hos_limits_chi_denver(self):
        result = plan_trip(
            "Chicago, IL",
            "Chicago, IL",
            "Denver, CO",
            10,
            datetime(2026, 8, 10, 6, 0, tzinfo=TZ),
        )
        _assert_timeline_hos_limits(self, result.timeline, msg="chi_denver")
