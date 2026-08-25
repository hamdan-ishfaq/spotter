"""Human-readable route instructions from duty timeline."""

from __future__ import annotations

from .types import ActionType, DutySegment, Instruction


def build_instructions(timeline: list[DutySegment]) -> list[Instruction]:
    out: list[Instruction] = []
    seq = 1
    for seg in timeline:
        action: ActionType | None = None
        text = seg.remark or seg.status
        if seg.stop_type == "pretrip":
            action = "pretrip"
            text = f"Pre-trip inspection ({_h(seg):.2f} h) — {seg.location_label}"
        elif seg.stop_type == "pickup":
            action = "pickup"
            text = f"Pickup freight ({_h(seg):.2f} h) — {seg.location_label}"
        elif seg.stop_type == "dropoff":
            action = "dropoff"
            text = f"Dropoff freight ({_h(seg):.2f} h) — {seg.location_label}"
        elif seg.stop_type == "fuel":
            action = "fuel"
            text = f"Fuel stop ({_h(seg):.2f} h ON) — {seg.location_label}"
        elif seg.stop_type == "break_30":
            action = "break_30"
            text = f"30-minute break (OFF) — {seg.location_label}"
        elif seg.stop_type in ("rest_off", "rest_sb"):
            if seg.stop_type == "rest_off":
                action = "rest_10"
                text = f"Begin 10h reset (OFF) — {seg.location_label}"
            else:
                # skip duplicate rest_sb as separate rest_10 if previous was rest_off
                if out and out[-1].action == "rest_10":
                    out[-1] = Instruction(
                        seq=out[-1].seq,
                        action="rest_10",
                        text=f"10-hour sleeper berth reset — {seg.location_label}",
                        start=out[-1].start,
                        end=seg.end.isoformat(),
                        status=seg.status,
                        location_label=seg.location_label,
                        miles=None,
                        lat=seg.point.lat if seg.point else None,
                        lng=seg.point.lng if seg.point else None,
                    )
                    continue
                action = "rest_10"
                text = f"Sleeper berth reset — {seg.location_label}"
        elif seg.stop_type == "restart_34":
            action = "restart_34"
            text = f"34-hour restart (cycle reset) — {seg.location_label}"
        elif seg.status == "D":
            action = "drive"
            text = (
                f"Drive {_h(seg):.2f} h ({seg.miles:.1f} mi) toward {seg.location_label}"
            )
        else:
            continue

        out.append(
            Instruction(
                seq=seq,
                action=action,
                text=text,
                start=seg.start.isoformat(),
                end=seg.end.isoformat(),
                status=seg.status,
                location_label=seg.location_label,
                miles=seg.miles if seg.status == "D" else None,
                lat=seg.point.lat if seg.point else None,
                lng=seg.point.lng if seg.point else None,
            )
        )
        seq += 1
    return out


def _h(seg: DutySegment) -> float:
    return (seg.end - seg.start).total_seconds() / 3600.0
