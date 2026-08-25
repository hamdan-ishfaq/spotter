"""Build calendar daily logs from a duty timeline."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .constants import (
    CARRIER_NAME,
    CO_DRIVER,
    COMMODITY,
    CYCLE_LIMIT_HOURS,
    DRAW_TICK_MINUTES,
    DRIVER_NAME,
    HOME_TERMINAL_TZ,
    LOAD_ID,
    MAIN_OFFICE,
    SHIPPER,
    VEHICLE_NUMBER,
)
from .types import DailyLog, DutySegment, GridSeg, Remark

TZ = ZoneInfo(HOME_TERMINAL_TZ)


def _hours(seg: DutySegment) -> float:
    return (seg.end - seg.start).total_seconds() / 3600.0


def _split_at_midnight(timeline: list[DutySegment]) -> list[DutySegment]:
    out: list[DutySegment] = []
    for seg in timeline:
        cursor = seg.start.astimezone(TZ)
        end = seg.end.astimezone(TZ)
        total_h = (end - cursor).total_seconds() / 3600.0
        miles_left = seg.miles
        while cursor < end:
            nxt = (cursor + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            slice_end = min(end, nxt)
            slice_h = (slice_end - cursor).total_seconds() / 3600.0
            share = (slice_h / total_h) if total_h > 0 else 0
            slice_miles = miles_left * share if seg.status == "D" else 0.0
            miles_left -= slice_miles
            out.append(
                DutySegment(
                    status=seg.status,
                    start=cursor,
                    end=slice_end,
                    miles=slice_miles,
                    point=seg.point,
                    location_label=seg.location_label,
                    remark=seg.remark,
                    stop_type=seg.stop_type,
                    stationary=seg.stationary,
                )
            )
            cursor = slice_end
    return out


def _snap_minute(minute: float) -> int:
    step = DRAW_TICK_MINUTES
    return int(round(minute / step) * step)


def build_daily_logs(
    timeline: list[DutySegment],
    cycle_used_at_start: float,
) -> list[DailyLog]:
    if not timeline:
        return []

    split = _split_at_midnight(timeline)
    by_day: dict = defaultdict(list)
    for seg in split:
        by_day[seg.start.astimezone(TZ).date()].append(seg)

    # Track cycle remaining through original timeline for recap
    cycle = CYCLE_LIMIT_HOURS - cycle_used_at_start
    cycle_by_day_start: dict = {}
    cycle_by_day_end: dict = {}
    for seg in timeline:
        d = seg.start.astimezone(TZ).date()
        if d not in cycle_by_day_start:
            cycle_by_day_start[d] = cycle
        if seg.status in ("D", "ON"):
            cycle -= _hours(seg)
        if seg.stop_type == "restart_34":
            cycle = CYCLE_LIMIT_HOURS
        cycle_by_day_end[d] = cycle

    logs: list[DailyLog] = []
    for day in sorted(by_day.keys()):
        segs: list[DutySegment] = by_day[day]
        day_start = datetime(day.year, day.month, day.day, tzinfo=TZ)
        day_end = day_start + timedelta(days=1)

        # Pad OFF to fill 00:00 → first segment and last → 24:00
        padded: list[DutySegment] = []
        if segs[0].start > day_start:
            padded.append(
                DutySegment(
                    status="OFF",
                    start=day_start,
                    end=segs[0].start,
                    miles=0.0,
                    point=segs[0].point,
                    location_label=segs[0].location_label,
                    remark="Off duty",
                    stop_type=None,
                    stationary=True,
                )
            )
        padded.extend(segs)
        if padded[-1].end < day_end:
            padded.append(
                DutySegment(
                    status="OFF",
                    start=padded[-1].end,
                    end=day_end,
                    miles=0.0,
                    point=padded[-1].point,
                    location_label=padded[-1].location_label,
                    remark="Off duty",
                    stop_type=None,
                    stationary=True,
                )
            )

        totals = {"off": 0.0, "sb": 0.0, "drive": 0.0, "on": 0.0}
        for s in padded:
            h = _hours(s)
            if s.status == "OFF":
                totals["off"] += h
            elif s.status == "SB":
                totals["sb"] += h
            elif s.status == "D":
                totals["drive"] += h
            else:
                totals["on"] += h

        # Reconcile to 24.00 on longest OFF/SB
        drift = 24.0 - sum(totals.values())
        if abs(drift) > 1e-6:
            rest_idxs = [
                i for i, s in enumerate(padded) if s.status in ("OFF", "SB")
            ]
            if rest_idxs:
                i = max(rest_idxs, key=lambda idx: _hours(padded[idx]))
                s = padded[i]
                new_end = s.end + timedelta(hours=drift)
                # keep within day
                new_end = min(max(new_end, s.start + timedelta(minutes=1)), day_end)
                padded[i] = DutySegment(
                    status=s.status,
                    start=s.start,
                    end=new_end,
                    miles=s.miles,
                    point=s.point,
                    location_label=s.location_label,
                    remark=s.remark,
                    stop_type=s.stop_type,
                    stationary=s.stationary,
                )
                totals = {"off": 0.0, "sb": 0.0, "drive": 0.0, "on": 0.0}
                for s2 in padded:
                    h = _hours(s2)
                    if s2.status == "OFF":
                        totals["off"] += h
                    elif s2.status == "SB":
                        totals["sb"] += h
                    elif s2.status == "D":
                        totals["drive"] += h
                    else:
                        totals["on"] += h

        for k in totals:
            totals[k] = round(totals[k], 2)
        # final nudge
        diff = round(24.0 - sum(totals.values()), 2)
        if abs(diff) >= 0.01:
            totals["off"] = round(totals["off"] + diff, 2)

        remarks: list[Remark] = []
        prev_status = None
        for s in padded:
            if s.status != prev_status and s.remark:
                remarks.append(
                    Remark(
                        time=s.start.strftime("%H:%M"),
                        location_label=s.location_label,
                        text=s.remark,
                    )
                )
            prev_status = s.status

        grid: list[GridSeg] = []
        for s in padded:
            start_m = (s.start - day_start).total_seconds() / 60.0
            end_m = (s.end - day_start).total_seconds() / 60.0
            sm = max(0, min(1440, _snap_minute(start_m)))
            em = max(0, min(1440, _snap_minute(end_m)))
            if em <= sm:
                em = min(1440, sm + DRAW_TICK_MINUTES)
            grid.append(
                GridSeg(
                    status=s.status,
                    start_minute=sm,
                    end_minute=em,
                    bracket=bool(s.stationary and s.status == "ON"),
                )
            )

        work_labels = [
            s.location_label
            for s in padded
            if s.stop_type in ("pickup", "dropoff", "fuel", "pretrip")
            or s.status == "D"
        ]
        from_loc = work_labels[0] if work_labels else padded[0].location_label
        to_loc = work_labels[-1] if work_labels else padded[-1].location_label
        miles = round(sum(s.miles for s in padded), 1)
        on_duty_today = round(totals["drive"] + totals["on"], 2)

        logs.append(
            DailyLog(
                date=day.isoformat(),
                from_location=from_loc,
                to_location=to_loc,
                total_miles_driving=miles,
                segments=padded,
                totals=totals,
                remarks=remarks,
                recap={
                    "on_duty_today": on_duty_today,
                    "cycle_remaining_start": round(
                        cycle_by_day_start.get(day, CYCLE_LIMIT_HOURS - cycle_used_at_start),
                        2,
                    ),
                    "cycle_remaining_end": round(
                        cycle_by_day_end.get(day, cycle), 2
                    ),
                    "note": "Approximate — full 8-day history not provided",
                },
                grid_segments=grid,
                header={
                    "carrier_name": CARRIER_NAME,
                    "main_office": MAIN_OFFICE,
                    "vehicle_number": VEHICLE_NUMBER,
                    "co_driver": CO_DRIVER,
                    "shipper": SHIPPER,
                    "commodity": COMMODITY,
                    "load_id": LOAD_ID,
                    "driver_name": DRIVER_NAME,
                },
            )
        )
    return logs
