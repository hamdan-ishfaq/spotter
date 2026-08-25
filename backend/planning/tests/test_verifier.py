"""Unit tests for HOS verifier."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase

from planning.constants import HOME_TERMINAL_TZ
from planning.hos_verifier import verify
from planning.types import DutySegment, LatLng

TZ = ZoneInfo(HOME_TERMINAL_TZ)


def seg(
    status,
    start,
    hours,
    *,
    miles=0.0,
    stop_type=None,
    remark="",
    stationary=False,
    label="Test, TX",
):
    end = start + timedelta(hours=hours)
    return DutySegment(
        status=status,
        start=start,
        end=end,
        miles=miles,
        point=LatLng(32.78, -96.8),
        location_label=label,
        remark=remark,
        stop_type=stop_type,
        stationary=stationary,
    )


class VerifierTests(SimpleTestCase):
    def test_legal_short_timeline_passes(self):
        t0 = datetime(2026, 8, 10, 6, 0, tzinfo=TZ)
        timeline = [
            seg("ON", t0, 0.5, stop_type="pretrip", remark="Pre-trip", stationary=True),
            seg(
                "ON",
                t0 + timedelta(hours=0.5),
                1.0,
                stop_type="pickup",
                remark="Pickup",
                stationary=True,
            ),
            seg(
                "D",
                t0 + timedelta(hours=1.5),
                4.0,
                miles=220,
                remark="Drive",
            ),
            seg(
                "ON",
                t0 + timedelta(hours=5.5),
                1.0,
                stop_type="dropoff",
                remark="Dropoff",
                stationary=True,
            ),
            seg("OFF", t0 + timedelta(hours=6.5), 17.5, remark="Off duty"),
        ]
        # pad to cover? not full day interior — should pass
        v = verify(timeline, cycle_used_at_start=10)
        codes = {x.code for x in v}
        self.assertNotIn("DRIVE_11", codes)
        self.assertNotIn("WINDOW_14", codes)
        self.assertNotIn("BREAK_8", codes)
        self.assertNotIn("PICKUP_1H", codes)
        self.assertNotIn("DROPOFF_1H", codes)

    def test_drive_over_11_violates(self):
        t0 = datetime(2026, 8, 10, 6, 0, tzinfo=TZ)
        timeline = [
            seg("ON", t0, 1.0, stop_type="pickup", remark="Pickup", stationary=True),
            seg("D", t0 + timedelta(hours=1), 8.0, miles=400),
            seg("OFF", t0 + timedelta(hours=9), 0.5, stop_type="break_30"),
            seg("D", t0 + timedelta(hours=9.5), 4.0, miles=200),  # 12h drive total
            seg(
                "ON",
                t0 + timedelta(hours=13.5),
                1.0,
                stop_type="dropoff",
                remark="Dropoff",
                stationary=True,
            ),
        ]
        v = verify(timeline, 0)
        self.assertTrue(any(x.code == "DRIVE_11" for x in v))

    def test_window_14_violates(self):
        t0 = datetime(2026, 8, 10, 6, 0, tzinfo=TZ)
        timeline = [
            seg("ON", t0, 1.0, stop_type="pickup", remark="Pickup", stationary=True),
            seg("D", t0 + timedelta(hours=1), 8.0, miles=400),
            seg("OFF", t0 + timedelta(hours=9), 0.5, stop_type="break_30"),
            # sit around then drive after hour 14
            seg("ON", t0 + timedelta(hours=9.5), 5.0, remark="Waiting"),
            seg("D", t0 + timedelta(hours=14.5), 1.0, miles=50),
            seg(
                "ON",
                t0 + timedelta(hours=15.5),
                1.0,
                stop_type="dropoff",
                remark="Dropoff",
                stationary=True,
            ),
        ]
        v = verify(timeline, 0)
        self.assertTrue(any(x.code == "WINDOW_14" for x in v))

    def test_break_8_violates(self):
        t0 = datetime(2026, 8, 10, 6, 0, tzinfo=TZ)
        timeline = [
            seg("ON", t0, 1.0, stop_type="pickup", remark="Pickup", stationary=True),
            seg("D", t0 + timedelta(hours=1), 9.0, miles=450),  # no break
            seg(
                "ON",
                t0 + timedelta(hours=10),
                1.0,
                stop_type="dropoff",
                remark="Dropoff",
                stationary=True,
            ),
        ]
        v = verify(timeline, 0)
        self.assertTrue(any(x.code == "BREAK_8" for x in v))

    def test_fuel_1000_violates(self):
        t0 = datetime(2026, 8, 10, 6, 0, tzinfo=TZ)
        timeline = [
            seg("ON", t0, 1.0, stop_type="pickup", remark="Pickup", stationary=True),
            seg("D", t0 + timedelta(hours=1), 8.0, miles=1100),
            seg("OFF", t0 + timedelta(hours=9), 0.5, stop_type="break_30"),
            seg("D", t0 + timedelta(hours=9.5), 2.0, miles=100),
            seg(
                "ON",
                t0 + timedelta(hours=11.5),
                1.0,
                stop_type="dropoff",
                remark="Dropoff",
                stationary=True,
            ),
        ]
        v = verify(timeline, 0)
        self.assertTrue(any(x.code == "FUEL_1000" for x in v))

    def test_cycle_70_violates_without_restart(self):
        t0 = datetime(2026, 8, 10, 6, 0, tzinfo=TZ)
        timeline = [
            seg("ON", t0, 1.0, stop_type="pickup", remark="Pickup", stationary=True),
            seg("D", t0 + timedelta(hours=1), 3.0, miles=150),
            seg(
                "ON",
                t0 + timedelta(hours=4),
                1.0,
                stop_type="dropoff",
                remark="Dropoff",
                stationary=True,
            ),
        ]
        # only 2h remaining in cycle; need ~5h on-duty
        v = verify(timeline, cycle_used_at_start=68)
        self.assertTrue(any(x.code == "CYCLE_70" for x in v))

    def test_missing_pickup_violates(self):
        t0 = datetime(2026, 8, 10, 6, 0, tzinfo=TZ)
        timeline = [
            seg("D", t0, 2.0, miles=100),
            seg(
                "ON",
                t0 + timedelta(hours=2),
                1.0,
                stop_type="dropoff",
                remark="Dropoff",
                stationary=True,
            ),
        ]
        v = verify(timeline, 0)
        self.assertTrue(any(x.code == "PICKUP_1H" for x in v))

    def test_reset_10_violates_short_daily_reset(self):
        t0 = datetime(2026, 8, 10, 6, 0, tzinfo=TZ)
        timeline = [
            seg(
                "OFF",
                t0,
                0.5,
                stop_type="rest_off",
                remark="Begin 10h break / post-trip",
                stationary=True,
            ),
            seg(
                "SB",
                t0 + timedelta(hours=0.5),
                9.0,
                stop_type="rest_sb",
                remark="Sleeper berth",
                stationary=True,
            ),
        ]
        v = verify(timeline, 0)
        self.assertTrue(any(x.code == "RESET_10" for x in v))

    def test_reset_10_passes_full_daily_reset(self):
        t0 = datetime(2026, 8, 10, 6, 0, tzinfo=TZ)
        timeline = [
            seg(
                "OFF",
                t0,
                0.5,
                stop_type="rest_off",
                remark="Begin 10h break / post-trip",
                stationary=True,
            ),
            seg(
                "SB",
                t0 + timedelta(hours=0.5),
                9.5,
                stop_type="rest_sb",
                remark="Sleeper berth",
                stationary=True,
            ),
        ]
        v = verify(timeline, 0)
        self.assertFalse(any(x.code == "RESET_10" for x in v))
