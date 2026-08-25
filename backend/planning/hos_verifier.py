"""Independent HOS legality verifier."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .constants import (
    BREAK_AFTER_DRIVE_HOURS,
    BREAK_DURATION_HOURS,
    CYCLE_LIMIT_HOURS,
    DAILY_DRIVE_LIMIT_HOURS,
    DAILY_RESET_OFF_HOURS,
    DAILY_RESET_SB_HOURS,
    DROPOFF_DURATION_HOURS,
    DUTY_WINDOW_HOURS,
    FUEL_EVERY_MILES,
    HOME_TERMINAL_TZ,
    HOUR_TOLERANCE,
    PICKUP_DURATION_HOURS,
    RESTART_34_HOURS,
)
from .types import DutySegment, Violation

TZ = ZoneInfo(HOME_TERMINAL_TZ)


def _hours(seg: DutySegment) -> float:
    return max(0.0, (seg.end - seg.start).total_seconds() / 3600.0)


def _is_on_duty(status: str) -> bool:
    return status in ("D", "ON")


def _is_rest(status: str) -> bool:
    return status in ("OFF", "SB")


def verify(timeline: list[DutySegment], cycle_used_at_start: float) -> list[Violation]:
    violations: list[Violation] = []
    if not timeline:
        violations.append(Violation("SEG_ORDER", "Timeline is empty"))
        return violations

    # SEG_ORDER + TZ
    for i, seg in enumerate(timeline):
        if seg.start.tzinfo is None or seg.end.tzinfo is None:
            violations.append(
                Violation("TZ", "All datetimes must be timezone-aware", seg.start)
            )
        if seg.end <= seg.start:
            violations.append(
                Violation("SEG_ORDER", "Segment end must be after start", seg.start)
            )
        if i > 0:
            prev = timeline[i - 1]
            gap = abs((seg.start - prev.end).total_seconds())
            if gap > 1.0:
                violations.append(
                    Violation(
                        "SEG_ORDER",
                        f"Timeline gap/overlap between segments at {seg.start.isoformat()}",
                        seg.start,
                    )
                )

    # Simulate clocks
    window_start: datetime | None = None
    driving_in_window = 0.0
    driving_since_break = 0.0
    miles_since_fuel = 0.0
    cycle_remaining = CYCLE_LIMIT_HOURS - cycle_used_at_start
    consecutive_rest_h = 0.0

    pickup_hours = 0.0
    dropoff_hours = 0.0
    pickup_count = 0
    dropoff_count = 0

    for seg in timeline:
        h = _hours(seg)

        if seg.stop_type == "pickup" or (
            seg.status == "ON" and "pickup" in (seg.remark or "").lower()
        ):
            if seg.stop_type == "pickup":
                pickup_count += 1
                pickup_hours += h
        if seg.stop_type == "dropoff" or (
            seg.status == "ON" and "dropoff" in (seg.remark or "").lower()
        ):
            if seg.stop_type == "dropoff":
                dropoff_count += 1
                dropoff_hours += h

        # 34h restart resets cycle
        if seg.status == "SB" and seg.stop_type == "restart_34" and h + HOUR_TOLERANCE >= RESTART_34_HOURS:
            cycle_remaining = CYCLE_LIMIT_HOURS
            window_start = None
            driving_in_window = 0.0
            driving_since_break = 0.0
            consecutive_rest_h = 0.0
            continue

        # Track consecutive rest for daily reset detection
        if _is_rest(seg.status):
            consecutive_rest_h += h
            if consecutive_rest_h + HOUR_TOLERANCE >= (
                DAILY_RESET_OFF_HOURS + DAILY_RESET_SB_HOURS
            ):
                window_start = None
                driving_in_window = 0.0
                driving_since_break = 0.0
            if h + HOUR_TOLERANCE >= BREAK_DURATION_HOURS:
                driving_since_break = 0.0
            if _is_on_duty(seg.status):
                pass
            continue

        consecutive_rest_h = 0.0

        if _is_on_duty(seg.status):
            if window_start is None:
                window_start = seg.start

            if cycle_remaining + HOUR_TOLERANCE < h:
                violations.append(
                    Violation(
                        "CYCLE_70",
                        f"On-duty {h:.2f}h exceeds cycle remaining {cycle_remaining:.2f}h",
                        seg.start,
                    )
                )
            cycle_remaining -= h

            if seg.status == "ON":
                if h + HOUR_TOLERANCE >= BREAK_DURATION_HOURS:
                    driving_since_break = 0.0
                if seg.stop_type == "fuel":
                    miles_since_fuel = 0.0
                continue

            # Driving
            if window_start is not None:
                window_end = window_start + timedelta(hours=DUTY_WINDOW_HOURS)
                if seg.start + timedelta(seconds=1) > window_end:
                    violations.append(
                        Violation(
                            "WINDOW_14",
                            "Driving after 14-hour window ended",
                            seg.start,
                        )
                    )
                # any driving that extends past window end
                if seg.end > window_end + timedelta(seconds=30):
                    violations.append(
                        Violation(
                            "WINDOW_14",
                            "Driving segment extends past 14-hour window",
                            seg.start,
                        )
                    )

            if driving_since_break - HOUR_TOLERANCE > BREAK_AFTER_DRIVE_HOURS:
                violations.append(
                    Violation(
                        "BREAK_8",
                        "Driving without required 30-minute break after 8h",
                        seg.start,
                    )
                )

            projected_break = driving_since_break + h
            if projected_break - HOUR_TOLERANCE > BREAK_AFTER_DRIVE_HOURS:
                violations.append(
                    Violation(
                        "BREAK_8",
                        f"Drive chunk pushes past 8h without break ({projected_break:.2f}h)",
                        seg.start,
                    )
                )

            projected_drive = driving_in_window + h
            if projected_drive - HOUR_TOLERANCE > DAILY_DRIVE_LIMIT_HOURS:
                violations.append(
                    Violation(
                        "DRIVE_11",
                        f"Driving exceeds 11h limit ({projected_drive:.2f}h)",
                        seg.start,
                    )
                )

            if miles_since_fuel - 0.5 > FUEL_EVERY_MILES:
                violations.append(
                    Violation(
                        "FUEL_1000",
                        f"Exceeded 1000 miles since fuel ({miles_since_fuel:.1f})",
                        seg.start,
                    )
                )

            projected_miles = miles_since_fuel + seg.miles
            if projected_miles - 0.5 > FUEL_EVERY_MILES:
                violations.append(
                    Violation(
                        "FUEL_1000",
                        f"Drive chunk exceeds 1000 miles since fuel ({projected_miles:.1f})",
                        seg.start,
                    )
                )

            driving_in_window += h
            driving_since_break += h
            miles_since_fuel += seg.miles

    # Pickup / dropoff
    if pickup_count != 1:
        violations.append(
            Violation("PICKUP_1H", f"Expected exactly one pickup stop, found {pickup_count}")
        )
    elif abs(pickup_hours - PICKUP_DURATION_HOURS) > HOUR_TOLERANCE + 0.05:
        violations.append(
            Violation(
                "PICKUP_1H",
                f"Pickup duration {pickup_hours:.2f}h != {PICKUP_DURATION_HOURS}h",
            )
        )

    if dropoff_count != 1:
        violations.append(
            Violation(
                "DROPOFF_1H", f"Expected exactly one dropoff stop, found {dropoff_count}"
            )
        )
    elif abs(dropoff_hours - DROPOFF_DURATION_HOURS) > HOUR_TOLERANCE + 0.05:
        violations.append(
            Violation(
                "DROPOFF_1H",
                f"Dropoff duration {dropoff_hours:.2f}h != {DROPOFF_DURATION_HOURS}h",
            )
        )

    # DAY_24 — after splitting at midnight
    day_hours: dict = defaultdict(float)
    for seg in timeline:
        # split across midnights
        cursor = seg.start.astimezone(TZ)
        end = seg.end.astimezone(TZ)
        while cursor < end:
            next_midnight = (cursor + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            slice_end = min(end, next_midnight)
            day_hours[cursor.date()] += (slice_end - cursor).total_seconds() / 3600.0
            cursor = slice_end

    for day, total in day_hours.items():
        # Only enforce full days that are completely covered; partial first/last
        # days are OK if trip doesn't span full midnight-midnight.
        # For segments that cover a full calendar day interior, require ~24.
        # Simpler rule: if a day's covered span is the only activity and sum of
        # all segments that day should be close to 24 when day is fully inside trip.
        pass

    # Stronger DAY_24: for each calendar day that has any segment, if the
    # timeline covers from midnight to midnight of that day, sum must be ~24.
    if timeline:
        trip_start = timeline[0].start.astimezone(TZ)
        trip_end = timeline[-1].end.astimezone(TZ)
        d = trip_start.date()
        end_date = trip_end.date()
        while d <= end_date:
            day_start = datetime(d.year, d.month, d.day, tzinfo=TZ)
            day_end = day_start + timedelta(days=1)
            # Fully interior day
            if day_start >= trip_start and day_end <= trip_end:
                total = day_hours.get(d, 0.0)
                if abs(total - 24.0) > HOUR_TOLERANCE + 0.05:
                    violations.append(
                        Violation(
                            "DAY_24",
                            f"Day {d.isoformat()} totals {total:.2f}h, expected 24",
                            day_start,
                        )
                    )
            d += timedelta(days=1)

    # RESET_10: if any rest_off+rest_sb pair claimed, ensure >= 10h consecutive
    i = 0
    while i < len(timeline):
        seg = timeline[i]
        if seg.stop_type == "rest_off":
            rest_h = _hours(seg)
            j = i + 1
            while j < len(timeline) and _is_rest(timeline[j].status):
                rest_h += _hours(timeline[j])
                if timeline[j].stop_type == "rest_sb":
                    break
                j += 1
            if rest_h + HOUR_TOLERANCE < 10.0:
                violations.append(
                    Violation(
                        "RESET_10",
                        f"Daily reset only {rest_h:.2f}h, need >= 10",
                        seg.start,
                    )
                )
        i += 1

    return violations
