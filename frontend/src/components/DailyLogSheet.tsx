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
const HEADER_H = 168;
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

function fmtHours(h: number): string {
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

function layoutRemarks(remarks: Remark[], baseY: number) {
  const slots: { x: number; y: number; remark: Remark; lane: number }[] = [];
  const laneHeight = 52;
  const minGap = 72;

  for (const remark of remarks) {
    const x = xAt(timeToMinute(remark.time));
    let lane = 0;
    for (;;) {
      const y = baseY + lane * laneHeight;
      const clash = slots.some(
        (s) => s.lane === lane && Math.abs(s.x - x) < minGap,
      );
      if (!clash) {
        slots.push({ x, y, remark, lane });
        break;
      }
      lane += 1;
    }
  }
  return slots;
}

export function DailyLogSheet({ log }: { log: DailyLog }) {
  const dateObj = new Date(log.date + "T12:00:00");
  const month = String(dateObj.getMonth() + 1).padStart(2, "0");
  const day = String(dateObj.getDate()).padStart(2, "0");
  const year = dateObj.getFullYear();
  const remarks = log.remarks;
  const remarkBaseY = GRID_TOP + GRID_H + 36;
  const remarkSlots = layoutRemarks(remarks, remarkBaseY + 28);
  const remarkDepth =
    remarkSlots.length > 0
      ? Math.max(...remarkSlots.map((s) => s.y)) - remarkBaseY + 64
      : 48;
  const recapY = remarkBaseY + remarkDepth + 12;
  const svgH = recapY + 88;

  const grandTotal =
    log.totals.off + log.totals.sb + log.totals.drive + log.totals.on;

  const transitionDots: { x: number; y: number }[] = [];
  log.grid_segments.forEach((g, idx) => {
    const x1 = xAt(g.start_minute);
    const y = yRow(g.status);
    if (idx === 0) {
      transitionDots.push({ x: x1, y });
    }
    const prev = idx > 0 ? log.grid_segments[idx - 1] : null;
    if (prev && prev.status !== g.status) {
      transitionDots.push({ x: x1, y: yRow(prev.status) });
      transitionDots.push({ x: x1, y });
    }
    transitionDots.push({ x: xAt(g.end_minute), y });
  });

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

        {/* Title + date block */}
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
          (24 Hours)
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
        <line
          x1={CX - 88}
          y1={42}
          x2={CX - 32}
          y2={42}
          stroke="#94a3b8"
          strokeWidth="0.8"
        />

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
          ORIGINAL — file at end of trip · DUPLICATE — driver retains 8 days
        </text>
        <text x={W - 14} y="36" fontSize="8" fill="#64748b" textAnchor="end" fontFamily="Arial, sans-serif">
          U.S. DOT · FMCSA Driver&apos;s Daily Log · Time base: Home Terminal (America/Chicago)
        </text>

        {/* Header fields */}
        <UnderlineField x={14} y={58} width={320} label="From:" value={log.from_location} />
        <UnderlineField
          x={360}
          y={58}
          width={320}
          label="To:"
          value={log.to_location}
        />

        <rect x={14} y={88} width={148} height={52} fill={GRID_BLUE_LIGHT} stroke={GRID_BLUE} strokeWidth="0.8" />
        <text x={22} y={104} fontSize="9" fill="#475569" fontFamily="Arial, sans-serif">
          Total Miles Driving Today
        </text>
        <text x={22} y={128} fontSize="16" fontWeight="700" fill={INK} fontFamily="Arial, sans-serif">
          {log.total_miles_driving}
        </text>

        <rect x={170} y={88} width={148} height={52} fill={GRID_BLUE_LIGHT} stroke={GRID_BLUE} strokeWidth="0.8" />
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
          x={360}
          y={148}
          width={200}
          label="Co-Driver:"
          value={log.header.co_driver}
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
                  x={x + (h === 12 ? -12 : 2)}
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

        {/* 15-minute ticks */}
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

        {/* Row labels + horizontal dividers */}
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

        {/* Alternate row shading */}
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

        {/* Duty status line */}
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

        {/* Transition dots */}
        {transitionDots.map((dot, i) => (
          <circle key={i} cx={dot.x} cy={dot.y} r="3.2" fill={DOT_RED} stroke="#fff" strokeWidth="0.6" />
        ))}

        {/* Totals column */}
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

        {/* Remarks timeline */}
        <text
          x={GRID_LEFT}
          y={remarkBaseY}
          fontSize="12"
          fontWeight="700"
          fill={HEADER_BAR}
          fontFamily="Arial, sans-serif"
        >
          REMARKS
        </text>
        <line
          x1={GRID_LEFT}
          y1={remarkBaseY + 6}
          x2={GRID_RIGHT}
          y2={remarkBaseY + 6}
          stroke={GRID_BLUE}
          strokeWidth="0.8"
        />

        {remarkSlots.map(({ x, y, remark }, i) => {
          const bracketTop = GRID_TOP + GRID_H;
          const label = remark.location_label || remark.text;
          const detail = remark.location_label ? remark.text : "";
          return (
            <g key={i}>
              <line
                x1={x}
                y1={bracketTop}
                x2={x}
                y2={y - 8}
                stroke={GRID_BLUE}
                strokeWidth="1"
              />
              <line
                x1={x - 4}
                y1={y - 8}
                x2={x + 4}
                y2={y - 8}
                stroke={GRID_BLUE}
                strokeWidth="1"
              />
              <text
                x={x + 6}
                y={y}
                fontSize="10"
                fill={INK}
                fontFamily="Arial, sans-serif"
                fontWeight="600"
                transform={`rotate(-55 ${x + 6} ${y})`}
              >
                {label}
              </text>
              {detail ? (
                <text
                  x={x + 6}
                  y={y + 14}
                  fontSize="9"
                  fill="#475569"
                  fontFamily="Arial, sans-serif"
                  transform={`rotate(-55 ${x + 6} ${y + 14})`}
                >
                  {remark.time} · {detail}
                </text>
              ) : null}
            </g>
          );
        })}

        {/* Recap footer */}
        <rect
          x={14}
          y={recapY}
          width={W - 28}
          height={72}
          fill="#f8fafc"
          stroke="#cbd5e1"
          strokeWidth="0.8"
          rx="2"
        />
        <text x={24} y={recapY + 18} fontSize="10" fontWeight="700" fill={INK} fontFamily="Arial, sans-serif">
          Recap — 70 Hour / 8 Day (approx.)
        </text>
        <text x={24} y={recapY + 34} fontSize="10" fill="#334155" fontFamily="Arial, sans-serif">
          On duty today (lines 3 &amp; 4): {fmtHours(log.recap.on_duty_today)} h
        </text>
        <text x={24} y={recapY + 50} fontSize="10" fill="#334155" fontFamily="Arial, sans-serif">
          Cycle remaining — start {fmtHours(log.recap.cycle_remaining_start)} h · end{" "}
          {fmtHours(log.recap.cycle_remaining_end)} h · {log.recap.note}
        </text>
        <text
          x={W - 24}
          y={recapY + 34}
          fontSize="9"
          fill="#64748b"
          fontFamily="Arial, sans-serif"
          fontStyle="italic"
          textAnchor="end"
        >
          I certify these entries are true and correct
        </text>
        <text
          x={W - 24}
          y={recapY + 50}
          fontSize="10"
          fill={INK}
          fontFamily="Arial, sans-serif"
          fontWeight="600"
          textAnchor="end"
        >
          {log.header.driver_name}
        </text>

        <text x={14} y={svgH - 8} fontSize="8" fill="#94a3b8" fontFamily="Arial, sans-serif">
          FMCSA-style grid · 15-minute increments · blue line = duty status · red dots = transitions
        </text>
      </svg>
    </Box>
  );
}
