"""HOS trip planner — builds a legal duty timeline for the assessment rules."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .constants import (
    AVG_SPEED_MPH,
    BREAK_AFTER_DRIVE_HOURS,
    BREAK_DURATION_HOURS,
    CYCLE_LIMIT_HOURS,
    DAILY_DRIVE_LIMIT_HOURS,
    DAILY_RESET_OFF_HOURS,
    DAILY_RESET_SB_HOURS,
    DROPOFF_DURATION_HOURS,
    DUTY_WINDOW_HOURS,
    ENABLE_PRETRIP,
    FUEL_DURATION_HOURS,
    FUEL_EVERY_MILES,
    HOME_TERMINAL_TZ,
    PICKUP_DURATION_HOURS,
    PRETRIP_DURATION_HOURS,
    RESTART_34_HOURS,
    SAME_POINT_EPSILON_MILES,
)
from .exceptions import PlanIntegrityError, ValidationFailed
from .geo import interpolate_along_route, nearly_same
from .geocode import geocode_place, reverse_geocode_label
from .hos_verifier import verify
from .instructions import build_instructions
from .logs_builder import build_daily_logs
from .routing import build_route
from .types import DutySegment, HosState, LatLng, Place, PlanResult, RouteLeg, StopType

TZ = ZoneInfo(HOME_TERMINAL_TZ)


class Planner:
    def __init__(self, cycle_used: float, start: datetime):
        self.segments: list[DutySegment] = []
        self.stops: list[dict] = []
        self.used_car = False
        self.state = HosState(
            t=start,
            window_start=None,
            driving_in_window=0.0,
            driving_since_break=0.0,
            miles_since_fuel=0.0,
            cycle_remaining=CYCLE_LIMIT_HOURS - cycle_used,
            needs_pretrip=ENABLE_PRETRIP,
        )
        self.inserted_34h = False
        self.geometry: list[LatLng] = []

    def _emit(
        self,
        status: str,
        hours: float,
        *,
        miles: float = 0.0,
        point: LatLng | None = None,
        label: str = "",
        remark: str = "",
        stop_type: StopType | None = None,
        stationary: bool = False,
    ) -> None:
        if hours <= 1e-9 and miles <= 0:
            return
        start = self.state.t
        minutes = max(1, int(round(hours * 60)))
        end = start + timedelta(minutes=minutes)

        actual_h = (end - start).total_seconds() / 3600.0
        seg = DutySegment(
            status=status,  # type: ignore[arg-type]
            start=start,
            end=end,
            miles=miles,
            point=point,
            location_label=label,
            remark=remark,
            stop_type=stop_type,
            stationary=stationary,
        )
        self.segments.append(seg)

        if status in ("D", "ON"):
            if self.state.window_start is None:
                self.state.window_start = start
            self.state.cycle_remaining -= actual_h

        if status == "D":
            self.state.driving_in_window += actual_h
            self.state.driving_since_break += actual_h
            self.state.miles_since_fuel += miles
        elif status == "ON":
            if actual_h + 1e-6 >= BREAK_DURATION_HOURS:
                self.state.driving_since_break = 0.0
            if stop_type == "fuel":
                self.state.miles_since_fuel = 0.0
        elif status in ("OFF", "SB"):
            if actual_h + 1e-6 >= BREAK_DURATION_HOURS:
                self.state.driving_since_break = 0.0

        if stop_type in (
            "pickup",
            "dropoff",
            "fuel",
            "break_30",
            "rest_off",
            "rest_sb",
            "restart_34",
            "pretrip",
            "current",
        ):
            self.stops.append(
                {
                    "type": stop_type,
                    "label": label,
                    "lat": point.lat if point else None,
                    "lng": point.lng if point else None,
                    "arrival": start.isoformat(),
                    "departure": end.isoformat(),
                    "duration_hours": round(actual_h, 2),
                }
            )

        self.state.t = end

    def _daily_reset(self, point: LatLng, label: str) -> None:
        self._emit(
            "OFF",
            DAILY_RESET_OFF_HOURS,
            point=point,
            label=label,
            remark="Begin 10h break / post-trip",
            stop_type="rest_off",
            stationary=True,
        )
        self._emit(
            "SB",
            DAILY_RESET_SB_HOURS,
            point=point,
            label=label,
            remark="Sleeper berth",
            stop_type="rest_sb",
            stationary=True,
        )
        self.state.window_start = None
        self.state.driving_in_window = 0.0
        self.state.driving_since_break = 0.0
        self.state.needs_pretrip = ENABLE_PRETRIP

    def _restart_34(self, point: LatLng, label: str) -> None:
        self._emit(
            "SB",
            RESTART_34_HOURS,
            point=point,
            label=label,
            remark="34-hour restart",
            stop_type="restart_34",
            stationary=True,
        )
        self.state.cycle_remaining = CYCLE_LIMIT_HOURS
        self.state.window_start = None
        self.state.driving_in_window = 0.0
        self.state.driving_since_break = 0.0
        self.state.needs_pretrip = ENABLE_PRETRIP
        self.inserted_34h = True

    def ensure_cycle(self, needed: float, point: LatLng, label: str) -> None:
        if self.state.cycle_remaining + 1e-6 < needed:
            self._restart_34(point, label)

    def ensure_window_for_drive(
        self, drive_h: float, point: LatLng, label: str
    ) -> None:
        """Insert daily reset if drive_h would break 11h or 14h rules."""
        for _ in range(4):
            st = self.state
            # Opening window with this drive
            if st.window_start is None:
                # fresh window — only check drive vs 11 and 14
                if drive_h > DAILY_DRIVE_LIMIT_HOURS + 1e-6:
                    # can't do more than 11 in one chunk; caller chunks
                    return
                return

            elapsed = (st.t - st.window_start).total_seconds() / 3600.0
            if (
                st.driving_in_window + drive_h > DAILY_DRIVE_LIMIT_HOURS + 1e-6
                or elapsed + drive_h > DUTY_WINDOW_HOURS + 1e-6
            ):
                self._daily_reset(point, label)
                continue
            return

    def ensure_break_before_drive(
        self, drive_h: float, point: LatLng, label: str, fuel_due: bool
    ) -> None:
        if self.state.driving_since_break + drive_h <= BREAK_AFTER_DRIVE_HOURS + 1e-6:
            return
        if fuel_due or self.state.miles_since_fuel >= FUEL_EVERY_MILES - 1e-6:
            self.ensure_cycle(FUEL_DURATION_HOURS, point, label)
            self.ensure_on_fits(FUEL_DURATION_HOURS, point, label)
            self._emit(
                "ON",
                FUEL_DURATION_HOURS,
                point=point,
                label=label,
                remark="Fuel stop",
                stop_type="fuel",
                stationary=True,
            )
        else:
            self._emit(
                "OFF",
                BREAK_DURATION_HOURS,
                point=point,
                label=label,
                remark="30-minute break",
                stop_type="break_30",
                stationary=True,
            )

    def ensure_on_fits(self, on_h: float, point: LatLng, label: str) -> None:
        """ON burns 14h window; if window nearly exhausted for later driving, reset first."""
        st = self.state
        if st.window_start is None:
            return
        elapsed = (st.t - st.window_start).total_seconds() / 3600.0
        if elapsed + on_h > DUTY_WINDOW_HOURS + 1e-6:
            # still allowed to be ON after 14h, but we prefer reset before heavy ON
            # only reset if we'd have no room to drive after
            if elapsed >= DUTY_WINDOW_HOURS - 0.01:
                self._daily_reset(point, label)

    def ensure_pretrip(self, point: LatLng, label: str) -> None:
        if not self.state.needs_pretrip or not ENABLE_PRETRIP:
            return
        self.ensure_cycle(PRETRIP_DURATION_HOURS, point, label)
        self.ensure_on_fits(PRETRIP_DURATION_HOURS, point, label)
        self._emit(
            "ON",
            PRETRIP_DURATION_HOURS,
            point=point,
            label=label,
            remark="Pre-trip inspection",
            stop_type="pretrip",
            stationary=True,
        )
        self.state.needs_pretrip = False

    def drive_leg(self, leg: RouteLeg) -> None:
        if leg.distance_miles <= 0.05:
            return

        self.geometry.extend(leg.geometry)
        miles_left = leg.distance_miles
        miles_done = 0.0
        dest_label = leg.destination.label
        speed = leg.distance_miles / max(leg.duration_hours, 1e-6)
        if speed <= 1e-6:
            speed = AVG_SPEED_MPH

        def here_label(pt: LatLng) -> str:
            return reverse_geocode_label(pt, fallback=leg.origin.label)

        guard = 0
        while miles_left > 0.05 and guard < 500:
            guard += 1
            point = interpolate_along_route(leg, miles_done)
            label = here_label(point)

            fuel_room = FUEL_EVERY_MILES - self.state.miles_since_fuel
            if fuel_room <= 0.05:
                self.ensure_cycle(FUEL_DURATION_HOURS, point, label)
                self.ensure_on_fits(FUEL_DURATION_HOURS, point, label)
                self._emit(
                    "ON",
                    FUEL_DURATION_HOURS,
                    point=point,
                    label=label,
                    remark="Fuel stop",
                    stop_type="fuel",
                    stationary=True,
                )
                continue

            # max hours legally left this window
            if self.state.window_start is None:
                window_room = DUTY_WINDOW_HOURS
            else:
                elapsed = (self.state.t - self.state.window_start).total_seconds() / 3600.0
                window_room = max(0.0, DUTY_WINDOW_HOURS - elapsed)

            drive11_room = max(0.0, DAILY_DRIVE_LIMIT_HOURS - self.state.driving_in_window)
            break_room = max(0.0, BREAK_AFTER_DRIVE_HOURS - self.state.driving_since_break)

            max_h = min(window_room, drive11_room, break_room)
            if max_h <= 0.02:
                if break_room <= 0.02:
                    self.ensure_break_before_drive(0.1, point, label, fuel_due=fuel_room < 50)
                else:
                    self.ensure_window_for_drive(0.1, point, label)
                continue

            max_mi = min(miles_left, fuel_room, max_h * speed)
            if max_mi <= 0.05:
                if fuel_room <= max_mi + 0.1:
                    self.ensure_cycle(FUEL_DURATION_HOURS, point, label)
                    self._emit(
                        "ON",
                        FUEL_DURATION_HOURS,
                        point=point,
                        label=label,
                        remark="Fuel stop",
                        stop_type="fuel",
                        stationary=True,
                    )
                else:
                    self.ensure_break_before_drive(1.0, point, label, False)
                continue

            drive_h = max_mi / speed
            self.ensure_cycle(drive_h, point, label)
            self.ensure_window_for_drive(drive_h, point, label)
            point = interpolate_along_route(leg, miles_done)
            label = here_label(point)
            if self.state.window_start is not None:
                elapsed = (self.state.t - self.state.window_start).total_seconds() / 3600.0
                window_room = max(0.0, DUTY_WINDOW_HOURS - elapsed)
                drive11_room = max(0.0, DAILY_DRIVE_LIMIT_HOURS - self.state.driving_in_window)
                break_room = max(0.0, BREAK_AFTER_DRIVE_HOURS - self.state.driving_since_break)
                max_h = min(window_room, drive11_room, break_room)
                if max_h <= 0.02:
                    continue
                max_mi = min(
                    miles_left,
                    FUEL_EVERY_MILES - self.state.miles_since_fuel,
                    max_h * speed,
                )
                if max_mi <= 0.05:
                    continue
                drive_h = max_mi / speed

            fuel_due = (self.state.miles_since_fuel + max_mi) >= FUEL_EVERY_MILES - 1e-6
            self.ensure_break_before_drive(drive_h, point, label, fuel_due)
            self.ensure_pretrip(point, label)

            end_point = interpolate_along_route(leg, miles_done + max_mi)
            end_label = here_label(end_point)
            self._emit(
                "D",
                drive_h,
                miles=max_mi,
                point=end_point,
                label=end_label,
                remark=f"Drive toward {dest_label}",
                stop_type=None,
                stationary=False,
            )
            miles_left -= max_mi
            miles_done += max_mi

            if self.state.miles_since_fuel >= FUEL_EVERY_MILES - 0.05:
                fp = interpolate_along_route(leg, miles_done)
                fl = here_label(fp)
                self.ensure_cycle(FUEL_DURATION_HOURS, fp, fl)
                self._emit(
                    "ON",
                    FUEL_DURATION_HOURS,
                    point=fp,
                    label=fl,
                    remark="Fuel stop",
                    stop_type="fuel",
                    stationary=True,
                )

    def on_duty_block(
        self,
        hours: float,
        point: LatLng,
        label: str,
        remark: str,
        stop_type: StopType,
    ) -> None:
        self.ensure_cycle(hours, point, label)
        self.ensure_on_fits(hours, point, label)
        self._emit(
            "ON",
            hours,
            point=point,
            label=label,
            remark=remark,
            stop_type=stop_type,
            stationary=True,
        )


def _default_start() -> datetime:
    now = datetime.now(TZ)
    return now.replace(hour=6, minute=0, second=0, microsecond=0)


def plan_trip(
    current_location: str,
    pickup_location: str,
    dropoff_location: str,
    current_cycle_used_hours: float,
    start_datetime: datetime | None = None,
) -> PlanResult:
    if not (0 <= current_cycle_used_hours <= CYCLE_LIMIT_HOURS):
        raise ValidationFailed(
            "current_cycle_used_hours must be between 0 and 70",
            fields={
                "current_cycle_used_hours": [
                    "Ensure this value is between 0 and 70."
                ]
            },
        )

    current = geocode_place(current_location, "current_location")
    pickup = geocode_place(pickup_location, "pickup_location")
    dropoff = geocode_place(dropoff_location, "dropoff_location")

    if nearly_same(pickup.point, dropoff.point, SAME_POINT_EPSILON_MILES):
        raise ValidationFailed(
            "Pickup and dropoff must be different locations",
            fields={
                "dropoff_location": [
                    "Pickup and dropoff must be different locations."
                ]
            },
        )

    start = start_datetime
    if start is None:
        start = _default_start()
    elif start.tzinfo is None:
        start = start.replace(tzinfo=TZ)
    else:
        start = start.astimezone(TZ)
    start = start.replace(second=0, microsecond=0)

    planner = Planner(current_cycle_used_hours, start)
    planner.stops.append(
        {
            "type": "current",
            "label": current.label,
            "lat": current.point.lat,
            "lng": current.point.lng,
            "arrival": start.isoformat(),
            "departure": start.isoformat(),
            "duration_hours": 0,
        }
    )

    # Empty reposition leg
    if not nearly_same(current.point, pickup.point, SAME_POINT_EPSILON_MILES):
        empty, used_car = build_route(current, pickup)
        planner.used_car = planner.used_car or used_car
        planner.drive_leg(empty)

    # Pickup
    planner.ensure_pretrip(pickup.point, pickup.label)
    planner.on_duty_block(
        PICKUP_DURATION_HOURS,
        pickup.point,
        pickup.label,
        "Pickup",
        "pickup",
    )

    # Loaded leg
    loaded, used_car2 = build_route(pickup, dropoff)
    planner.used_car = planner.used_car or used_car2
    planner.drive_leg(loaded)

    # Dropoff
    planner.on_duty_block(
        DROPOFF_DURATION_HOURS,
        dropoff.point,
        dropoff.label,
        "Dropoff",
        "dropoff",
    )

    timeline = planner.segments
    daily_logs = build_daily_logs(timeline, current_cycle_used_hours)
    hard = verify(timeline, current_cycle_used_hours)
    if hard:
        raise PlanIntegrityError(
            "; ".join(f"{v.code}: {v.message}" for v in hard[:5]),
            fields={"violations": [v.code for v in hard]},
        )

    instructions = build_instructions(timeline)

    total_miles = sum(s.miles for s in timeline)
    total_drive = sum(
        (s.end - s.start).total_seconds() / 3600.0 for s in timeline if s.status == "D"
    )
    total_on = sum(
        (s.end - s.start).total_seconds() / 3600.0
        for s in timeline
        if s.status in ("D", "ON")
    )
    total_off = sum(
        (s.end - s.start).total_seconds() / 3600.0 for s in timeline if s.status == "OFF"
    )
    total_sb = sum(
        (s.end - s.start).total_seconds() / 3600.0 for s in timeline if s.status == "SB"
    )

    assumptions = [
        "Property-carrying driver, 70h/8-day cycle",
        "No adverse driving conditions",
        "Driver starts after ≥10 consecutive hours off",
        "70/8 approximated as remaining-hours pool (no prior day history)",
        f"Home terminal timezone: {HOME_TERMINAL_TZ}",
        "Fuel every 1000 miles, 0.5h ON",
        "Pickup/dropoff 1.0h ON each",
        "Pre-trip 0.5h ON before first drive of each duty window (log realism)",
        "Daily reset modeled as 0.5h OFF + 9.5h SB (≥10h consecutive)",
        "No split-sleeper-berth optimization (full 10h/34h resets only)",
    ]
    if planner.used_car:
        assumptions.append("Used car routing profile (HGV unavailable)")

    # Deduplicate geometry
    geo_pairs = [[p.lat, p.lng] for p in planner.geometry]
    if not geo_pairs:
        geo_pairs = [
            [current.point.lat, current.point.lng],
            [pickup.point.lat, pickup.point.lng],
            [dropoff.point.lat, dropoff.point.lng],
        ]

    return PlanResult(
        summary={
            "total_miles": round(total_miles, 1),
            "total_driving_hours": round(total_drive, 2),
            "total_on_duty_hours": round(total_on, 2),
            "total_off_hours": round(total_off, 2),
            "total_sb_hours": round(total_sb, 2),
            "days": len(daily_logs),
            "cycle_remaining_end": round(planner.state.cycle_remaining, 2),
            "inserted_34h_restart": planner.inserted_34h,
            "start": timeline[0].start.isoformat() if timeline else start.isoformat(),
            "end": timeline[-1].end.isoformat() if timeline else start.isoformat(),
        },
        places={
            "current": {
                "label": current.label,
                "lat": current.point.lat,
                "lng": current.point.lng,
            },
            "pickup": {
                "label": pickup.label,
                "lat": pickup.point.lat,
                "lng": pickup.point.lng,
            },
            "dropoff": {
                "label": dropoff.label,
                "lat": dropoff.point.lat,
                "lng": dropoff.point.lng,
            },
        },
        route={"geometry": geo_pairs, "stops": planner.stops},
        instructions=instructions,
        timeline=timeline,
        daily_logs=daily_logs,
        assumptions=assumptions,
        used_car_routing=planner.used_car,
    )
