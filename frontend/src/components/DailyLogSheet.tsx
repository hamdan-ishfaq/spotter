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
const ROW_LABELS = [
  ["1. Off Duty"],
  ["2. Sleeper Berth"],
  ["3. Driving"],
  ["4. On Duty", "(Not Driving)"],
];

const W = 980;
const CX = W / 2;
const LABEL_W = 158;
const TOTAL_W = 88;
const GRID_LEFT = LABEL_W + 6;
const GRID_RIGHT = W - TOTAL_W - 12;
const GRID_W = GRID_RIGHT - GRID_LEFT;
const HEADER_H = 198;
const GRID_TOP = HEADER_H + 22;
const GRID_H = 184;
const ROW_H = GRID_H / 4;

const INK = "#0f172a";
const GRID_BLUE = "#5b8fc7";
const GRID_BLUE_LIGHT = "#dce8f4";
const DUTY_BLUE = "#1d4ed8";
const DOT_RED = "#dc2626";
const HEADER_BAR = "#1e3a5f";

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

function UnderlineField({
  x,
  y,
  width,
  label,
  value,
  labelSize = 10,
  valueSize = 11,
}: {
  x: number;
  y: number;
  width: number;
  label: string;
  value: string;
  labelSize?: number;
  valueSize?: number;
}) {
  return (
    <g>
      <text x={x} y={y} fontSize={labelSize} fill="#475569" fontFamily="Arial, sans-serif">
        {label}
      </text>
      <text x={x} y={y + 14} fontSize={valueSize} fill={INK} fontWeight="600" fontFamily="Arial, sans-serif">
        {value}
      </text>
      <line x1={x} y1={y + 18} x2={x + width} y2={y + 18} stroke="#94a3b8" strokeWidth="0.8" />
    </g>
  );
}

/** Location pins under the grid (FMCSA-style) — location only, collision-aware. */
function layoutLocationPins(remarks: Remark[], baseY: number) {
  const pins: { x: number; y: number; label: string; lane: number }[] = [];
  const laneHeight = 44;
  const minGap = 58;
  let lastLoc = "";

  for (const remark of remarks) {
    const label = (remark.location_label || "").trim();
    if (!label || label === "—") {
      continue;
    }
    // One pin per location change (matches completed FMCSA sample grids)
    if (label === lastLoc) {
      continue;
    }
    lastLoc = label;
    const x = xAt(timeToMinute(remark.time));
    let lane = 0;
    for (;;) {
      const clash = pins.some((p) => p.lane === lane && Math.abs(p.x - x) < minGap);
      if (!clash) {
        pins.push({ x, y: baseY + lane * laneHeight, label, lane });
        break;
      }
      lane += 1;
      if (lane > 4) {
        pins.push({ x, y: baseY + lane * laneHeight, label, lane });
        break;
      }
    }
  }
  return pins;
}

/** Shorten long remark text for the list. */
function shortRemark(text: string): string {
  const t = text.trim();
  if (t.length <= 42) {
    return t;
  }
  return `${t.slice(0, 40)}…`;
}

export function DailyLogSheet({ log }: { log: DailyLog }) {
  const dateObj = new Date(log.date + "T12:00:00");
  const month = String(dateObj.getMonth() + 1).padStart(2, "0");
  const day = String(dateObj.getDate()).padStart(2, "0");
  const year = dateObj.getFullYear();
  const remarks = log.remarks;

  const remarkTitleY = GRID_TOP + GRID_H + 28;
  const pinBaseY = remarkTitleY + 22;
  const pins = layoutLocationPins(remarks, pinBaseY);
  const pinDepth =
    pins.length > 0 ? Math.max(...pins.map((p) => p.y)) - pinBaseY + 52 : 28;

  const listTop = pinBaseY + pinDepth + 8;
  const LIST_ROW = 15;
  const listCols = 2;
  const listRows = Math.ceil(Math.max(remarks.length, 1) / listCols);
  const listHeight = Math.max(listRows, 1) * LIST_ROW + 8;
  const recapY = listTop + listHeight + 14;
  const RECAP_H = 118;
  const svgH = recapY + RECAP_H + 18;

  const grandTotal =
    log.totals.off + log.totals.sb + log.totals.drive + log.totals.on;

  const a70 =
    log.recap.a_70_8 ??
    Math.max(0, 70 - (log.recap.cycle_remaining_end ?? 0));
  const b70 = log.recap.b_70_8 ?? log.recap.cycle_remaining_end;
  const c70 = log.recap.c_70_8 ?? a70;

  const periodLabel =
    log.header.period_start_label ||
    log.header.period_start_time ||
    "Midnight (home terminal)";
  const homeTerminal = log.header.home_terminal || log.header.main_office || "—";
  const tz = log.header.time_zone || "America/Chicago";

  const transitionDots: { x: number; y: number }[] = [];
  log.grid_segments.forEach((g, idx) => {
    const x1 = xAt(g.start_minute);
    const y = yRow(g.status);
    const prev = idx > 0 ? log.grid_segments[idx - 1] : null;
    if (!prev) {
      transitionDots.push({ x: x1, y });
      return;
    }
    if (prev.status !== g.status) {
      // Corner at end of previous row + corner on new row (status change)
      transitionDots.push({ x: x1, y: yRow(prev.status) });
      transitionDots.push({ x: x1, y });
    }
  });
  // Final end-of-day point
  const last = log.grid_segments[log.grid_segments.length - 1];
  if (last) {
    transitionDots.push({ x: xAt(last.end_minute), y: yRow(last.status) });
  }

  return (
    <Box
      className="daily-log-sheet"
      sx={{
        bgcolor: "#fff",
        border: "1.5px solid #1e293b",
        borderRadius: "2px",
        p: { xs: 0.5, md: 1 },
        overflow: "auto",
        boxShadow: "0 2px 12px rgba(15,23,42,0.08)",
      }}
    >
      <svg
        viewBox={`0 0 ${W} ${svgH}`}
        width="100%"
        role="img"
        aria-label={`Daily log ${log.date}`}
        style={{ display: "block", minWidth: 720 }}
      >
        <rect x="0" y="0" width={W} height={svgH} fill="#ffffff" />

        <text
          x="14"
          y="26"
          fontFamily="Georgia, 'Times New Roman', serif"
          fontSize="22"
          fontWeight="700"
          fill={INK}
        >
          Driver&apos;s Daily Log
        </text>
        <text x="14" y="44" fontSize="11" fill="#64748b" fontFamily="Arial, sans-serif">
          (One Calendar Day — 24 Hours)
        </text>

        <text x={CX - 60} y="22" fontSize="10" fill="#64748b" fontFamily="Arial, sans-serif">
          (Month)
        </text>
        <text
          x={CX - 60}
          y="38"
          fontSize="14"
          fontWeight="700"
          fill={INK}
          fontFamily="Arial, sans-serif"
          textAnchor="middle"
        >
          {month}
        </text>
        <line x1={CX - 88} y1={42} x2={CX - 32} y2={42} stroke="#94a3b8" strokeWidth="0.8" />

        <text x={CX - 8} y="22" fontSize="10" fill="#64748b" fontFamily="Arial, sans-serif">
          (Day)
        </text>
        <text
          x={CX - 8}
          y="38"
          fontSize="14"
          fontWeight="700"
          fill={INK}
          fontFamily="Arial, sans-serif"
          textAnchor="middle"
        >
          {day}
        </text>
        <line x1={CX - 36} y1={42} x2={CX + 20} y2={42} stroke="#94a3b8" strokeWidth="0.8" />

        <text x={CX + 44} y="22" fontSize="10" fill="#64748b" fontFamily="Arial, sans-serif">
          (Year)
        </text>
        <text
          x={CX + 44}
          y="38"
          fontSize="14"
          fontWeight="700"
          fill={INK}
          fontFamily="Arial, sans-serif"
          textAnchor="middle"
        >
          {year}
        </text>
        <line x1={CX + 16} y1={42} x2={CX + 72} y2={42} stroke="#94a3b8" strokeWidth="0.8" />

        <text x={W - 14} y="22" fontSize="9" fill="#64748b" textAnchor="end" fontFamily="Arial, sans-serif">
          ORIGINAL — Submit to carrier within 13 days
        </text>
        <text x={W - 14} y="36" fontSize="8" fill="#64748b" textAnchor="end" fontFamily="Arial, sans-serif">
          DUPLICATE — Driver retains for 8 days · U.S. DOT / FMCSA
        </text>

        <UnderlineField x={14} y={58} width={320} label="From:" value={log.from_location} />
        <UnderlineField x={360} y={58} width={320} label="To:" value={log.to_location} />
        <UnderlineField
          x={700}
          y={58}
          width={260}
          label="24-hour period starting time:"
          value={periodLabel}
          valueSize={10}
        />

        <rect
          x={14}
          y={88}
          width={148}
          height={52}
          fill={GRID_BLUE_LIGHT}
          stroke={GRID_BLUE}
          strokeWidth="0.8"
        />
        <text x={22} y={104} fontSize="9" fill="#475569" fontFamily="Arial, sans-serif">
          Total Miles Driving Today
        </text>
        <text x={22} y={128} fontSize="16" fontWeight="700" fill={INK} fontFamily="Arial, sans-serif">
          {log.total_miles_driving}
        </text>

        <rect
          x={170}
          y={88}
          width={148}
          height={52}
          fill={GRID_BLUE_LIGHT}
          stroke={GRID_BLUE}
          strokeWidth="0.8"
        />
        <text x={178} y={104} fontSize="9" fill="#475569" fontFamily="Arial, sans-serif">
          Truck / Tractor &amp; Trailer No.
        </text>
        <text x={178} y={128} fontSize="12" fontWeight="600" fill={INK} fontFamily="Arial, sans-serif">
          {log.header.vehicle_number}
        </text>

        <UnderlineField
          x={360}
          y={88}
          width={280}
          label="Name of Carrier or Carriers:"
          value={log.header.carrier_name}
        />
        <UnderlineField
          x={360}
          y={118}
          width={280}
          label="Main Office Address:"
          value={log.header.main_office}
        />

        <UnderlineField
          x={660}
          y={88}
          width={300}
          label="Shipper & Commodity:"
          value={`${log.header.shipper} · ${log.header.commodity}`}
          valueSize={10}
        />
        <UnderlineField
          x={660}
          y={118}
          width={300}
          label="Shipping Documents / Load No.:"
          value={log.header.load_id}
        />

        <UnderlineField
          x={14}
          y={148}
          width={300}
          label="Driver's Signature (Full Name):"
          value={log.header.driver_name}
        />
        <UnderlineField
          x={330}
          y={148}
          width={160}
          label="Co-Driver:"
          value={log.header.co_driver}
        />
        <UnderlineField
          x={510}
          y={148}
          width={220}
          label="Home Terminal Address:"
          value={homeTerminal}
        />
        <UnderlineField
          x={750}
          y={148}
          width={210}
          label="Time base (home terminal):"
          value={tz}
          valueSize={10}
        />

        {/* Time header bar */}
        <rect x={GRID_LEFT} y={GRID_TOP - 20} width={GRID_W} height={18} fill={HEADER_BAR} />
        {Array.from({ length: 25 }, (_, h) => {
          const x = xAt(h * 60);
          return (
            <g key={h}>
              <line
                x1={x}
                y1={GRID_TOP - 20}
                x2={x}
                y2={GRID_TOP + GRID_H}
                stroke={h % 6 === 0 ? GRID_BLUE : "#c5d9eb"}
                strokeWidth={h % 6 === 0 ? 1 : 0.5}
              />
              {h < 24 && hourLabel(h) && (
                <text
                  x={x + (h === 12 || h === 0 ? -10 : 2)}
                  y={GRID_TOP - 7}
                  fontSize="8"
                  fill="#fff"
                  fontFamily="Arial, sans-serif"
                >
                  {hourLabel(h)}
                </text>
              )}
            </g>
          );
        })}

        {Array.from({ length: 96 }, (_, i) => {
          const x = xAt(i * 15);
          return (
            <line
              key={`t${i}`}
              x1={x}
              y1={GRID_TOP}
              x2={x}
              y2={GRID_TOP + (i % 4 === 0 ? 0 : 5)}
              stroke="#b8cfe4"
              strokeWidth="0.5"
            />
          );
        })}

        {ROW_LABELS.map((lines, i) => {
          const y = GRID_TOP + i * ROW_H;
          return (
            <g key={i}>
              {lines.map((line, li) => (
                <text
                  key={li}
                  x={10}
                  y={y + ROW_H / 2 - (lines.length > 1 ? 6 : 0) + li * 12}
                  fontSize="10"
                  fill={INK}
                  fontFamily="Arial, sans-serif"
                  fontWeight={500}
                >
                  {line}
                </text>
              ))}
              <line
                x1={GRID_LEFT}
                y1={y + ROW_H}
                x2={GRID_RIGHT}
                y2={y + ROW_H}
                stroke={GRID_BLUE}
                strokeWidth="0.9"
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
          strokeWidth="1.4"
        />

        {[0, 2].map((i) => (
          <rect
            key={i}
            x={GRID_LEFT}
            y={GRID_TOP + i * ROW_H}
            width={GRID_W}
            height={ROW_H}
            fill={GRID_BLUE_LIGHT}
            opacity={0.35}
          />
        ))}

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
                  stroke={DUTY_BLUE}
                  strokeWidth="2.4"
                  strokeLinecap="square"
                />
              )}
              <line
                x1={x1}
                y1={y}
                x2={x2}
                y2={y}
                stroke={DUTY_BLUE}
                strokeWidth="2.8"
                strokeLinecap="square"
              />
              {g.bracket && (
                <path
                  d={`M ${x1} ${y + 10} L ${x1} ${y + 16} L ${x2} ${y + 16} L ${x2} ${y + 10}`}
                  fill="none"
                  stroke={INK}
                  strokeWidth="1.2"
                />
              )}
            </g>
          );
        })}

        {transitionDots.map((dot, i) => (
          <circle
            key={i}
            cx={dot.x}
            cy={dot.y}
            r="3.2"
            fill={DOT_RED}
            stroke="#fff"
            strokeWidth="0.6"
          />
        ))}

        <text
          x={GRID_RIGHT + 10}
          y={GRID_TOP - 7}
          fontSize="9"
          fill="#475569"
          fontFamily="Arial, sans-serif"
          fontWeight="600"
        >
          Total Hours
        </text>
        <rect
          x={GRID_RIGHT + 4}
          y={GRID_TOP}
          width={TOTAL_W}
          height={GRID_H}
          fill="#f8fafc"
          stroke={GRID_BLUE}
          strokeWidth="0.8"
        />
        {(
          [
            ["off", log.totals.off],
            ["sb", log.totals.sb],
            ["drive", log.totals.drive],
            ["on", log.totals.on],
          ] as const
        ).map(([k, v], i) => (
          <text
            key={k}
            x={GRID_RIGHT + TOTAL_W / 2 + 4}
            y={GRID_TOP + i * ROW_H + ROW_H / 2 + 4}
            fontSize="13"
            fill={INK}
            fontFamily="Arial, sans-serif"
            fontWeight="600"
            textAnchor="middle"
          >
            {fmtHours(v)}
          </text>
        ))}
        <line
          x1={GRID_RIGHT + 4}
          y1={GRID_TOP + GRID_H + 4}
          x2={GRID_RIGHT + TOTAL_W + 4}
          y2={GRID_TOP + GRID_H + 4}
          stroke={INK}
          strokeWidth="0.8"
        />
        <text
          x={GRID_RIGHT + TOTAL_W / 2 + 4}
          y={GRID_TOP + GRID_H + 20}
          fontSize="13"
          fontWeight="700"
          fill={INK}
          fontFamily="Arial, sans-serif"
          textAnchor="middle"
        >
          = {fmtHours(grandTotal)}
        </text>

        <text
          x={GRID_LEFT}
          y={remarkTitleY}
          fontSize="12"
          fontWeight="700"
          fill={HEADER_BAR}
          fontFamily="Arial, sans-serif"
        >
          REMARKS
        </text>
        <text
          x={GRID_LEFT + 78}
          y={remarkTitleY}
          fontSize="9"
          fill="#64748b"
          fontFamily="Arial, sans-serif"
        >
          Location pins under timeline · full duty changes listed below (home terminal time)
        </text>
        <line
          x1={GRID_LEFT}
          y1={remarkTitleY + 6}
          x2={GRID_RIGHT}
          y2={remarkTitleY + 6}
          stroke={GRID_BLUE}
          strokeWidth="0.8"
        />

        {/* FMCSA-style location pins — City, ST only, staggered */}
        {pins.map((pin, i) => {
          const bracketTop = GRID_TOP + GRID_H;
          return (
            <g key={`pin-${i}`}>
              <line
                x1={pin.x}
                y1={bracketTop}
                x2={pin.x}
                y2={pin.y - 4}
                stroke={GRID_BLUE}
                strokeWidth="1.1"
              />
              <line
                x1={pin.x - 5}
                y1={pin.y - 4}
                x2={pin.x + 5}
                y2={pin.y - 4}
                stroke={GRID_BLUE}
                strokeWidth="1.1"
              />
              <text
                x={pin.x + 4}
                y={pin.y + 2}
                fontSize="10"
                fill={DUTY_BLUE}
                fontFamily="Arial, sans-serif"
                fontWeight="600"
                transform={`rotate(-58 ${pin.x + 4} ${pin.y + 2})`}
              >
                {pin.label}
              </text>
            </g>
          );
        })}

        {/* Clean chronological list — no overlap */}
        <rect
          x={14}
          y={listTop - 4}
          width={W - 28}
          height={listHeight + 4}
          fill="#f8fafc"
          stroke="#e2e8f0"
          strokeWidth="0.6"
          rx="2"
        />
        {remarks.length === 0 ? (
          <text
            x={24}
            y={listTop + 12}
            fontSize="10"
            fill="#94a3b8"
            fontFamily="Arial, sans-serif"
          >
            No duty-status changes this day
          </text>
        ) : (
          remarks.map((r, i) => {
            const col = i % listCols;
            const row = Math.floor(i / listCols);
            const colW = (W - 48) / listCols;
            const x = 24 + col * colW;
            const y = listTop + 12 + row * LIST_ROW;
            return (
              <text key={i} x={x} y={y} fontSize="10" fill={INK} fontFamily="Arial, sans-serif">
                <tspan fill="#64748b" fontWeight="600">
                  {r.time}
                </tspan>
                <tspan fill="#94a3b8">{"  ·  "}</tspan>
                <tspan fontWeight="600" fill={DUTY_BLUE}>
                  {r.location_label}
                </tspan>
                <tspan fill="#64748b">{"  —  "}</tspan>
                <tspan fill="#334155">{shortRemark(r.text)}</tspan>
              </text>
            );
          })
        )}

        {/* Recap: FMCSA A/B/C style */}
        <rect
          x={14}
          y={recapY}
          width={W - 28}
          height={RECAP_H}
          fill="#f8fafc"
          stroke="#cbd5e1"
          strokeWidth="0.8"
          rx="2"
        />
        <text x={24} y={recapY + 16} fontSize="10" fontWeight="700" fill={INK} fontFamily="Arial, sans-serif">
          Recap: Complete at end of day
        </text>
        <text x={24} y={recapY + 32} fontSize="10" fill="#334155" fontFamily="Arial, sans-serif">
          On duty hours today (Total lines 3 &amp; 4): {fmtHours(log.recap.on_duty_today)} h
        </text>

        {/* 70/8 columns */}
        <text x={24} y={recapY + 52} fontSize="9" fontWeight="700" fill={HEADER_BAR} fontFamily="Arial, sans-serif">
          70 Hour / 8 Day Drivers
        </text>
        {[
          ["A", a70, "Total hours on duty last 8 days including today"],
          ["B", b70, "Total hours available tomorrow (70 − A)"],
          ["C", c70, "Total hours on duty last 7 days including today"],
        ].map(([letter, val, desc], i) => (
          <g key={String(letter)}>
            <rect
              x={24 + i * 150}
              y={recapY + 58}
              width={140}
              height={36}
              fill="#fff"
              stroke={GRID_BLUE}
              strokeWidth="0.8"
            />
            <text
              x={32 + i * 150}
              y={recapY + 72}
              fontSize="10"
              fontWeight="700"
              fill={INK}
              fontFamily="Arial, sans-serif"
            >
              {letter}: {fmtHours(val as number)}
            </text>
            <text
              x={32 + i * 150}
              y={recapY + 86}
              fontSize="7.5"
              fill="#64748b"
              fontFamily="Arial, sans-serif"
            >
              {desc as string}
            </text>
          </g>
        ))}

        {/* 60/7 — carrier uses 70/8 */}
        <text x={500} y={recapY + 52} fontSize="9" fontWeight="700" fill="#94a3b8" fontFamily="Arial, sans-serif">
          60 Hour / 7 Day Drivers
        </text>
        {["A", "B", "C"].map((letter, i) => (
          <g key={`60-${letter}`}>
            <rect
              x={500 + i * 88}
              y={recapY + 58}
              width={80}
              height={36}
              fill="#f1f5f9"
              stroke="#cbd5e1"
              strokeWidth="0.8"
            />
            <text
              x={508 + i * 88}
              y={recapY + 78}
              fontSize="11"
              fill="#94a3b8"
              fontFamily="Arial, sans-serif"
            >
              {letter}: —
            </text>
          </g>
        ))}
        <text x={500} y={recapY + 106} fontSize="8" fill="#94a3b8" fontFamily="Arial, sans-serif">
          N/A — carrier operates on 70/8 schedule
        </text>

        <text
          x={W - 24}
          y={recapY + 32}
          fontSize="9"
          fill="#64748b"
          fontFamily="Arial, sans-serif"
          fontStyle="italic"
          textAnchor="end"
        >
          I certify that these entries are true and correct
        </text>
        <text
          x={W - 24}
          y={recapY + 48}
          fontSize="10"
          fill={INK}
          fontFamily="Arial, sans-serif"
          fontWeight="600"
          textAnchor="end"
        >
          {log.header.driver_name}
        </text>

        <text x={24} y={recapY + RECAP_H - 8} fontSize="8" fill="#94a3b8" fontFamily="Arial, sans-serif">
          {log.recap.note}
        </text>

        <text x={14} y={svgH - 6} fontSize="8" fill="#94a3b8" fontFamily="Arial, sans-serif">
          FMCSA-style grid · 15-minute increments · blue line = duty status · red dots = transitions
        </text>
      </svg>
    </Box>
  );
}
