"""Unit tests for daily log remarks and totals alignment."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase

from planning.constants import HOME_TERMINAL_TZ
from planning.logs_builder import build_daily_logs
from planning.types import DutySegment, LatLng

TZ = ZoneInfo(HOME_TERMINAL_TZ)
PT = LatLng(33.45, -112.07)


def seg(
    status,
    start,
    hours,
    *,
    remark="",
    stop_type=None,
    label="Phoenix, AZ",
    miles=0.0,
    stationary=True,
):
    return DutySegment(
        status=status,
        start=start,
        end=start + timedelta(hours=hours),
        miles=miles,
        point=PT,
        location_label=label,
        remark=remark,
        stop_type=stop_type,
        stationary=stationary,
    )


class LogsBuilderRemarksTests(SimpleTestCase):
    def test_same_city_status_changes_each_get_a_remark(self):
        """FMCSA: city/state on every duty-status change — even if City repeats."""
        t0 = datetime(2026, 8, 26, 0, 0, tzinfo=TZ)
        timeline = [
            seg("SB", t0, 17.5, remark="Sleeper berth", stop_type="rest_sb"),
            seg(
                "D",
                t0 + timedelta(hours=17.5),
                6.0,
                remark="Drive toward Atlanta",
                stop_type=None,
                stationary=False,
                miles=300,
            ),
            seg(
                "ON",
                t0 + timedelta(hours=23.5),
                0.5,
                remark="Fuel stop",
                stop_type="fuel",
            ),
        ]
        log = build_daily_logs(timeline, 65)[0]
        self.assertGreaterEqual(len(log.remarks), 3)
        times = [r.time for r in log.remarks]
        self.assertIn("00:00", times)
        self.assertIn("17:30", times)
        self.assertIn("23:30", times)
        # All still Phoenix — UI must not collapse; API keeps each change
        self.assertTrue(all(r.location_label == "Phoenix, AZ" for r in log.remarks))

    def test_totals_match_grid_ink_no_phantom_off(self):
        """Totals column must not invent Off Duty hours with no Off Duty grid line."""
        t0 = datetime(2026, 8, 27, 0, 0, tzinfo=TZ)
        timeline = [
            seg("SB", t0, 9.5, remark="Sleeper berth", stop_type="rest_sb"),
            seg(
                "D",
                t0 + timedelta(hours=9.5),
                11.0,
                remark="Drive",
                stationary=False,
                miles=500,
            ),
            seg(
                "ON",
                t0 + timedelta(hours=20.5),
                0.5,
                remark="Fuel stop",
                stop_type="fuel",
            ),
            seg(
                "SB",
                t0 + timedelta(hours=21.0),
                3.0,
                remark="Sleeper berth",
                stop_type="rest_sb",
            ),
        ]
        log = build_daily_logs(timeline, 20)[0]
        statuses = {g.status for g in log.grid_segments}
        self.assertNotIn("OFF", statuses)
        self.assertEqual(log.totals["off"], 0.0)
        self.assertAlmostEqual(sum(log.totals.values()), 24.0, places=2)
