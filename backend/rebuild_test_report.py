"""Rebuild DETAILED_TEST_REPORT.md from the latest raw_*.jsonl."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "test_logs"
raw = sorted(LOG_DIR.glob("raw_*.jsonl"))[-1]
results = [json.loads(line) for line in raw.read_text(encoding="utf-8").splitlines() if line.strip()]
passed = sum(1 for r in results if r["passed"])
failed = [r for r in results if not r["passed"]]

lines = [
    "# Detailed Test Report - Spotter HOS Trip Planner",
    "",
    f"**Generated:** {datetime.now().isoformat(timespec='seconds')}",
    "**API base:** `http://127.0.0.1:8080`",
    f"**Total cases:** {len(results)}",
    f"**Passed:** {passed}",
    f"**Failed:** {len(failed)}",
    f"**Pass rate:** {100 * passed / max(1, len(results)):.1f}%",
    f"**Raw JSONL log:** `test_logs/{raw.name}`",
    "",
    "## Category summary",
    "",
    "| Category | Pass | Fail | Total |",
    "|---|---:|---:|---:|",
]

cats: dict[str, list] = {}
for r in results:
    cats.setdefault(r["category"], []).append(r)
for cat, items in cats.items():
    p = sum(1 for i in items if i["passed"])
    lines.append(f"| {cat} | {p} | {len(items) - p} | {len(items)} |")

lines += ["", "## Failed cases (detailed)", ""]
if not failed:
    lines.append("_None - all cases passed._")
else:
    for r in failed:
        lines += [
            f"### Case #{r['id']:03d} — {r['category']} / {r['name']}",
            "",
            f"- **Expected:** {r['expected']}",
            f"- **Actual:** {r['actual']}",
            f"- **Duration:** {r['duration_ms']} ms",
            "",
        ]

lines += [
    "",
    "## All cases (summary table)",
    "",
    "| ID | Cat | Name | Result | ms | Actual |",
    "|---:|---|---|---|---:|---|",
]
for r in results:
    act = str(r["actual"]).replace("|", "/").replace("\n", " ")[:120]
    status = "PASS" if r["passed"] else "FAIL"
    lines.append(
        f"| {r['id']} | {r['category']} | {r['name']} | {status} | {r['duration_ms']} | {act} |"
    )

lines += ["", "## Case-by-case detailed outputs", ""]
for r in results:
    status = "PASS" if r["passed"] else "FAIL"
    detail_json = json.dumps(r.get("details") or {}, default=str, indent=2)
    if len(detail_json) > 6000:
        detail_json = detail_json[:6000] + "\n... [truncated]"
    lines += [
        f"### Case #{r['id']:03d} [{status}] — {r['category']} / {r['name']}",
        "",
        f"- **Expected:** {r['expected']}",
        f"- **Actual:** {r['actual']}",
        f"- **Duration:** {r['duration_ms']} ms",
        "",
        "```json",
        detail_json,
        "```",
        "",
    ]
    if r.get("error"):
        lines += ["**Traceback:**", "```", r["error"][-2000:], "```", ""]

lines += [
    "",
    "## Notes",
    "",
    "- HTTP cases hit the live local API.",
    "- HOS in-process cases call `plan_trip` + `verify` directly.",
    "- Geocode may use Nominatim/known-city fallback when ORS key is absent.",
    "- Each case is also one JSON line in the raw `.jsonl` log.",
    "- Summary JSON is under `test_logs/`.",
    "",
]

report = ROOT / "DETAILED_TEST_REPORT.md"
report.write_text("\n".join(lines), encoding="utf-8")
print(f"Wrote {report}")
print(f"Source: {raw.name}")
print(f"Cases: {len(results)}  Passed: {passed}  Failed: {len(failed)}")
print(f"Size: {report.stat().st_size} bytes")
