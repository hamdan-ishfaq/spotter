"""
Extensive break-the-app stress harness.
Runs against live API (default http://127.0.0.1:8001) and records findings.
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

import httpx
from planning.hos_planner import plan_trip
from planning.hos_verifier import verify
from planning.geocode import geocode_place
from planning.routing import build_route
from planning.exceptions import PlanningError

BASE = os.getenv("STRESS_API", "http://127.0.0.1:8080")


@dataclass
class Finding:
    feature: str
    case: str
    severity: str  # critical | high | medium | low | info | pass
    broke: bool
    expected: str
    actual: str
    root_cause: str
    evidence: str = ""


findings: list[Finding] = []


def record(**kwargs):
    findings.append(Finding(**kwargs))
    status = "BROKE" if kwargs.get("broke") else "OK"
    print(f"[{status}] {kwargs['feature']} :: {kwargs['case']} ({kwargs['severity']})".encode("ascii", "replace").decode("ascii"))


def http_json(method: str, path: str, body: dict | None = None, timeout: float = 120.0):
    url = f"{BASE}{path}"
    with httpx.Client(timeout=timeout) as client:
        if method == "GET":
            r = client.get(url)
        else:
            r = client.post(url, json=body)
        try:
            data = r.json()
        except Exception:
            data = {"raw": r.text[:500]}
        return r.status_code, data


# ---------------------------------------------------------------------------
# 1. Health
# ---------------------------------------------------------------------------
def test_health():
    try:
        code, data = http_json("GET", "/api/health/")
        if code != 200 or data.get("status") != "ok":
            record(
                feature="Health",
                case="GET /api/health/",
                severity="critical",
                broke=True,
                expected="200 {status:ok}",
                actual=f"{code} {data}",
                root_cause="API not reachable or health view broken",
            )
        else:
            record(
                feature="Health",
                case="GET /api/health/",
                severity="pass",
                broke=False,
                expected="200 ok",
                actual=str(data),
                root_cause="n/a",
            )
    except Exception as e:
        record(
            feature="Health",
            case="GET /api/health/",
            severity="critical",
            broke=True,
            expected="200 ok",
            actual=str(e),
            root_cause="Server down / wrong port / firewall",
            evidence=traceback.format_exc(),
        )


# ---------------------------------------------------------------------------
# 2. Validation / inputs
# ---------------------------------------------------------------------------
def test_validation():
    cases = [
        (
            "cycle > 70",
            {
                "current_location": "Dallas, TX",
                "pickup_location": "Dallas, TX",
                "dropoff_location": "Houston, TX",
                "current_cycle_used_hours": 80,
            },
            400,
        ),
        (
            "cycle < 0",
            {
                "current_location": "Dallas, TX",
                "pickup_location": "Dallas, TX",
                "dropoff_location": "Houston, TX",
                "current_cycle_used_hours": -1,
            },
            400,
        ),
        (
            "missing pickup",
            {
                "current_location": "Dallas, TX",
                "dropoff_location": "Houston, TX",
                "current_cycle_used_hours": 10,
            },
            400,
        ),
        (
            "empty strings",
            {
                "current_location": "",
                "pickup_location": "",
                "dropoff_location": "",
                "current_cycle_used_hours": 10,
            },
            400,
        ),
        (
            "same pickup and dropoff",
            {
                "current_location": "Dallas, TX",
                "pickup_location": "Dallas, TX",
                "dropoff_location": "Dallas, TX",
                "current_cycle_used_hours": 10,
                "start_datetime": "2026-08-25T06:00:00",
            },
            400,
        ),
        (
            "garbage location",
            {
                "current_location": "zzzxqnotacity999",
                "pickup_location": "zzzxqnotacity999",
                "dropoff_location": "yyyqnotacity888",
                "current_cycle_used_hours": 10,
                "start_datetime": "2026-08-25T06:00:00",
            },
            422,
        ),
    ]
    for name, body, expect in cases:
        code, data = http_json("POST", "/api/plan/", body)
        ok = code == expect
        # same pickup/dropoff might be 400 validation
        record(
            feature="Input validation",
            case=name,
            severity="high" if not ok else "pass",
            broke=not ok,
            expected=f"HTTP {expect}",
            actual=f"HTTP {code}: {json.dumps(data)[:300]}",
            root_cause=(
                "n/a"
                if ok
                else "Serializer/planner validation gap or wrong status mapping"
            ),
        )


# ---------------------------------------------------------------------------
# 3. Happy path demos
# ---------------------------------------------------------------------------
def test_demos():
    demos = [
        (
            "Short Dallas-Houston",
            {
                "current_location": "Dallas, TX",
                "pickup_location": "Dallas, TX",
                "dropoff_location": "Houston, TX",
                "current_cycle_used_hours": 10,
                "start_datetime": "2026-08-25T06:00:00",
            },
        ),
        (
            "Long Chicago-LA",
            {
                "current_location": "Chicago, IL",
                "pickup_location": "Chicago, IL",
                "dropoff_location": "Los Angeles, CA",
                "current_cycle_used_hours": 15,
                "start_datetime": "2026-08-25T06:00:00",
            },
        ),
        (
            "Cycle pressure 68",
            {
                "current_location": "Dallas, TX",
                "pickup_location": "Dallas, TX",
                "dropoff_location": "Houston, TX",
                "current_cycle_used_hours": 68,
                "start_datetime": "2026-08-25T06:00:00",
            },
        ),
    ]
    for name, body in demos:
        code, data = http_json("POST", "/api/plan/", body, timeout=180)
        if code != 200:
            record(
                feature="Plan demos",
                case=name,
                severity="critical",
                broke=True,
                expected="200 with plan",
                actual=f"{code} {json.dumps(data)[:400]}",
                root_cause="Planner/route/geocode failure under demo inputs",
            )
            continue

        issues = []
        summary = data.get("summary") or {}
        logs = data.get("daily_logs") or []
        route = data.get("route") or {}
        instructions = data.get("instructions") or []
        assumptions = data.get("assumptions") or []

        if not route.get("geometry"):
            issues.append("missing route geometry")
        if not route.get("stops"):
            issues.append("missing stops")
        if not instructions:
            issues.append("missing instructions")
        if not logs:
            issues.append("missing daily logs")
        if not assumptions:
            issues.append("missing assumptions")

        for log in logs:
            tot = sum((log.get("totals") or {}).values())
            if abs(tot - 24.0) > 0.06:
                issues.append(f"log {log.get('date')} totals {tot} != 24")
            if not log.get("grid_segments"):
                issues.append(f"log {log.get('date')} missing grid_segments")
            recap = log.get("recap") or {}
            if "on_duty_today" not in recap:
                issues.append("recap missing on_duty_today")

        # pickup/dropoff 1h
        stops = route.get("stops") or []
        pu = [s for s in stops if s.get("type") == "pickup"]
        do = [s for s in stops if s.get("type") == "dropoff"]
        if len(pu) != 1:
            issues.append(f"pickup count {len(pu)}")
        elif abs(float(pu[0].get("duration_hours", 0)) - 1.0) > 0.05:
            issues.append(f"pickup hours {pu[0].get('duration_hours')}")
        if len(do) != 1:
            issues.append(f"dropoff count {len(do)}")

        if name.startswith("Long") and len(logs) < 2:
            issues.append(f"expected multi-day logs, got {len(logs)}")
        if name.startswith("Long"):
            fuels = [s for s in stops if s.get("type") == "fuel"]
            if summary.get("total_miles", 0) > 1000 and not fuels:
                issues.append("no fuel stop on >1000 mi trip")

        if name.startswith("Cycle"):
            if not (
                summary.get("inserted_34h_restart")
                or any(s.get("type") == "restart_34" for s in stops)
                or any(s.get("stop_type") == "restart_34" for s in data.get("timeline") or [])
            ):
                issues.append("expected 34h restart at cycle 68")

        record(
            feature="Plan demos",
            case=name,
            severity="high" if issues else "pass",
            broke=bool(issues),
            expected="legal plan with map/logs/instructions",
            actual=f"miles={summary.get('total_miles')} days={summary.get('days')} issues={issues or 'none'}",
            root_cause=(
                "n/a"
                if not issues
                else "See issues list - likely planner edge or assertion mismatch"
            ),
            evidence=json.dumps(issues),
        )


# ---------------------------------------------------------------------------
# 4. Autocomplete
# ---------------------------------------------------------------------------
def test_autocomplete():
    cases = [
        ("empty", "", 200, 0),
        ("short", "Da", 200, 0),
        ("dallas", "Dallas", 200, None),  # None = any
        ("unicode", "道", 200, None),
    ]
    for name, q, expect_code, expect_len in cases:
        code, data = http_json("GET", f"/api/autocomplete/?q={q}")
        results = data.get("results") if isinstance(data, dict) else None
        broke = code != expect_code
        if expect_len is not None and isinstance(results, list) and len(results) != expect_len:
            # empty/short should be []
            if name in ("empty", "short") and len(results) != 0:
                broke = True
        record(
            feature="Autocomplete",
            case=name,
            severity="medium" if broke else "pass",
            broke=broke,
            expected=f"{expect_code}, len={expect_len}",
            actual=f"{code}, results={str(results)[:200]}",
            root_cause="n/a" if not broke else "Autocomplete proxy/cache/ORS behavior",
        )


# ---------------------------------------------------------------------------
# 5. HOS rule breaks via direct planner
# ---------------------------------------------------------------------------
def test_hos_invariants():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from planning.constants import HOME_TERMINAL_TZ, FUEL_EVERY_MILES

    TZ = ZoneInfo(HOME_TERMINAL_TZ)
    start = datetime(2026, 8, 10, 6, 0, tzinfo=TZ)

    # Empty reposition + long haul fuel
    try:
        r = plan_trip("Chicago, IL", "Chicago, IL", "Los Angeles, CA", 15, start)
        hard = [v for v in verify(r.timeline, 15) if v.code != "DAY_24"]
        miles = r.summary["total_miles"]
        fuels = [s for s in r.route["stops"] if s["type"] == "fuel"]
        # check no drive streak without break > 8 via verifier
        broke = bool(hard)
        # fuel spacing on timeline
        since = 0.0
        fuel_viol = False
        for seg in r.timeline:
            if seg.status == "D":
                since += seg.miles
                if since > FUEL_EVERY_MILES + 1:
                    fuel_viol = True
            if seg.stop_type == "fuel":
                since = 0.0
        if fuel_viol:
            broke = True
            hard.append(type("V", (), {"code": "FUEL_LOGIC", "message": "miles since fuel exceeded"})())

        record(
            feature="HOS invariants",
            case="Chicago-LA cycle15",
            severity="critical" if broke else "pass",
            broke=broke,
            expected="verifier clean + fuel before 1000mi",
            actual=f"miles={miles} fuels={len(fuels)} violations={[getattr(v,'code',v) for v in hard]}",
            root_cause="n/a" if not broke else "Planner chunking / fuel insertion bug",
        )
    except Exception as e:
        record(
            feature="HOS invariants",
            case="Chicago-LA cycle15",
            severity="critical",
            broke=True,
            expected="successful legal plan",
            actual=str(e),
            root_cause="Unhandled exception in planner",
            evidence=traceback.format_exc(),
        )

    # Current far from pickup (empty leg)
    try:
        r = plan_trip("Denver, CO", "Chicago, IL", "Atlanta, GA", 5, start)
        hard = [v for v in verify(r.timeline, 5) if v.code != "DAY_24"]
        record(
            feature="Empty reposition leg",
            case="Denver-Chicago pickup-Atlanta",
            severity="high" if hard else "pass",
            broke=bool(hard),
            expected="legal plan with empty + loaded legs",
            actual=f"miles={r.summary['total_miles']} viol={[v.code for v in hard]}",
            root_cause="n/a" if not hard else "Empty-leg HOS interaction bug",
        )
    except Exception as e:
        record(
            feature="Empty reposition leg",
            case="Denver-Chicago pickup-Atlanta",
            severity="critical",
            broke=True,
            expected="success",
            actual=str(e),
            root_cause="Planner/route failure on multi-leg",
            evidence=traceback.format_exc(),
        )

    # cycle 70 exact
    try:
        r = plan_trip("Dallas, TX", "Dallas, TX", "Houston, TX", 70, start)
        has_34 = r.summary.get("inserted_34h_restart") or any(
            s.stop_type == "restart_34" for s in r.timeline
        )
        hard = [v for v in verify(r.timeline, 70) if v.code != "DAY_24"]
        broke = (not has_34) or bool(hard)
        record(
            feature="Cycle at 70",
            case="cycle_used=70 must 34h restart",
            severity="high" if broke else "pass",
            broke=broke,
            expected="34h restart before on-duty",
            actual=f"restart={has_34} viol={[v.code for v in hard]}",
            root_cause="n/a" if not broke else "ensure_cycle not triggered at remaining=0",
        )
    except Exception as e:
        record(
            feature="Cycle at 70",
            case="cycle_used=70",
            severity="critical",
            broke=True,
            expected="plan with restart",
            actual=str(e),
            root_cause="Exception when cycle fully used",
            evidence=traceback.format_exc(),
        )


# ---------------------------------------------------------------------------
# 6. Log sheet data integrity
# ---------------------------------------------------------------------------
def test_logs():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from planning.constants import HOME_TERMINAL_TZ

    TZ = ZoneInfo(HOME_TERMINAL_TZ)
    r = plan_trip("Chicago, IL", "Chicago, IL", "Denver, CO", 12, datetime(2026, 8, 10, 6, 0, tzinfo=TZ))
    issues = []
    for log in r.daily_logs:
        tot = sum(log.totals.values())
        if abs(tot - 24.0) > 0.05:
            issues.append(f"{log.date} sum={tot}")
        # grid coverage
        if not log.grid_segments:
            issues.append(f"{log.date} empty grid")
        else:
            # brackets only on ON stationary
            for g in log.grid_segments:
                if g.bracket and g.status != "ON":
                    issues.append("bracket on non-ON")
        if log.recap.get("note") is None:
            issues.append("missing recap note")
        # remarks should exist for meaningful days
        if log.totals["drive"] > 0 and not log.remarks:
            issues.append(f"{log.date} drive but no remarks")

    record(
        feature="Daily logs",
            case="Chicago-Denver log integrity",
        severity="high" if issues else "pass",
        broke=bool(issues),
        expected="24h days, grid, remarks, computed recap",
        actual=str(issues or "ok"),
        root_cause="n/a" if not issues else "logs_builder padding/reconcile/remark bugs",
    )


# ---------------------------------------------------------------------------
# 7. Geocode / route edge
# ---------------------------------------------------------------------------
def test_geo_edge():
    # nearly same points
    try:
        a = geocode_place("Dallas, TX")
        leg, _ = build_route(a, a)
        record(
            feature="Routing",
            case="same origin/destination",
            severity="pass" if leg.distance_miles < 1 else "medium",
            broke=leg.distance_miles >= 1,
            expected="~0 mile leg",
            actual=f"{leg.distance_miles} mi",
            root_cause="n/a" if leg.distance_miles < 1 else "nearly_same not applied",
        )
    except Exception as e:
        record(
            feature="Routing",
            case="same origin/destination",
            severity="medium",
            broke=True,
            expected="0-mile leg",
            actual=str(e),
            root_cause="Route layer rejects identical points",
        )


# ---------------------------------------------------------------------------
# 8. Frontend static checks (build artifacts / source smells)
# ---------------------------------------------------------------------------
def test_frontend_source():
    root = os.path.join(os.path.dirname(__file__), "..", "frontend", "src")
    issues = []
    app = open(os.path.join(root, "App.tsx"), encoding="utf-8").read()
    if "Assumptions" not in app:
        issues.append("assumptions banner missing in App")
    log = open(os.path.join(root, "components", "DailyLogSheet.tsx"), encoding="utf-8").read()
    if "bracket" not in log:
        issues.append("DailyLogSheet missing bracket drawing")
    if "Remarks" not in log:
        issues.append("DailyLogSheet missing Remarks")
    form = open(os.path.join(root, "components", "TripForm.tsx"), encoding="utf-8").read()
    if "Demo" not in form:
        issues.append("TripForm missing demos")
    # datetime submit bug check
    if "toApiDateTime" not in form and "`${start}:00`" in form:
        issues.append(
            "TripForm appends :00 to datetime-local value unsafely"
        )
    elif "toApiDateTime" not in form and "start_datetime: start" in form:
        issues.append("TripForm missing toApiDateTime helper")

    record(
        feature="Frontend source",
        case="static integrity",
        severity="medium" if issues else "pass",
        broke=bool(issues),
        expected="assumptions, brackets, demos, safe datetime",
        actual=str(issues or "ok"),
        root_cause="n/a" if not issues else "UI implementation gaps / datetime formatting",
    )


# ---------------------------------------------------------------------------
# 9. API response contract
# ---------------------------------------------------------------------------
def test_contract():
    code, data = http_json(
        "POST",
        "/api/plan/",
        {
            "current_location": "Dallas, TX",
            "pickup_location": "Dallas, TX",
            "dropoff_location": "Houston, TX",
            "current_cycle_used_hours": 10,
            "start_datetime": "2026-08-25T06:00:00",
        },
    )
    required = ["summary", "places", "route", "instructions", "timeline", "daily_logs", "assumptions"]
    missing = [k for k in required if k not in (data or {})]
    pretrip_disclosed = any("Pre-trip" in a or "pre-trip" in a.lower() for a in (data.get("assumptions") or []))
    reset_disclosed = any("0.5h OFF" in a or "9.5h SB" in a for a in (data.get("assumptions") or []))
    extras = []
    if not pretrip_disclosed:
        extras.append("pre-trip not in assumptions")
    if not reset_disclosed:
        extras.append("OFF/SB reset split not in assumptions")

    broke = code != 200 or bool(missing) or bool(extras)
    record(
        feature="API contract",
        case="plan response shape + assumption disclosure",
        severity="high" if broke else "pass",
        broke=broke,
        expected="full keys + disclosed pretrip/reset",
        actual=f"code={code} missing={missing} extras={extras}",
        root_cause="n/a" if not broke else "Serializer/assumptions list incomplete",
    )


def write_report(path: str):
    broke = [f for f in findings if f.broke]
    passed = [f for f in findings if not f.broke]
    lines = []
    lines.append("# Break Report — Spotter HOS Trip Planner")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"**API base:** `{BASE}`")
    lines.append(f"**Cases run:** {len(findings)} · **Broke:** {len(broke)} · **Passed:** {len(passed)}")
    lines.append("")
    lines.append("## Executive summary")
    lines.append("")
    if not broke:
        lines.append("No hard breaks detected in this harness pass. See info/medium notes below if any.")
    else:
        lines.append("The following features failed under stress. Each item includes **root cause** analysis.")
    lines.append("")
    lines.append("## Failures (broke = true)")
    lines.append("")
    if not broke:
        lines.append("_None._")
    else:
        for i, f in enumerate(broke, 1):
            lines.append(f"### {i}. [{f.severity.upper()}] {f.feature} — {f.case}")
            lines.append("")
            lines.append(f"- **Expected:** {f.expected}")
            lines.append(f"- **Actual:** {f.actual}")
            lines.append(f"- **Root cause:** {f.root_cause}")
            if f.evidence:
                lines.append(f"- **Evidence:** `{f.evidence[:500]}`")
            lines.append("")

    lines.append("## Passed cases")
    lines.append("")
    for f in passed:
        lines.append(f"- **{f.feature}** / {f.case}: {f.actual}")
    lines.append("")
    lines.append("## Feature coverage matrix")
    lines.append("")
    lines.append("| Feature | Result | Notes |")
    lines.append("|---|---|---|")
    by_feat: dict[str, list[Finding]] = {}
    for f in findings:
        by_feat.setdefault(f.feature, []).append(f)
    for feat, items in by_feat.items():
        bad = [i for i in items if i.broke]
        status = "BROKEN" if bad else "OK"
        note = bad[0].root_cause if bad else f"{len(items)} cases ok"
        lines.append(f"| {feat} | {status} | {note} |")
    lines.append("")
    lines.append("## Recommended fixes (priority)")
    lines.append("")
    crit = [f for f in broke if f.severity == "critical"]
    high = [f for f in broke if f.severity == "high"]
    med = [f for f in broke if f.severity in ("medium", "low")]
    n = 1
    for group, label in ((crit, "Critical"), (high, "High"), (med, "Medium")):
        for f in group:
            lines.append(f"{n}. **{label} — {f.feature}/{f.case}:** {f.root_cause}")
            n += 1
    if n == 1:
        lines.append("1. Keep running this harness before each deploy.")
        lines.append("2. Add Playwright e2e for SVG log + map click sync (not covered by API harness).")
        lines.append("3. Fix datetime-local `:00` append edge if users paste full ISO strings.")
    lines.append("")
    lines.append("## Gaps this harness cannot fully break")
    lines.append("")
    lines.append("- Visual SVG alignment vs paper form (needs human/screenshot review)")
    lines.append("- Leaflet marker↔instruction sync (browser-only)")
    lines.append("- Render Free cold-start UX (needs deployed env)")
    lines.append("- ORS quota exhaustion (needs live key + rate limit)")
    lines.append("")

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print(f"\nWrote {path}")


def main():
    print(f"Stress API: {BASE}")
    test_health()
    if any(f.feature == "Health" and f.broke for f in findings):
        print("API down — continuing with in-process planner tests only where possible")
    else:
        test_validation()
        test_autocomplete()
        test_demos()
        test_contract()
    test_hos_invariants()
    test_logs()
    test_geo_edge()
    test_frontend_source()
    out = os.path.join(os.path.dirname(__file__), "..", "BREAK_REPORT.md")
    write_report(os.path.abspath(out))


if __name__ == "__main__":
    main()
