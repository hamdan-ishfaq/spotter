from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

DutyStatus = Literal["OFF", "SB", "D", "ON"]
StopType = Literal[
    "current",
    "pickup",
    "dropoff",
    "fuel",
    "break_30",
    "rest_off",
    "rest_sb",
    "restart_34",
    "pretrip",
]
ActionType = Literal[
    "drive",
    "pickup",
    "dropoff",
    "fuel",
    "break_30",
    "rest_10",
    "restart_34",
    "pretrip",
]


@dataclass
class LatLng:
    lat: float
    lng: float


@dataclass
class Place:
    query: str
    label: str
    point: LatLng


@dataclass
class RouteLeg:
    origin: Place
    destination: Place
    distance_miles: float
    duration_hours: float
    geometry: list[LatLng]
    cumulative_miles: list[float]


@dataclass
class DutySegment:
    status: DutyStatus
    start: datetime
    end: datetime
    miles: float
    point: LatLng | None
    location_label: str
    remark: str
    stop_type: StopType | None
    stationary: bool


@dataclass
class HosState:
    t: datetime
    window_start: datetime | None
    driving_in_window: float
    driving_since_break: float
    miles_since_fuel: float
    cycle_remaining: float
    needs_pretrip: bool


@dataclass
class Violation:
    code: str
    message: str
    at: datetime | None = None


@dataclass
class Remark:
    time: str
    location_label: str
    text: str


@dataclass
class GridSeg:
    status: DutyStatus
    start_minute: int
    end_minute: int
    bracket: bool


@dataclass
class DailyLog:
    date: str
    from_location: str
    to_location: str
    total_miles_driving: float
    segments: list[DutySegment]
    totals: dict[str, float]
    remarks: list[Remark]
    recap: dict[str, Any]
    grid_segments: list[GridSeg]
    header: dict[str, str]


@dataclass
class Instruction:
    seq: int
    action: ActionType
    text: str
    start: str
    end: str
    status: DutyStatus
    location_label: str
    miles: float | None = None
    lat: float | None = None
    lng: float | None = None


@dataclass
class PlanResult:
    summary: dict[str, Any]
    places: dict[str, Any]
    route: dict[str, Any]
    instructions: list[Instruction]
    timeline: list[DutySegment]
    daily_logs: list[DailyLog]
    assumptions: list[str]
    used_car_routing: bool = False
    extras: dict[str, Any] = field(default_factory=dict)
