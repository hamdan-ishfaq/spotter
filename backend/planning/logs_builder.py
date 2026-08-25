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
    HOME_TERMINAL_ADDRESS,
    HOME_TERMINAL_TZ,
    LOAD_ID,
    MAIN_OFFICE,
    PERIOD_START_LABEL,
    PERIOD_START_TIME,
    SHIPPER,
    VEHICLE_NUMBER,
)
from .types import DailyLog, DutySegment, GridSeg, Remark

TZ = ZoneInfo(HOME_TERMINAL_TZ)

IMPORTANT_STOPS = {
    "pickup",
    "dropoff",
    "fuel",
    "pretrip",
    "break_30",
    "rest_off",
    "rest_sb",
    "restart_34",
}

STATUS_REMARK = {
    "OFF": "Off duty",
    "SB": "Sleeper berth",
    "D": "Driving",
    "ON": "On duty (not driving)",
}


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


def _recompute_totals(padded: list[DutySegment]) -> dict[str, float]:
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
    return totals


def _track_cycle_by_day(
    timeline: list[DutySegment], cycle_used_at_start: float
) -> tuple[dict, dict]:
    """Walk every calendar day covered by the timeline for accurate recap."""
    cycle = CYCLE_LIMIT_HOURS - cycle_used_at_start
    cycle_by_day_start: dict = {}
    cycle_by_day_end: dict = {}

    for seg in timeline:
        cursor = seg.start.astimezone(TZ)
        end = seg.end.astimezone(TZ)
        while cursor < end:
            d = cursor.date()
            if d not in cycle_by_day_start:
                cycle_by_day_start[d] = cycle
            day_end = datetime(d.year, d.month, d.day, tzinfo=TZ) + timedelta(days=1)
            slice_end = min(end, day_end)
            h = (slice_end - cursor).total_seconds() / 3600.0
            if seg.status in ("D", "ON"):
                cycle -= h
            cycle_by_day_end[d] = cycle
            cursor = slice_end
        if seg.stop_type == "restart_34":
            cycle = CYCLE_LIMIT_HOURS
            d = (seg.end - timedelta(seconds=1)).astimezone(TZ).date()
            cycle_by_day_end[d] = cycle

    return cycle_by_day_start, cycle_by_day_end


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

    cycle_by_day_start, cycle_by_day_end = _track_cycle_by_day(
        timeline, cycle_used_at_start
    )

    logs: list[DailyLog] = []
    for day in sorted(by_day.keys()):
        segs: list[DutySegment] = by_day[day]
        day_start = datetime(day.year, day.month, day.day, tzinfo=TZ)
        day_end = day_start + timedelta(days=1)

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

        totals = _recompute_totals(padded)
        drift = 24.0 - sum(totals.values())
        if abs(drift) > 1e-6:
            rest_idxs = [
                i for i, s in enumerate(padded) if s.status in ("OFF", "SB")
            ]
            if rest_idxs:
                i = max(rest_idxs, key=lambda idx: _hours(padded[idx]))
                s = padded[i]
                new_end = s.end + timedelta(hours=drift)
                # Keep within day and before next segment
                next_start = padded[i + 1].start if i + 1 < len(padded) else day_end
                new_end = min(max(new_end, s.start + timedelta(minutes=1)), next_start, day_end)
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
                totals = _recompute_totals(padded)

        for k in totals:
            totals[k] = round(totals[k], 2)
        diff = round(24.0 - sum(totals.values()), 2)
        if abs(diff) >= 0.01:
            # Prefer adjusting the longest OFF/SB total so grid and totals stay aligned
            if totals["off"] >= totals["sb"]:
                totals["off"] = round(totals["off"] + diff, 2)
            else:
                totals["sb"] = round(totals["sb"] + diff, 2)

        remarks: list[Remark] = []
        prev_status = None
        for idx, s in enumerate(padded):
            # Skip midnight / end-of-day padding filler (not a real duty change)
            is_pad = (
                s.stop_type is None
                and (s.remark or "").strip().lower() in ("off duty", "off-duty", "")
                and s.status == "OFF"
                and s.stationary
                and (
                    (idx == 0 and s.start == day_start)
                    or (idx == len(padded) - 1 and s.end == day_end)
                )
            )
            if is_pad:
                prev_status = s.status
                continue

            status_changed = prev_status is None or s.status != prev_status
            important = s.stop_type in IMPORTANT_STOPS
            # FMCSA §395.8: city/state in Remarks on every change of duty status
            if status_changed or important:
                text = (s.remark or "").strip() or STATUS_REMARK.get(s.status, s.status)
                loc = (s.location_label or "").strip() or "—"
                if not (
                    remarks
                    and remarks[-1].time == s.start.strftime("%H:%M")
                    and remarks[-1].text == text
                    and remarks[-1].location_label == loc
                ):
                    remarks.append(
                        Remark(
                            time=s.start.strftime("%H:%M"),
                            location_label=loc,
                            text=text,
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

        # From = where the day starts; To = where the day ends
        from_loc = padded[0].location_label
        to_loc = padded[-1].location_label
        # Prefer first/last meaningful movement/work if present
        for s in padded:
            if s.stop_type in ("pickup", "dropoff", "fuel", "pretrip") or s.status == "D":
                from_loc = s.location_label
                break
        for s in reversed(padded):
            if s.stop_type in ("pickup", "dropoff", "fuel", "pretrip") or s.status == "D":
                to_loc = s.location_label
                break

        miles = round(sum(s.miles for s in padded), 1)
        on_duty_today = round(totals["drive"] + totals["on"], 2)

        rem_start = round(
            cycle_by_day_start.get(day, CYCLE_LIMIT_HOURS - cycle_used_at_start),
            2,
        )
        rem_end = round(
            cycle_by_day_end.get(day, CYCLE_LIMIT_HOURS - cycle_used_at_start),
            2,
        )
        # FMCSA recap A/B/C for 70h/8-day (approx without full prior RODS)
        # A = total on-duty hours in current 8-day window including today
        # B = hours available tomorrow (70 − A)
        # C = approx on-duty last 7 days including today
        a_70 = round(max(0.0, min(CYCLE_LIMIT_HOURS, CYCLE_LIMIT_HOURS - rem_end)), 2)
        b_70 = round(max(0.0, rem_end), 2)
        # Drop one average prior day from the 8-day pool when estimating 7-day C
        prior_avg = (
            round(cycle_used_at_start / 8.0, 2) if cycle_used_at_start > 0 else 0.0
        )
        c_70 = round(max(0.0, a_70 - prior_avg), 2)

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
                    "cycle_remaining_start": rem_start,
                    "cycle_remaining_end": rem_end,
                    "a_70_8": a_70,
                    "b_70_8": b_70,
                    "c_70_8": c_70,
                    "a_60_7": None,
                    "b_60_7": None,
                    "c_60_7": None,
                    "note": (
                        "70/8 A/B/C approx from cycle clocks — "
                        "full 8-day prior RODS not provided; carrier uses 70/8"
                    ),
                },
                grid_segments=grid,
                header={
                    "carrier_name": CARRIER_NAME,
                    "main_office": MAIN_OFFICE,
                    "home_terminal": HOME_TERMINAL_ADDRESS,
                    "period_start_time": PERIOD_START_TIME,
                    "period_start_label": PERIOD_START_LABEL,
                    "time_zone": HOME_TERMINAL_TZ,
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
