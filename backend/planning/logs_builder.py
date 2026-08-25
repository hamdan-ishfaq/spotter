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
        prev_stop = None
        for s in padded:
            if not s.remark:
                prev_status = s.status
                prev_stop = s.stop_type
                continue
            changed = s.status != prev_status or s.stop_type != prev_stop
            important = s.stop_type in IMPORTANT_STOPS
            if changed or important:
                # Deduplicate identical consecutive remarks
                if not (
                    remarks
                    and remarks[-1].time == s.start.strftime("%H:%M")
                    and remarks[-1].text == s.remark
                    and remarks[-1].location_label == s.location_label
                ):
                    remarks.append(
                        Remark(
                            time=s.start.strftime("%H:%M"),
                            location_label=s.location_label,
                            text=s.remark,
                        )
                    )
            prev_status = s.status
            prev_stop = s.stop_type

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
                        cycle_by_day_start.get(
                            day, CYCLE_LIMIT_HOURS - cycle_used_at_start
                        ),
                        2,
                    ),
                    "cycle_remaining_end": round(
                        cycle_by_day_end.get(day, CYCLE_LIMIT_HOURS - cycle_used_at_start),
                        2,
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
