"""
Extra edge-case break suite — run after stress_break.py
Targets: NaN cycle, CORS-ish headers, midnight logs, verifier vs planner,
instruction completeness, stop lat/lng, concurrent plans.
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from zoneinfo import ZoneInfo

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

import httpx
from planning.constants import HOME_TERMINAL_TZ
from planning.hos_planner import plan_trip
from planning.hos_verifier import verify

BASE = os.getenv("STRESS_API", "http://127.0.0.1:8080")
TZ = ZoneInfo(HOME_TERMINAL_TZ)
findings = []


def rec(feature, case, broke, expected, actual, root_cause, severity="high"):
    findings.append(
        {
            "feature": feature,
            "case": case,
            "broke": broke,
            "severity": "pass" if not broke else severity,
            "expected": expected,
            "actual": actual,
            "root_cause": root_cause,
        }
    )
    tag = "BROKE" if broke else "OK"
    print(f"[{tag}] {feature} :: {case}")


def post(body, timeout=180):
    with httpx.Client(timeout=timeout) as c:
        r = c.post(f"{BASE}/api/plan/", json=body)
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, {"raw": r.text[:400]}


def main():
    # 1) NaN / non-numeric cycle
    code, data = post(
        {
            "current_location": "Dallas, TX",
            "pickup_location": "Dallas, TX",
            "dropoff_location": "Houston, TX",
            "current_cycle_used_hours": "abc",
        }
    )
    rec(
        "Validation",
        "cycle=abc",
        code != 400,
        "400 VALIDATION_ERROR",
        f"{code} {data}",
        "Serializer should reject non-float cycle",
    )

    # 2) null cycle
    code, data = post(
        {
            "current_location": "Dallas, TX",
            "pickup_location": "Dallas, TX",
            "dropoff_location": "Houston, TX",
            "current_cycle_used_hours": None,
        }
    )
    rec(
        "Validation",
        "cycle=null",
        code != 400,
        "400",
        f"{code}",
        "Null cycle must 400",
    )

    # 3) start_datetime with seconds (UI fix path)
    code, data = post(
        {
            "current_location": "Dallas, TX",
            "pickup_location": "Dallas, TX",
            "dropoff_location": "Houston, TX",
            "current_cycle_used_hours": 10,
            "start_datetime": "2026-08-25T06:00:00",
        }
    )
    rec(
        "Plan",
        "start with seconds",
        code != 200,
        "200",
        f"{code}",
        "DRF DateTimeField parse",
    )

    # 4) start at 23:30 to force midnight log split quickly
    try:
        r = plan_trip(
            "Dallas, TX",
            "Dallas, TX",
            "Houston, TX",
            10,
            datetime(2026, 8, 10, 23, 30, tzinfo=TZ),
        )
        days = len(r.daily_logs)
        sums_ok = all(abs(sum(l.totals.values()) - 24) < 0.06 for l in r.daily_logs)
        hard = [v.code for v in verify(r.timeline, 10) if v.code != "DAY_24"]
        broke = days < 2 or not sums_ok or bool(hard)
        rec(
            "Midnight split",
            "start 23:30 Dallas-Houston",
            broke,
            ">=2 log days, each ~24h, verifier clean",
            f"days={days} sums_ok={sums_ok} viol={hard}",
            "logs_builder midnight split / padding" if broke else "n/a",
            severity="critical",
        )
    except Exception as e:
        rec(
            "Midnight split",
            "start 23:30",
            True,
            "success",
            str(e),
            "Exception near midnight planning",
            "critical",
        )

    # 5) All stops need coordinates for map
    code, data = post(
        {
            "current_location": "Chicago, IL",
            "pickup_location": "Chicago, IL",
            "dropoff_location": "Denver, CO",
            "current_cycle_used_hours": 12,
            "start_datetime": "2026-08-25T06:00:00",
        }
    )
    if code == 200:
        missing = [
            s
            for s in data["route"]["stops"]
            if s.get("type") not in ("current",) and (s.get("lat") is None or s.get("lng") is None)
        ]
        # current is fine; fuel/break should have coords
        bad = [s for s in data["route"]["stops"] if s.get("lat") is None]
        rec(
            "Map stops",
            "all stops have lat/lng",
            bool(bad),
            "every stop has lat/lng",
            f"missing={bad}",
            "planner emit without point" if bad else "n/a",
        )
        # instructions with drive should have miles
        drives = [i for i in data["instructions"] if i.get("action") == "drive"]
        no_miles = [i for i in drives if i.get("miles") is None]
        rec(
            "Instructions",
            "drive entries have miles",
            bool(no_miles),
            "miles present on drive",
            f"count={len(no_miles)}",
            "instructions builder" if no_miles else "n/a",
        )
        # grid segments cover 0-1440 roughly
        for log in data["daily_logs"]:
            segs = log["grid_segments"]
            if not segs:
                rec("Logs SVG data", f"grid {log['date']}", True, "non-empty", "empty", "logs_builder")
                break
            else:
                span = max(s["end_minute"] for s in segs) - min(s["start_minute"] for s in segs)
                rec(
                    "Logs SVG data",
                    f"grid span {log['date']}",
                    span < 1000,
                    "near-full day coverage",
                    f"span_minutes={span}",
                    "padding missing overnight OFF" if span < 1000 else "n/a",
                    severity="medium",
                )
    else:
        rec("Map stops", "chicago-denver plan", True, "200", str(code), "plan failed")

    # 6) Concurrent requests (free-tier realism)
    def one(i):
        return post(
            {
                "current_location": "Dallas, TX",
                "pickup_location": "Dallas, TX",
                "dropoff_location": "Houston, TX",
                "current_cycle_used_hours": 10 + i,
                "start_datetime": "2026-08-25T06:00:00",
            },
            timeout=180,
        )

    codes = []
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = [ex.submit(one, i) for i in range(3)]
        for f in as_completed(futs):
            try:
                codes.append(f.result()[0])
            except Exception as e:
                codes.append(str(e))
    broke = any(c != 200 for c in codes)
    rec(
        "Concurrency",
        "3 parallel short plans",
        broke,
        "all 200",
        str(codes),
        "thread-safety / httpx client / cache lock" if broke else "n/a",
        severity="medium",
    )

    # 7) Extremely high precision cycle
    code, data = post(
        {
            "current_location": "Dallas, TX",
            "pickup_location": "Dallas, TX",
            "dropoff_location": "Houston, TX",
            "current_cycle_used_hours": 10.123456789,
            "start_datetime": "2026-08-25T06:00:00",
        }
    )
    rec(
        "Validation",
        "high precision cycle",
        code != 200,
        "200 accepted float",
        f"{code}",
        "float serializer",
    )

    # 8) Phoenix to Atlanta long-ish empty+loaded? current=pickup
    try:
        r = plan_trip(
            "Phoenix, AZ",
            "Phoenix, AZ",
            "Atlanta, GA",
            20,
            datetime(2026, 8, 10, 6, 0, tzinfo=TZ),
        )
        hard = [v.code for v in verify(r.timeline, 20) if v.code != "DAY_24"]
        fuels = [s for s in r.route["stops"] if s["type"] == "fuel"]
        need_fuel = r.summary["total_miles"] > 1000
        broke = bool(hard) or (need_fuel and not fuels)
        rec(
            "HOS long haul",
            "Phoenix-Atlanta",
            broke,
            "legal + fuel if >1000mi",
            f"mi={r.summary['total_miles']} fuels={len(fuels)} viol={hard}",
            "planner" if broke else "n/a",
            severity="critical",
        )
    except Exception as e:
        rec(
            "HOS long haul",
            "Phoenix-Atlanta",
            True,
            "success",
            str(e),
            traceback.format_exc()[-400:],
            "critical",
        )

    # Write append report
    out = os.path.join(os.path.dirname(__file__), "..", "BREAK_REPORT_ROUND2.md")
    broke_list = [f for f in findings if f["broke"]]
    lines = [
        "# Break Report Round 2 — Edge cases",
        "",
        f"**Generated:** {datetime.now().isoformat(timespec='seconds')}",
        f"**API:** `{BASE}`",
        f"**Cases:** {len(findings)} · **Broke:** {len(broke_list)} · **Passed:** {len(findings)-len(broke_list)}",
        "",
        "## Failures",
        "",
    ]
    if not broke_list:
        lines.append("_None — all edge cases passed._")
    else:
        for i, f in enumerate(broke_list, 1):
            lines += [
                f"### {i}. [{f['severity'].upper()}] {f['feature']} — {f['case']}",
                "",
                f"- **Expected:** {f['expected']}",
                f"- **Actual:** {f['actual']}",
                f"- **Root cause:** {f['root_cause']}",
                "",
            ]
    lines += ["", "## All results", ""]
    for f in findings:
        lines.append(
            f"- [{'BROKE' if f['broke'] else 'OK'}] **{f['feature']}** / {f['case']}: {f['actual']}"
        )
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print(f"Wrote {out}")
    return 1 if broke_list else 0


if __name__ == "__main__":
    raise SystemExit(main())
