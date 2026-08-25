import { Box } from "@mui/material";

type GridSeg = {
  status: "OFF" | "SB" | "D" | "ON";
  start_minute: number;
  end_minute: number;
  bracket: boolean;
};

type Remark = { time: string; location_label: string; text: string };

export type DailyLog = {
  date: string;
  from_location: string;
  to_location: string;
  total_miles_driving: number;
  totals: { off: number; sb: number; drive: number; on: number };
  remarks: Remark[];
  recap: {
    on_duty_today: number;
    cycle_remaining_start: number;
    cycle_remaining_end: number;
    a_70_8?: number;
    b_70_8?: number;
    c_70_8?: number;
    a_60_7?: number | null;
    b_60_7?: number | null;
    c_60_7?: number | null;
    note: string;
  };
  grid_segments: GridSeg[];
  header: Record<string, string>;
};

const ROW: Record<string, number> = { OFF: 0, SB: 1, D: 2, ON: 3 };
const ROW_LABELS: string[][] = [
  ["Off Duty"],
  ["Sleeper Berth"],
  ["Driving"],
  ["On Duty", "(Not Driving)"],
];

const W = 920;
const LABEL_W = 88;
const TOTAL_W = 56;
const MARGIN = 10;
const GRID_LEFT = MARGIN + LABEL_W;
const GRID_RIGHT = W - MARGIN - TOTAL_W;
const GRID_W = GRID_RIGHT - GRID_LEFT;

const HEADER_H = 128;
const RULER_H = 14;
const GRID_TOP = HEADER_H + RULER_H + 2;
const GRID_H = 128;
const ROW_H = GRID_H / 4;

const INK = "#111111";
const MUTED = "#333333";
const RULE = "#222222";
const RULE_LIGHT = "#888888";
const DUTY = "#1a1a1a";
const FONT = "Arial, Helvetica, sans-serif";
const FONT_ENTRY = "Georgia, 'Times New Roman', Times, serif";

function xAt(minute: number) {
  return GRID_LEFT + (Math.min(1440, Math.max(0, minute)) / 1440) * GRID_W;
}

function yRow(status: string) {
  return GRID_TOP + (ROW[status] ?? 0) * ROW_H + ROW_H / 2;
}

function timeToMinute(time: string): number {
  const [h, m] = time.split(":").map(Number);
  return (h ?? 0) * 60 + (m ?? 0);
}

function fmtHours(h: number | null | undefined): string {
  if (h == null || Number.isNaN(h)) {
    return "—";
  }
  const q = Math.round(h * 4) / 4;
  if (Number.isInteger(q)) {
    return String(q);
  }
  return q.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
}

function hourLabel(h: number): string {
  if (h === 0) {
    return "Midnight";
  }
  if (h === 12) {
    return "Noon";
  }
  if (h === 1) {
    return "";
  }
  return String(h);
}

function pinDisplayLabel(label: string): string {
  // Compact FMCSA-ish pin text: "San Bernardino County, CA" → "San Bernardino Co., CA"
  return label
    .replace(/\bCounty\b/gi, "Co.")
    .replace(/\bTownship\b/gi, "Twp.")
    .replace(/\bParish\b/gi, "Par.");
}

/**
 * Remarks timeline pins (FMCSA-style City, ST markers).
 * - One pin per location *change* (collapses back-to-back same-city events).
 * - Lane stagger + label-length-aware horizontal gap for close timestamps.
 */
function layoutRemarkPins(remarks: Remark[], baseY: number) {
  const pins: {
    x: number;
    y: number;
    label: string;
    lane: number;
    gap: number;
  }[] = [];
  const laneHeight = 50;
  const maxLanes = 5;
  let lastLoc = "";

  for (const remark of remarks) {
    const loc = (remark.location_label || "").trim();
    const raw = loc && loc !== "—" ? loc : shortText(remark.text, 24);
    if (!raw) {
      continue;
    }
    const label = pinDisplayLabel(raw);
    // Skip repeated same location (many duty changes at one stop)
    if (label === lastLoc) {
      continue;
    }
    lastLoc = label;

    const x = xAt(timeToMinute(remark.time));
    // Diagonal ~55°: longer names need more horizontal clearance
    const gap = Math.max(60, Math.min(150, label.length * 3.8));

    let lane = 0;
    for (;;) {
      const clash = pins.some((p) => {
        const need = Math.max(gap, p.gap);
        const dx = Math.abs(p.x - x);
        if (dx >= need) {
          return false;
        }
        if (p.lane === lane) {
          return true;
        }
        if (Math.abs(p.lane - lane) === 1 && dx < need * 0.6) {
          return true;
        }
        return false;
      });
      if (!clash || lane >= maxLanes - 1) {
        pins.push({ x, y: baseY + lane * laneHeight, label, lane, gap });
        break;
      }
      lane += 1;
    }
  }
  return pins;
}

function shortText(text: string, max: number): string {
  const t = text.trim();
  if (t.length <= max) {
    return t;
  }
  return `${t.slice(0, max - 1)}…`;
}

function TimeRuler({ y, showLabels }: { y: number; showLabels: boolean }) {
  return (
    <g>
      <line
        x1={GRID_LEFT}
        y1={y}
        x2={GRID_RIGHT}
        y2={y}
        stroke={RULE}
        strokeWidth="0.9"
      />
      {Array.from({ length: 25 }, (_, h) => {
        const x = xAt(h * 60);
        return (
          <g key={h}>
            <line
              x1={x}
              y1={y - 4}
              x2={x}
              y2={y + 4}
              stroke={RULE}
              strokeWidth={h % 6 === 0 ? 1 : 0.7}
            />
            {showLabels && h < 24 && hourLabel(h) ? (
              <text
                x={h === 0 ? x + 1 : h === 12 ? x : x}
                y={y - 6}
                fontSize={h === 0 || h === 12 ? 7.5 : 8}
                fill={INK}
                fontFamily={FONT}
                textAnchor={h === 0 ? "start" : h === 12 ? "middle" : "middle"}
              >
                {hourLabel(h)}
              </text>
            ) : null}
          </g>
        );
      })}
      {Array.from({ length: 96 }, (_, i) => {
        if (i % 4 === 0) {
          return null;
        }
        const x = xAt(i * 15);
        return (
          <line
            key={`q${i}`}
            x1={x}
            y1={y - 2}
            x2={x}
            y2={y + 2}
            stroke={RULE_LIGHT}
            strokeWidth="0.5"
          />
        );
      })}
    </g>
  );
}

export function DailyLogSheet({ log }: { log: DailyLog }) {
  const dateObj = new Date(log.date + "T12:00:00");
  const month = String(dateObj.getMonth() + 1).padStart(2, "0");
  const day = String(dateObj.getDate()).padStart(2, "0");
  const year = String(dateObj.getFullYear());

  const remarks = log.remarks;
  const remarksRulerY = GRID_TOP + GRID_H + 18;
  // Short leader to tick tip; label baseline offset inside rotate() keeps glyphs below axis
  const pinBaseY = remarksRulerY + 10;
  const pins = layoutRemarkPins(remarks, pinBaseY);
  const pinDepth =
    pins.length > 0 ? Math.max(...pins.map((p) => p.y)) - pinBaseY + 110 : 44;

  const shippingY = pinBaseY + pinDepth + 6;
  const recapY = shippingY + 28;
  const RECAP_H = 86;
  const svgH = recapY + RECAP_H + 10;

  const grandTotal =
    log.totals.off + log.totals.sb + log.totals.drive + log.totals.on;

  const a70 =
    log.recap.a_70_8 ?? Math.max(0, 70 - (log.recap.cycle_remaining_end ?? 0));
  const b70 = log.recap.b_70_8 ?? log.recap.cycle_remaining_end;
  const c70 = log.recap.c_70_8 ?? a70;

  return (
    <Box
      className="daily-log-sheet"
      sx={{
        bgcolor: "#fff",
        border: "1px solid #111",
        borderRadius: 0,
        p: 0.75,
        overflow: "auto",
        boxShadow: "none",
      }}
    >
      <svg
        viewBox={`0 0 ${W} ${svgH}`}
        width="100%"
        role="img"
        aria-label={`Daily log ${log.date}`}
        style={{ display: "block", minWidth: 680, background: "#fff" }}
      >
        <rect x="0" y="0" width={W} height={svgH} fill="#ffffff" />

        {/* ——— HEADER (DOT paper form) ——— */}
        <text x={MARGIN} y={12} fontSize="7.5" fill={MUTED} fontFamily={FONT} letterSpacing="0.4">
          U.S. DEPARTMENT OF TRANSPORTATION
        </text>

        <text
          x={W / 2}
          y={14}
          fontSize="15"
          fontWeight="700"
          fill={INK}
          fontFamily={FONT}
          textAnchor="middle"
        >
          DRIVER&apos;S DAILY LOG
        </text>
        <text
          x={W / 2}
          y={26}
          fontSize="8"
          fill={MUTED}
          fontFamily={FONT}
          textAnchor="middle"
        >
          (ONE CALENDAR DAY — 24 HOURS)
        </text>

        <text
          x={W - MARGIN}
          y={11}
          fontSize="6.5"
          fill={MUTED}
          fontFamily={FONT}
          textAnchor="end"
        >
          ORIGINAL — Submit to carrier within 13 days
        </text>
        <text
          x={W - MARGIN}
          y={20}
          fontSize="6.5"
          fill={MUTED}
          fontFamily={FONT}
          textAnchor="end"
        >
          DUPLICATE — Driver retains possession for eight days
        </text>

        {/* Date: MM  DD  YYYY compact */}
        <text x={MARGIN} y={36} fontSize="6.5" fill={MUTED} fontFamily={FONT}>
          (MONTH)
        </text>
        <text x={MARGIN + 42} y={36} fontSize="6.5" fill={MUTED} fontFamily={FONT}>
          (DAY)
        </text>
        <text x={MARGIN + 78} y={36} fontSize="6.5" fill={MUTED} fontFamily={FONT}>
          (YEAR)
        </text>
        <text x={MARGIN + 8} y={50} fontSize="13" fill={INK} fontFamily={FONT_ENTRY} fontWeight="700">
          {month}
        </text>
        <text x={MARGIN + 48} y={50} fontSize="13" fill={INK} fontFamily={FONT_ENTRY} fontWeight="700">
          {day}
        </text>
        <text x={MARGIN + 78} y={50} fontSize="13" fill={INK} fontFamily={FONT_ENTRY} fontWeight="700">
          {year}
        </text>
        <line x1={MARGIN} y1={53} x2={MARGIN + 118} y2={53} stroke={RULE} strokeWidth="0.7" />

        {/* Total miles */}
        <text x={MARGIN + 8} y={68} fontSize="13" fill={INK} fontFamily={FONT_ENTRY} fontWeight="700">
          {log.total_miles_driving}
        </text>
        <line x1={MARGIN} y1={71} x2={MARGIN + 70} y2={71} stroke={RULE} strokeWidth="0.7" />
        <text x={MARGIN} y={80} fontSize="6" fill={MUTED} fontFamily={FONT}>
          (TOTAL MILES DRIVING TODAY)
        </text>

        {/* Carrier / office — center-left */}
        <text
          x={MARGIN + 140}
          y={48}
          fontSize="12"
          fill={INK}
          fontFamily={FONT_ENTRY}
          fontStyle="italic"
        >
          {log.header.carrier_name}
        </text>
        <line
          x1={MARGIN + 140}
          y1={51}
          x2={MARGIN + 400}
          y2={51}
          stroke={RULE}
          strokeWidth="0.7"
        />
        <text x={MARGIN + 140} y={60} fontSize="6" fill={MUTED} fontFamily={FONT}>
          (NAME OF CARRIER OR CARRIERS)
        </text>

        <text
          x={MARGIN + 140}
          y={74}
          fontSize="11"
          fill={INK}
          fontFamily={FONT_ENTRY}
          fontStyle="italic"
        >
          {log.header.main_office}
        </text>
        <line
          x1={MARGIN + 140}
          y1={77}
          x2={MARGIN + 400}
          y2={77}
          stroke={RULE}
          strokeWidth="0.7"
        />
        <text x={MARGIN + 140} y={86} fontSize="6" fill={MUTED} fontFamily={FONT}>
          (MAIN OFFICE ADDRESS)
        </text>

        {/* From / To compact */}
        <text x={MARGIN} y={96} fontSize="7" fill={MUTED} fontFamily={FONT}>
          From:
        </text>
        <text x={MARGIN + 28} y={96} fontSize="9" fill={INK} fontFamily={FONT_ENTRY}>
          {log.from_location}
        </text>
        <line x1={MARGIN + 28} y1={98} x2={MARGIN + 200} y2={98} stroke={RULE} strokeWidth="0.6" />
        <text x={MARGIN + 210} y={96} fontSize="7" fill={MUTED} fontFamily={FONT}>
          To:
        </text>
        <text x={MARGIN + 226} y={96} fontSize="9" fill={INK} fontFamily={FONT_ENTRY}>
          {log.to_location}
        </text>
        <line x1={MARGIN + 226} y1={98} x2={MARGIN + 400} y2={98} stroke={RULE} strokeWidth="0.6" />

        {/* Right: vehicle + certification + driver signature */}
        <text
          x={W - MARGIN - 8}
          y={48}
          fontSize="12"
          fill={INK}
          fontFamily={FONT_ENTRY}
          fontWeight="700"
          textAnchor="end"
        >
          {log.header.vehicle_number}
        </text>
        <line
          x1={W - MARGIN - 200}
          y1={51}
          x2={W - MARGIN}
          y2={51}
          stroke={RULE}
          strokeWidth="0.7"
        />
        <text
          x={W - MARGIN}
          y={60}
          fontSize="6"
          fill={MUTED}
          fontFamily={FONT}
          textAnchor="end"
        >
          VEHICLE NUMBERS—(SHOW EACH UNIT)
        </text>

        <text
          x={W - MARGIN}
          y={74}
          fontSize="7"
          fill={MUTED}
          fontFamily={FONT}
          fontStyle="italic"
          textAnchor="end"
        >
          I certify that these entries are true and correct
        </text>
        <text
          x={W - MARGIN - 8}
          y={90}
          fontSize="13"
          fill={INK}
          fontFamily={FONT_ENTRY}
          fontStyle="italic"
          textAnchor="end"
        >
          {log.header.driver_name}
        </text>
        <line
          x1={W - MARGIN - 200}
          y1={93}
          x2={W - MARGIN}
          y2={93}
          stroke={RULE}
          strokeWidth="0.7"
        />
        <text
          x={W - MARGIN}
          y={102}
          fontSize="6"
          fill={MUTED}
          fontFamily={FONT}
          textAnchor="end"
        >
          (DRIVER&apos;S SIGNATURE IN FULL)
        </text>
        <text
          x={W - MARGIN - 8}
          y={114}
          fontSize="10"
          fill={INK}
          fontFamily={FONT_ENTRY}
          textAnchor="end"
        >
          {log.header.co_driver}
        </text>
        <line
          x1={W - MARGIN - 160}
          y1={117}
          x2={W - MARGIN}
          y2={117}
          stroke={RULE}
          strokeWidth="0.6"
        />
        <text
          x={W - MARGIN}
          y={126}
          fontSize="6"
          fill={MUTED}
          fontFamily={FONT}
          textAnchor="end"
        >
          (NAME OF CO-DRIVER)
        </text>

        {/* ——— TIME RULER (top) ——— */}
        <TimeRuler y={GRID_TOP - 4} showLabels />

        {/* ——— DUTY GRID ——— */}
        {/* Vertical hour lines through all rows */}
        {Array.from({ length: 25 }, (_, h) => {
          const x = xAt(h * 60);
          return (
            <line
              key={`vh${h}`}
              x1={x}
              y1={GRID_TOP}
              x2={x}
              y2={GRID_TOP + GRID_H}
              stroke={RULE}
              strokeWidth={h === 0 || h === 24 || h === 12 ? 1 : 0.55}
            />
          );
        })}
        {/* 15-min ticks full height (light) */}
        {Array.from({ length: 96 }, (_, i) => {
          if (i % 4 === 0) {
            return null;
          }
          const x = xAt(i * 15);
          return (
            <line
              key={`vt${i}`}
              x1={x}
              y1={GRID_TOP}
              x2={x}
              y2={GRID_TOP + GRID_H}
              stroke="#bbbbbb"
              strokeWidth="0.35"
            />
          );
        })}

        {/* Row labels + horizontals */}
        {ROW_LABELS.map((lines, i) => {
          const y = GRID_TOP + i * ROW_H;
          return (
            <g key={i}>
              {lines.map((line, li) => (
                <text
                  key={li}
                  x={MARGIN + 2}
                  y={y + ROW_H / 2 - (lines.length > 1 ? 5 : 0) + li * 9 + 3}
                  fontSize="8"
                  fill={INK}
                  fontFamily={FONT}
                >
                  {line}
                </text>
              ))}
              <line
                x1={GRID_LEFT}
                y1={y + ROW_H}
                x2={GRID_RIGHT}
                y2={y + ROW_H}
                stroke={RULE}
                strokeWidth="0.8"
              />
            </g>
          );
        })}

        <rect
          x={GRID_LEFT}
          y={GRID_TOP}
          width={GRID_W}
          height={GRID_H}
          fill="none"
          stroke={INK}
          strokeWidth="1.2"
        />

        {/* Duty status polyline — thin black, 90° corners, no dots */}
        {log.grid_segments.map((g, idx) => {
          const y = yRow(g.status);
          const x1 = xAt(g.start_minute);
          const x2 = xAt(g.end_minute);
          const prev = idx > 0 ? log.grid_segments[idx - 1] : null;
          return (
            <g key={idx}>
              {prev && prev.status !== g.status && (
                <line
                  x1={x1}
                  y1={yRow(prev.status)}
                  x2={x1}
                  y2={y}
                  stroke={DUTY}
                  strokeWidth="1.35"
                  strokeLinecap="square"
                />
              )}
              <line
                x1={x1}
                y1={y}
                x2={x2}
                y2={y}
                stroke={DUTY}
                strokeWidth="1.5"
                strokeLinecap="square"
              />
              {g.bracket && (
                <path
                  d={`M ${x1} ${y + 7} L ${x1} ${y + 11} L ${x2} ${y + 11} L ${x2} ${y + 7}`}
                  fill="none"
                  stroke={INK}
                  strokeWidth="0.9"
                />
              )}
            </g>
          );
        })}

        {/* TOTAL HOURS column — aligned to rows */}
        <text
          x={GRID_RIGHT + TOTAL_W / 2}
          y={GRID_TOP - 8}
          fontSize="6.5"
          fill={MUTED}
          fontFamily={FONT}
          textAnchor="middle"
          fontWeight="700"
        >
          TOTAL
        </text>
        <text
          x={GRID_RIGHT + TOTAL_W / 2}
          y={GRID_TOP - 1}
          fontSize="6.5"
          fill={MUTED}
          fontFamily={FONT}
          textAnchor="middle"
          fontWeight="700"
        >
          HOURS
        </text>
        <rect
          x={GRID_RIGHT}
          y={GRID_TOP}
          width={TOTAL_W}
          height={GRID_H}
          fill="none"
          stroke={RULE}
          strokeWidth="0.9"
        />
        {(
          [
            log.totals.off,
            log.totals.sb,
            log.totals.drive,
            log.totals.on,
          ] as const
        ).map((v, i) => (
          <g key={i}>
            <line
              x1={GRID_RIGHT}
              y1={GRID_TOP + (i + 1) * ROW_H}
              x2={GRID_RIGHT + TOTAL_W}
              y2={GRID_TOP + (i + 1) * ROW_H}
              stroke={RULE}
              strokeWidth="0.7"
            />
            <text
              x={GRID_RIGHT + TOTAL_W / 2}
              y={GRID_TOP + i * ROW_H + ROW_H / 2 + 3}
              fontSize="11"
              fill={INK}
              fontFamily={FONT}
              textAnchor="middle"
            >
              {fmtHours(v)}
            </text>
          </g>
        ))}
        <line
          x1={GRID_RIGHT + 4}
          y1={GRID_TOP + GRID_H + 10}
          x2={GRID_RIGHT + TOTAL_W - 4}
          y2={GRID_TOP + GRID_H + 10}
          stroke={RULE}
          strokeWidth="0.8"
        />
        <text
          x={GRID_RIGHT + TOTAL_W / 2}
          y={GRID_TOP + GRID_H + 22}
          fontSize="11"
          fontWeight="700"
          fill={INK}
          fontFamily={FONT}
          textAnchor="middle"
        >
          ={fmtHours(grandTotal)}
        </text>
        <line
          x1={GRID_RIGHT + 4}
          y1={GRID_TOP + GRID_H + 26}
          x2={GRID_RIGHT + TOTAL_W - 4}
          y2={GRID_TOP + GRID_H + 26}
          stroke={RULE}
          strokeWidth="0.8"
        />

        {/* ——— REMARKS (directly under grid, same 24h scale) ——— */}
        <text
          x={MARGIN + 2}
          y={remarksRulerY + 3}
          fontSize="9"
          fontWeight="700"
          fill={INK}
          fontFamily={FONT}
        >
          REMARKS
        </text>
        <TimeRuler y={remarksRulerY} showLabels={false} />

        {pins.map((pin, i) => {
          // Translate to tick tip, then rotate. Local y>0 puts alphabetic baseline
          // below the tip so capital glyphs cannot cross the REMARKS axis.
          const tipY = pin.y;
          return (
            <g key={`pin-${i}`}>
              <line
                x1={pin.x}
                y1={remarksRulerY}
                x2={pin.x}
                y2={tipY}
                stroke={RULE}
                strokeWidth="0.85"
              />
              <line
                x1={pin.x - 4}
                y1={tipY}
                x2={pin.x + 4}
                y2={tipY}
                stroke={RULE}
                strokeWidth="0.85"
              />
              <g transform={`translate(${pin.x}, ${tipY}) rotate(55)`}>
                <text
                  x={3}
                  y={11}
                  fontSize="9"
                  fill={INK}
                  fontFamily={FONT}
                  textAnchor="start"
                >
                  {pin.label}
                </text>
              </g>
            </g>
          );
        })}

        {/* Pro / Shipping No. */}
        <text x={MARGIN} y={shippingY + 12} fontSize="8" fill={MUTED} fontFamily={FONT}>
          Pro or Shipping No.
        </text>
        <text
          x={MARGIN + 100}
          y={shippingY + 12}
          fontSize="11"
          fill={INK}
          fontFamily={FONT_ENTRY}
          fontWeight="700"
        >
          {log.header.load_id}
        </text>
        <line
          x1={MARGIN + 100}
          y1={shippingY + 15}
          x2={MARGIN + 220}
          y2={shippingY + 15}
          stroke={RULE}
          strokeWidth="0.7"
        />
        <text x={MARGIN + 240} y={shippingY + 12} fontSize="7" fill={MUTED} fontFamily={FONT}>
          Shipper / Commodity: {log.header.shipper} · {log.header.commodity}
        </text>

        {/* ——— RECAP (document boxes, not cards) ——— */}
        <line
          x1={MARGIN}
          y1={recapY}
          x2={W - MARGIN}
          y2={recapY}
          stroke={RULE}
          strokeWidth="0.8"
        />
        <text x={MARGIN} y={recapY + 12} fontSize="8" fontWeight="700" fill={INK} fontFamily={FONT}>
          Recap: Complete at end of day
        </text>
        <text x={MARGIN} y={recapY + 24} fontSize="8" fill={MUTED} fontFamily={FONT}>
          On duty hours today, Total lines 3 &amp; 4:{" "}
          <tspan fill={INK} fontWeight="700">
            {fmtHours(log.recap.on_duty_today)}
          </tspan>
        </text>

        <text x={MARGIN} y={recapY + 40} fontSize="7.5" fontWeight="700" fill={INK} fontFamily={FONT}>
          70 Hour / 8 Day Drivers
        </text>
        {[
          ["A", a70],
          ["B", b70],
          ["C", c70],
        ].map(([letter, val], i) => (
          <g key={String(letter)}>
            <rect
              x={MARGIN + i * 70}
              y={recapY + 46}
              width={64}
              height={22}
              fill="none"
              stroke={RULE}
              strokeWidth="0.7"
            />
            <text
              x={MARGIN + i * 70 + 6}
              y={recapY + 60}
              fontSize="10"
              fill={INK}
              fontFamily={FONT}
            >
              {letter} {fmtHours(val as number)}
            </text>
          </g>
        ))}
        <text x={MARGIN} y={recapY + 80} fontSize="6" fill={MUTED} fontFamily={FONT}>
          A: on duty last 8 days incl. today · B: available tomorrow (70−A) · C: on duty last 7 days incl.
          today
        </text>

        <text
          x={MARGIN + 280}
          y={recapY + 40}
          fontSize="7.5"
          fontWeight="700"
          fill={MUTED}
          fontFamily={FONT}
        >
          60 Hour / 7 Day Drivers
        </text>
        {["A", "B", "C"].map((letter, i) => (
          <g key={`60-${letter}`}>
            <rect
              x={MARGIN + 280 + i * 54}
              y={recapY + 46}
              width={48}
              height={22}
              fill="none"
              stroke={RULE_LIGHT}
              strokeWidth="0.6"
            />
            <text
              x={MARGIN + 280 + i * 54 + 6}
              y={recapY + 60}
              fontSize="9"
              fill={RULE_LIGHT}
              fontFamily={FONT}
            >
              {letter} —
            </text>
          </g>
        ))}
        <text
          x={MARGIN + 280}
          y={recapY + 80}
          fontSize="6"
          fill={MUTED}
          fontFamily={FONT}
        >
          N/A — carrier uses 70/8
        </text>

        <text
          x={W - MARGIN}
          y={recapY + 24}
          fontSize="7"
          fill={MUTED}
          fontFamily={FONT}
          fontStyle="italic"
          textAnchor="end"
        >
          I certify that these entries are true and correct
        </text>
        <text
          x={W - MARGIN - 4}
          y={recapY + 42}
          fontSize="12"
          fill={INK}
          fontFamily={FONT_ENTRY}
          fontStyle="italic"
          textAnchor="end"
        >
          {log.header.driver_name}
        </text>
        <line
          x1={W - MARGIN - 160}
          y1={recapY + 46}
          x2={W - MARGIN}
          y2={recapY + 46}
          stroke={RULE}
          strokeWidth="0.7"
        />
        <text
          x={W - MARGIN}
          y={recapY + 56}
          fontSize="6"
          fill={MUTED}
          fontFamily={FONT}
          textAnchor="end"
        >
          (DRIVER&apos;S SIGNATURE IN FULL)
        </text>
        <text
          x={W - MARGIN}
          y={recapY + 78}
          fontSize="5.5"
          fill={MUTED}
          fontFamily={FONT}
          textAnchor="end"
        >
          {log.recap.note}
        </text>
      </svg>
    </Box>
  );
}
