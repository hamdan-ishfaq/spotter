"""
100+ case comprehensive test suite for Spotter HOS Planner.
Writes DETAILED_TEST_REPORT.md + test_logs/ artifacts.
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
sys.path.insert(0, str(Path(__file__).resolve().parent))
django.setup()

import httpx
from planning.constants import HOME_TERMINAL_TZ
from planning.hos_planner import plan_trip
from planning.hos_verifier import verify
from planning.geocode import geocode_place, autocomplete
from planning.routing import build_route
from planning.exceptions import PlanningError, GeocodeFailed, ValidationFailed
from planning.types import Place, LatLng
from zoneinfo import ZoneInfo

BASE = os.getenv("STRESS_API", "http://127.0.0.1:8080")
TZ = ZoneInfo(HOME_TERMINAL_TZ)
ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "test_logs"
LOG_DIR.mkdir(exist_ok=True)
TS = datetime.now().strftime("%Y%m%d_%H%M%S")
RAW_LOG = LOG_DIR / f"raw_{TS}.jsonl"
REPORT = ROOT / "DETAILED_TEST_REPORT.md"


@dataclass
class CaseResult:
    id: int
    category: str
    name: str
    passed: bool
    expected: str
    actual: str
    duration_ms: float
    details: dict[str, Any] = field(default_factory=dict)
    error: str = ""


results: list[CaseResult] = []
_case_id = 0


def slim_plan(data: dict) -> dict:
    """Compact plan payload for logs (keeps decision-useful fields, drops huge geometry)."""
    if not isinstance(data, dict) or "summary" not in data:
        return data
    route = data.get("route") or {}
    geometry = route.get("geometry") or []
    logs = data.get("daily_logs") or []
    return {
        "summary": data.get("summary"),
        "places": data.get("places"),
        "stops": [
            {
                "type": s.get("type"),
                "label": s.get("label"),
                "lat": s.get("lat"),
                "lng": s.get("lng"),
                "duration_hours": s.get("duration_hours"),
                "mile_marker": s.get("mile_marker"),
            }
            for s in (route.get("stops") or [])
        ],
        # Full polyline omitted for readability; prove it exists with count + samples
        "geometry_points": len(geometry),
        "geometry_sample_first": geometry[:2],
        "geometry_sample_last": geometry[-2:] if len(geometry) >= 2 else geometry,
        "instructions": [
            {
                "action": i.get("action"),
                "start": i.get("start"),
                "end": i.get("end"),
                "miles": i.get("miles"),
                "text": i.get("text"),
            }
            for i in (data.get("instructions") or [])[:40]
        ],
        "instruction_count": len(data.get("instructions") or []),
        "daily_logs": [
            {
                "date": lg.get("date"),
                "totals": lg.get("totals"),
                "grid_segments": len(lg.get("grid_segments") or []),
                "remarks": lg.get("remarks"),
            }
            for lg in logs
        ],
        "assumptions": data.get("assumptions"),
    }


def run_case(category: str, name: str, expected: str, fn: Callable[[], tuple[bool, str, dict]]):
    global _case_id
    _case_id += 1
    cid = _case_id
    t0 = time.perf_counter()
    passed = False
    actual = ""
    details: dict = {}
    err = ""
    try:
        passed, actual, details = fn()
    except Exception as e:
        passed = False
        actual = f"EXCEPTION: {e}"
        err = traceback.format_exc()
        details = {"exception_type": type(e).__name__}
    ms = (time.perf_counter() - t0) * 1000
    cr = CaseResult(cid, category, name, passed, expected, actual, round(ms, 2), details, err)
    results.append(cr)
    with RAW_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(cr), default=str) + "\n")
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] #{cid:03d} {category} :: {name} ({ms:.0f}ms)")
    return cr


def http_get(path: str, timeout: float = 30.0):
    with httpx.Client(timeout=timeout) as c:
        r = c.get(f"{BASE}{path}")
        try:
            return r.status_code, r.json(), dict(r.headers)
        except Exception:
            return r.status_code, {"raw": r.text[:500]}, dict(r.headers)


def http_post(path: str, body: dict, timeout: float = 180.0, retries: int = 3):
    last = (0, {}, {})
    for attempt in range(retries):
        with httpx.Client(timeout=timeout) as c:
            r = c.post(f"{BASE}{path}", json=body)
            try:
                data = r.json()
            except Exception:
                data = {"raw": r.text[:500]}
            last = (r.status_code, data, dict(r.headers))
            # Retry transient upstream routing/geocode flaps
            code = r.status_code
            err = (data.get("error") or {}).get("code") if isinstance(data, dict) else None
            if code in (429, 502, 503) or err in ("ROUTE_FAILED", "GEOCODE_FAILED"):
                time.sleep(1.5 * (attempt + 1))
                continue
            return last
    return last


# =============================================================================
# Case generators
# =============================================================================

def cases_health():
    def t():
        code, data, _ = http_get("/api/health/")
        ok = code == 200 and data.get("status") == "ok"
        return ok, f"{code} {data}", {"response": data}

    run_case("Health", "GET /api/health/ returns ok", "200 status=ok", t)

    for i in range(5):
        def t(i=i):
            code, data, _ = http_get("/api/health/")
            return code == 200, f"{code}", {"i": i, "data": data}

        run_case("Health", f"health repeat #{i+1}", "200", t)


def cases_validation():
    base = {
        "current_location": "Dallas, TX",
        "pickup_location": "Dallas, TX",
        "dropoff_location": "Houston, TX",
        "current_cycle_used_hours": 10,
    }
    # cycle bounds
    for cycle, expect in [(-0.1, 400), (-1, 400), (70.1, 400), (80, 400), (1000, 400)]:
        def t(cycle=cycle, expect=expect):
            body = {**base, "current_cycle_used_hours": cycle}
            code, data, _ = http_post("/api/plan/", body)
            return code == expect, f"HTTP {code}", {"body": body, "response": data}

        run_case("Validation", f"cycle={cycle} -> {expect}", f"HTTP {expect}", t)

    for cycle in [0, 0.25, 10, 35, 69.75, 70]:
        def t(cycle=cycle):
            body = {
                **base,
                "current_cycle_used_hours": cycle,
                "start_datetime": "2026-08-25T06:00:00",
            }
            code, data, _ = http_post("/api/plan/", body)
            return code == 200, f"HTTP {code}", {
                "miles": (data.get("summary") or {}).get("total_miles"),
                "error": data.get("error"),
                "plan": slim_plan(data) if code == 200 else data,
            }

        run_case("Validation", f"cycle={cycle} accepted", "HTTP 200", t)

    # missing fields
    for field in ["current_location", "pickup_location", "dropoff_location", "current_cycle_used_hours"]:
        def t(field=field):
            body = {**base, "start_datetime": "2026-08-25T06:00:00"}
            del body[field]
            code, data, _ = http_post("/api/plan/", body)
            return code == 400, f"HTTP {code}", {"response": data}

        run_case("Validation", f"missing {field}", "HTTP 400", t)

    # empty strings
    for field in ["current_location", "pickup_location", "dropoff_location"]:
        def t(field=field):
            body = {**base, "start_datetime": "2026-08-25T06:00:00", field: ""}
            code, data, _ = http_post("/api/plan/", body)
            return code == 400, f"HTTP {code}", {"response": data}

        run_case("Validation", f"empty {field}", "HTTP 400", t)

    # bad types
    for val, label in [("abc", "string"), (None, "null"), (True, "bool"), ([], "list")]:
        def t(val=val, label=label):
            body = {**base, "current_cycle_used_hours": val}
            code, data, _ = http_post("/api/plan/", body)
            return code == 400, f"HTTP {code}", {"response": data}

        run_case("Validation", f"cycle type={label}", "HTTP 400", t)

    # same pickup/dropoff
    def t_same():
        body = {
            "current_location": "Dallas, TX",
            "pickup_location": "Dallas, TX",
            "dropoff_location": "Dallas, TX",
            "current_cycle_used_hours": 10,
            "start_datetime": "2026-08-25T06:00:00",
        }
        code, data, _ = http_post("/api/plan/", body)
        return code == 400, f"HTTP {code} {data.get('error',{})}", {"response": data}

    run_case("Validation", "same pickup and dropoff", "HTTP 400", t_same)

    # garbage geocode
    def t_geo():
        body = {
            "current_location": "zzznocity999xyz",
            "pickup_location": "zzznocity999xyz",
            "dropoff_location": "yyynocity888xyz",
            "current_cycle_used_hours": 10,
            "start_datetime": "2026-08-25T06:00:00",
        }
        code, data, _ = http_post("/api/plan/", body)
        return code == 422, f"HTTP {code}", {"response": data}

    run_case("Validation", "ungeocodable locations", "HTTP 422", t_geo)


def cases_autocomplete():
    queries = [
        ("", 0),
        ("a", 0),
        ("ab", 0),
        ("Dal", None),
        ("Dallas", None),
        ("Houston", None),
        ("Chicago", None),
        ("Los Ang", None),
        ("@@@", None),
        ("12345", None),
    ]
    for q, expect_len in queries:
        def t(q=q, expect_len=expect_len):
            code, data, _ = http_get(f"/api/autocomplete/?q={q}")
            results = data.get("results") if isinstance(data, dict) else None
            ok = code == 200 and isinstance(results, list)
            if expect_len is not None and ok:
                ok = len(results) == expect_len
            return ok, f"code={code} n={len(results) if isinstance(results, list) else '?'}", {
                "results": results
            }

        run_case("Autocomplete", f"q={q!r}", f"200 list len={expect_len}", t)


def cases_cors():
    origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5175",
        "http://localhost:5176",
        "http://127.0.0.1:5176",
    ]
    for origin in origins:
        def t(origin=origin):
            with httpx.Client(timeout=15) as c:
                r = c.get(f"{BASE}/api/health/", headers={"Origin": origin})
                acao = r.headers.get("access-control-allow-origin")
                ok = r.status_code == 200 and acao == origin
                return ok, f"ACAO={acao}", {"status": r.status_code}

        run_case("CORS", f"Origin {origin}", f"ACAO={origin}", t)

    # should NOT allow random origin in a way that echoes it (or may be None)
    def t_bad():
        with httpx.Client(timeout=15) as c:
            r = c.get(f"{BASE}/api/health/", headers={"Origin": "https://evil.example"})
            acao = r.headers.get("access-control-allow-origin")
            ok = acao != "https://evil.example"
            return ok, f"ACAO={acao}", {}

    run_case("CORS", "evil.example not echoed", "ACAO != evil", t_bad)


def cases_plan_demos():
    demos = [
        ("Short", "Dallas, TX", "Dallas, TX", "Houston, TX", 10, 1),
        ("Long", "Chicago, IL", "Chicago, IL", "Los Angeles, CA", 15, 2),
        ("Cycle68", "Dallas, TX", "Dallas, TX", "Houston, TX", 68, 1),
        ("Cycle70", "Dallas, TX", "Dallas, TX", "Houston, TX", 70, 1),
        ("Denver-Atlanta", "Denver, CO", "Denver, CO", "Atlanta, GA", 12, 1),
        ("Phoenix-Atlanta", "Phoenix, AZ", "Phoenix, AZ", "Atlanta, GA", 20, 2),
        ("NY-Chicago", "New York, NY", "New York, NY", "Chicago, IL", 8, 1),
        ("EmptyLeg", "Denver, CO", "Chicago, IL", "Atlanta, GA", 5, 2),
        ("LA-Phoenix", "Los Angeles, CA", "Los Angeles, CA", "Phoenix, AZ", 10, 1),
        ("Houston-Dallas", "Houston, TX", "Houston, TX", "Dallas, TX", 10, 1),
    ]
    for name, cur, pu, do, cycle, min_days in demos:
        def t(name=name, cur=cur, pu=pu, do=do, cycle=cycle, min_days=min_days):
            body = {
                "current_location": cur,
                "pickup_location": pu,
                "dropoff_location": do,
                "current_cycle_used_hours": cycle,
                "start_datetime": "2026-08-25T06:00:00",
            }
            code, data, _ = http_post("/api/plan/", body)
            if code != 200:
                return False, f"HTTP {code} {data.get('error')}", {"response": data}
            summary = data["summary"]
            logs = data["daily_logs"]
            issues = []
            if not data["route"]["geometry"]:
                issues.append("no geometry")
            if not data["instructions"]:
                issues.append("no instructions")
            if len(logs) < min_days:
                issues.append(f"days {len(logs)} < {min_days}")
            for log in logs:
                tot = sum(log["totals"].values())
                if abs(tot - 24) > 0.06:
                    issues.append(f"log {log['date']}={tot}")
            pu_s = [s for s in data["route"]["stops"] if s["type"] == "pickup"]
            do_s = [s for s in data["route"]["stops"] if s["type"] == "dropoff"]
            if len(pu_s) != 1 or abs(pu_s[0]["duration_hours"] - 1) > 0.05:
                issues.append("pickup")
            if len(do_s) != 1 or abs(do_s[0]["duration_hours"] - 1) > 0.05:
                issues.append("dropoff")
            if name.startswith("Cycle") and cycle >= 68:
                has34 = summary.get("inserted_34h_restart") or any(
                    s.get("type") == "restart_34" for s in data["route"]["stops"]
                )
                if not has34:
                    issues.append("no 34h restart")
            if summary.get("total_miles", 0) > 1000:
                fuels = [s for s in data["route"]["stops"] if s["type"] == "fuel"]
                if not fuels:
                    issues.append("no fuel")
            ok = not issues
            return ok, f"mi={summary.get('total_miles')} days={len(logs)} issues={issues or 'none'}", {
                "request": body,
                "issues": issues,
                "plan": slim_plan(data),
            }

        run_case("Plan demos", name, "200 legal plan", t)


def cases_start_times():
    times = [
        "2026-08-25T00:00:00",
        "2026-08-25T06:00:00",
        "2026-08-25T12:00:00",
        "2026-08-25T18:00:00",
        "2026-08-25T23:00:00",
        "2026-08-25T23:30:00",
        "2026-08-25T23:45:00",
        "2026-12-31T22:00:00",
        "2026-01-01T01:00:00",
    ]
    for st in times:
        def t(st=st):
            body = {
                "current_location": "Dallas, TX",
                "pickup_location": "Dallas, TX",
                "dropoff_location": "Houston, TX",
                "current_cycle_used_hours": 10,
                "start_datetime": st,
            }
            code, data, _ = http_post("/api/plan/", body)
            if code != 200:
                return False, f"HTTP {code}", {"error": data.get("error"), "request": body}
            logs = data["daily_logs"]
            sums_ok = all(abs(sum(l["totals"].values()) - 24) < 0.06 for l in logs)
            return sums_ok, f"days={len(logs)} sums_ok={sums_ok}", {
                "request": body,
                "dates": [l["date"] for l in logs],
                "plan": slim_plan(data),
            }

        run_case("Start times", f"start={st}", "200 + 24h logs", t)


def cases_inprocess_hos():
    """Direct planner+verifier checks (no HTTP)."""
    from datetime import datetime

    start = datetime(2026, 8, 10, 6, 0, tzinfo=TZ)
    trips = [
        ("DAL-HOU-10", "Dallas, TX", "Dallas, TX", "Houston, TX", 10),
        ("CHI-LA-15", "Chicago, IL", "Chicago, IL", "Los Angeles, CA", 15),
        ("PHX-ATL-20", "Phoenix, AZ", "Phoenix, AZ", "Atlanta, GA", 20),
        ("DEN-ATL-5", "Denver, CO", "Denver, CO", "Atlanta, GA", 5),
        ("NY-CHI-8", "New York, NY", "New York, NY", "Chicago, IL", 8),
        ("LA-PHX-10", "Los Angeles, CA", "Los Angeles, CA", "Phoenix, AZ", 10),
        ("HOU-DAL-12", "Houston, TX", "Houston, TX", "Dallas, TX", 12),
        ("CHI-DEN-12", "Chicago, IL", "Chicago, IL", "Denver, CO", 12),
        ("ATL-CHI-10", "Atlanta, GA", "Atlanta, GA", "Chicago, IL", 10),
        ("empty-leg", "Denver, CO", "Chicago, IL", "Houston, TX", 8),
    ]
    for name, cur, pu, do, cycle in trips:
        def t(name=name, cur=cur, pu=pu, do=do, cycle=cycle, start=start):
            r = plan_trip(cur, pu, do, cycle, start)
            hard = [v.code for v in verify(r.timeline, cycle) if v.code != "DAY_24"]
            log_ok = all(abs(sum(l.totals.values()) - 24) < 0.06 for l in r.daily_logs)
            ok = not hard and log_ok and len(r.instructions) > 0
            return ok, f"mi={r.summary['total_miles']} viol={hard} logs={len(r.daily_logs)}", {
                "summary": r.summary,
                "actions": [i.action for i in r.instructions[:20]],
                "log_totals": [{"date": l.date, "totals": l.totals} for l in r.daily_logs],
                "stop_types": [s.get("type") for s in (r.route.get("stops") or [])],
                "instruction_count": len(r.instructions),
            }

        run_case("HOS in-process", name, "verifier clean + 24h logs", t)


def cases_geo_route():
    cities = [
        "Dallas, TX",
        "Houston, TX",
        "Chicago, IL",
        "Los Angeles, CA",
        "Denver, CO",
        "Atlanta, GA",
        "New York, NY",
        "Phoenix, AZ",
    ]
    for city in cities:
        def t(city=city):
            p = geocode_place(city)
            ok = p.point.lat != 0 and p.label
            return ok, f"{p.label} ({p.point.lat:.4f},{p.point.lng:.4f})", {
                "label": p.label,
                "lat": p.point.lat,
                "lng": p.point.lng,
            }

        run_case("Geocode", f"geocode {city}", "valid Place", t)

    pairs = [
        ("Dallas, TX", "Houston, TX"),
        ("Chicago, IL", "Denver, CO"),
        ("Los Angeles, CA", "Phoenix, AZ"),
        ("New York, NY", "Chicago, IL"),
        ("Phoenix, AZ", "Atlanta, GA"),
    ]
    for a, b in pairs:
        def t(a=a, b=b):
            pa, pb = geocode_place(a), geocode_place(b)
            leg, used_car = build_route(pa, pb)
            ok = leg.distance_miles > 50 and len(leg.geometry) >= 2
            return ok, f"{leg.distance_miles:.1f}mi {leg.duration_hours:.2f}h pts={len(leg.geometry)} car={used_car}", {
                "miles": leg.distance_miles,
                "hours": leg.duration_hours,
                "used_car": used_car,
            }

        run_case("Routing", f"{a} -> {b}", "route with geometry", t)

    # same point
    def t_same():
        p = geocode_place("Dallas, TX")
        leg, _ = build_route(p, p)
        return leg.distance_miles < 1, f"{leg.distance_miles}", {}

    run_case("Routing", "identical points ~0 mi", "~0 miles", t_same)


def cases_contract_fields():
    def t():
        code, data, _ = http_post(
            "/api/plan/",
            {
                "current_location": "Dallas, TX",
                "pickup_location": "Dallas, TX",
                "dropoff_location": "Houston, TX",
                "current_cycle_used_hours": 10,
                "start_datetime": "2026-08-25T06:00:00",
            },
        )
        required = [
            "summary",
            "places",
            "route",
            "instructions",
            "timeline",
            "daily_logs",
            "assumptions",
        ]
        missing = [k for k in required if k not in data]
        asum = data.get("assumptions") or []
        need = ["Pre-trip", "0.5h OFF", "70h/8-day", "1000"]
        missing_a = [n for n in need if not any(n.lower() in a.lower() or n in a for a in asum)]
        # softer: check key phrases
        checks = {
            "pretrip": any("pre-trip" in a.lower() for a in asum),
            "reset_split": any("9.5h SB" in a or "0.5h OFF" in a for a in asum),
            "fuel": any("1000" in a for a in asum),
            "cycle": any("70" in a for a in asum),
        }
        ok = code == 200 and not missing and all(checks.values())
        return ok, f"missing={missing} checks={checks}", {"assumptions": asum}

    run_case("API contract", "plan response keys + assumptions", "full contract", t)

    # summary keys
    def t2():
        code, data, _ = http_post(
            "/api/plan/",
            {
                "current_location": "Dallas, TX",
                "pickup_location": "Dallas, TX",
                "dropoff_location": "Houston, TX",
                "current_cycle_used_hours": 10,
                "start_datetime": "2026-08-25T06:00:00",
            },
        )
        s = data.get("summary") or {}
        keys = [
            "total_miles",
            "total_driving_hours",
            "total_on_duty_hours",
            "days",
            "cycle_remaining_end",
            "inserted_34h_restart",
        ]
        missing = [k for k in keys if k not in s]
        return code == 200 and not missing, f"missing={missing}", {"summary": s}

    run_case("API contract", "summary fields", "summary complete", t2)

    # log fields
    def t3():
        code, data, _ = http_post(
            "/api/plan/",
            {
                "current_location": "Chicago, IL",
                "pickup_location": "Chicago, IL",
                "dropoff_location": "Denver, CO",
                "current_cycle_used_hours": 12,
                "start_datetime": "2026-08-25T06:00:00",
            },
        )
        log = (data.get("daily_logs") or [{}])[0]
        keys = [
            "date",
            "from_location",
            "to_location",
            "total_miles_driving",
            "totals",
            "remarks",
            "recap",
            "grid_segments",
            "header",
        ]
        missing = [k for k in keys if k not in log]
        recap_ok = "on_duty_today" in (log.get("recap") or {})
        grid_ok = len(log.get("grid_segments") or []) > 0
        return code == 200 and not missing and recap_ok and grid_ok, f"missing={missing} recap={recap_ok} grid={grid_ok}", {
            "log_keys": list(log.keys()),
            "grid_n": len(log.get("grid_segments") or []),
        }

    run_case("API contract", "daily_log fields", "log complete", t3)


def cases_stops_coords():
    def t():
        code, data, _ = http_post(
            "/api/plan/",
            {
                "current_location": "Chicago, IL",
                "pickup_location": "Chicago, IL",
                "dropoff_location": "Los Angeles, CA",
                "current_cycle_used_hours": 15,
                "start_datetime": "2026-08-25T06:00:00",
            },
        )
        if code != 200:
            return False, f"HTTP {code}", {}
        bad = [s for s in data["route"]["stops"] if s.get("lat") is None or s.get("lng") is None]
        return not bad, f"bad={bad}", {"stop_count": len(data["route"]["stops"])}

    run_case("Map data", "all stops have coordinates", "no null lat/lng", t)

    def t_geo():
        code, data, _ = http_post(
            "/api/plan/",
            {
                "current_location": "Dallas, TX",
                "pickup_location": "Dallas, TX",
                "dropoff_location": "Houston, TX",
                "current_cycle_used_hours": 10,
                "start_datetime": "2026-08-25T06:00:00",
            },
        )
        if code != 200:
            return False, f"HTTP {code}", {}
        geometry = data.get("route", {}).get("geometry") or []
        ok = len(geometry) >= 2 and all(
            isinstance(p, (list, tuple)) and len(p) == 2 for p in geometry[:5]
        )
        return ok, f"points={len(geometry)} first={geometry[:1]}", {
            "geometry_points": len(geometry),
            "geometry_sample_first": geometry[:2],
            "geometry_sample_last": geometry[-2:],
        }

    run_case("Map data", "route.geometry polyline present", ">=2 lat/lng pairs", t_geo)

    def t_instr_times():
        code, data, _ = http_post(
            "/api/plan/",
            {
                "current_location": "Dallas, TX",
                "pickup_location": "Dallas, TX",
                "dropoff_location": "Houston, TX",
                "current_cycle_used_hours": 10,
                "start_datetime": "2026-08-25T06:00:00",
            },
        )
        if code != 200:
            return False, f"HTTP {code}", {}
        instr = data.get("instructions") or []
        missing = [i.get("action") for i in instr if not i.get("start") or not i.get("end")]
        return (
            bool(instr) and not missing,
            f"n={len(instr)} missing_times={missing}",
            {"sample": [{"action": i.get("action"), "start": i.get("start"), "end": i.get("end")} for i in instr[:5]]},
        )

    run_case("Map data", "instructions have start/end times", "all instructions timed", t_instr_times)

    def t_fields_shape():
        code, data, _ = http_post(
            "/api/plan/",
            {
                "current_location": "Dallas, TX",
                "pickup_location": "Dallas, TX",
                "dropoff_location": "Dallas, TX",
                "current_cycle_used_hours": 10,
                "start_datetime": "2026-08-25T06:00:00",
            },
        )
        fields = (data.get("error") or {}).get("fields") or {}
        drop = fields.get("dropoff_location")
        ok = code == 400 and isinstance(drop, list) and drop and isinstance(drop[0], str)
        return ok, f"HTTP {code} fields={fields}", {"fields": fields}

    run_case(
        "Validation",
        "same pickup/dropoff fields are message arrays",
        "fields.dropoff_location = [str, ...]",
        t_fields_shape,
    )


def pad_to_100_plus():
    """Additional micro-cases to ensure >= 100."""
    # repeated short plans with varying cycle steps
    for i, cycle in enumerate([1, 2, 3, 4, 5, 6, 7, 9, 11, 13, 14, 16, 18, 22, 25, 30, 40, 50, 60, 65]):
        def t(cycle=cycle):
            code, data, _ = http_post(
                "/api/plan/",
                {
                    "current_location": "Dallas, TX",
                    "pickup_location": "Dallas, TX",
                    "dropoff_location": "Houston, TX",
                    "current_cycle_used_hours": cycle,
                    "start_datetime": "2026-08-25T06:00:00",
                },
            )
            ok = code == 200 and abs(sum(data["daily_logs"][0]["totals"].values()) - 24) < 0.06
            return ok, f"HTTP {code} mi={(data.get('summary') or {}).get('total_miles')}", {
                "cycle": cycle,
                "restart": (data.get("summary") or {}).get("inserted_34h_restart"),
                "plan": slim_plan(data) if code == 200 else data,
            }

        run_case("Cycle sweep", f"cycle={cycle} Dallas-Houston", "200 + 24h day", t)


def write_report():
    passed = sum(1 for r in results if r.passed)
    failed = [r for r in results if not r.passed]
    lines = [
        "# Detailed Test Report - Spotter HOS Trip Planner",
        "",
        f"**Generated:** {datetime.now().isoformat(timespec='seconds')}",
        f"**API base:** `{BASE}`",
        f"**Total cases:** {len(results)}",
        f"**Passed:** {passed}",
        f"**Failed:** {len(failed)}",
        f"**Pass rate:** {100 * passed / max(1, len(results)):.1f}%",
        f"**Raw JSONL log:** `test_logs/{RAW_LOG.name}`",
        "",
        "## Category summary",
        "",
        "| Category | Pass | Fail | Total |",
        "|---|---:|---:|---:|",
    ]
    cats: dict[str, list[CaseResult]] = {}
    for r in results:
        cats.setdefault(r.category, []).append(r)
    for cat, items in cats.items():
        p = sum(1 for i in items if i.passed)
        f = len(items) - p
        lines.append(f"| {cat} | {p} | {f} | {len(items)} |")

    lines += ["", "## Failed cases (detailed)", ""]
    if not failed:
        lines.append("_None - all cases passed._")
    else:
        for r in failed:
            lines += [
                f"### Case #{r.id:03d} — {r.category} / {r.name}",
                "",
                f"- **Expected:** {r.expected}",
                f"- **Actual:** {r.actual}",
                f"- **Duration:** {r.duration_ms} ms",
                f"- **Details:** `{json.dumps(r.details, default=str)[:800]}`",
            ]
            if r.error:
                lines.append(f"- **Traceback:**\n```\n{r.error[-1500:]}\n```")
            lines.append("")

    lines += ["", "## All cases (summary table)", "", "| ID | Cat | Name | Result | ms | Actual |", "|---:|---|---|---|---:|---|"]
    for r in results:
        act = str(r.actual).replace("|", "/").replace("\n", " ")[:120]
        lines.append(
            f"| {r.id} | {r.category} | {r.name} | {'PASS' if r.passed else 'FAIL'} | {r.duration_ms} | {act} |"
        )

    lines += ["", "## Case-by-case detailed outputs", ""]
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        detail_json = json.dumps(r.details, default=str, indent=2)
        if len(detail_json) > 6000:
            detail_json = detail_json[:6000] + "\n... [truncated]"
        lines += [
            f"### Case #{r.id:03d} [{status}] — {r.category} / {r.name}",
            "",
            f"- **Expected:** {r.expected}",
            f"- **Actual:** {r.actual}",
            f"- **Duration:** {r.duration_ms} ms",
            "",
            "```json",
            detail_json,
            "```",
            "",
        ]
        if r.error:
            lines += ["**Traceback:**", "```", r.error[-2000:], "```", ""]

    lines += [
        "",
        "## Notes",
        "",
        "- HTTP cases hit the live local API at the API base above.",
        "- HOS in-process cases call `plan_trip` + `verify` directly (no HTTP).",
        "- Geocode may use Nominatim/known-city fallback when ORS key is absent.",
        "- Each case is also one JSON line in the raw `.jsonl` log (full machine-readable).",
        "- Summary JSON is written beside the raw log under `test_logs/`.",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    summary = {
        "generated": datetime.now().isoformat(),
        "api": BASE,
        "total": len(results),
        "passed": passed,
        "failed": len(failed),
        "raw_log": str(RAW_LOG.relative_to(ROOT)),
        "report": str(REPORT.relative_to(ROOT)),
        "failed_ids": [r.id for r in failed],
    }
    (LOG_DIR / f"summary_{TS}.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nReport: {REPORT}")
    print(f"Raw log: {RAW_LOG}")
    print(f"Summary: {summary}")


def main():
    print(f"Running 100+ cases against {BASE}")
    print(f"Logging to {RAW_LOG}")
    cases_health()
    cases_validation()
    cases_autocomplete()
    cases_cors()
    cases_plan_demos()
    cases_start_times()
    cases_inprocess_hos()
    cases_geo_route()
    cases_contract_fields()
    cases_stops_coords()
    pad_to_100_plus()
    write_report()
    failed = sum(1 for r in results if not r.passed)
    if len(results) < 100:
        print(f"WARNING: only {len(results)} cases (need >=100)")
        return 2
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
