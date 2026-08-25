import { Box, Typography } from "@mui/material";

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
const ROW_LABELS = ["Off Duty", "Sleeper Berth", "Driving", "On Duty (Not Driving)"];

const W = 900;
const GRID_TOP = 130;
const GRID_H = 160;
const ROW_H = GRID_H / 4;
const LABEL_W = 120;
const TOTAL_W = 70;
const GRID_LEFT = LABEL_W;
const GRID_RIGHT = W - TOTAL_W - 16;
const GRID_W = GRID_RIGHT - GRID_LEFT;

function xAt(minute: number) {
  return GRID_LEFT + (Math.min(1440, Math.max(0, minute)) / 1440) * GRID_W;
}

function yRow(status: string) {
  return GRID_TOP + (ROW[status] ?? 0) * ROW_H + ROW_H / 2;
}

export function DailyLogSheet({ log }: { log: DailyLog }) {
  const dateObj = new Date(log.date + "T12:00:00");
  const month = dateObj.getMonth() + 1;
  const day = dateObj.getDate();
  const year = dateObj.getFullYear();
  const remarks = log.remarks;
  const remarkBlock = Math.max(remarks.length, 1) * 14;
  const svgH = Math.max(520, GRID_TOP + GRID_H + 70 + remarkBlock + 40);

  return (
    <Box className="daily-log-sheet" sx={{ bgcolor: "#FFFdf8", border: "1px solid #1a1a1a", p: 1, overflow: "auto" }}>
      <svg viewBox={`0 0 ${W} ${svgH}`} width="100%" role="img" aria-label={`Daily log ${log.date}`}>
        <rect x="0" y="0" width={W} height={svgH} fill="#FFFdf8" />
        <text x="16" y="28" fontFamily="Georgia, serif" fontSize="20" fontWeight="700" fill="#15202B">
          Drivers Daily Log (24 hours)
        </text>
        <text x="16" y="52" fontSize="12" fill="#333">
          Date: {month}/{day}/{year} &nbsp;&nbsp; From: {log.from_location} &nbsp;&nbsp; To: {log.to_location}
        </text>
        <text x="16" y="72" fontSize="12" fill="#333">
          Total miles driving today: {log.total_miles_driving}
        </text>
        <text x="16" y="92" fontSize="11" fill="#555">
          Carrier: {log.header.carrier_name} · Office: {log.header.main_office} · Unit: {log.header.vehicle_number} · Co-driver: {log.header.co_driver}
        </text>
        <text x="16" y="108" fontSize="11" fill="#555">
          Shipper: {log.header.shipper} · {log.header.commodity} · {log.header.load_id} · Driver: {log.header.driver_name}
        </text>
        <text x="16" y="122" fontSize="10" fill="#555" fontStyle="italic">
          I certify that these entries are true and correct — {log.header.driver_name}
        </text>

        <rect x={GRID_LEFT} y={GRID_TOP - 18} width={GRID_W} height="16" fill="#1B3A4B" />
        {Array.from({ length: 25 }, (_, h) => {
          const x = xAt(h * 60);
          return (
            <g key={h}>
              <line x1={x} y1={GRID_TOP - 18} x2={x} y2={GRID_TOP + GRID_H} stroke="#bbb" strokeWidth={h % 6 === 0 ? 1.2 : 0.5} />
              {h < 24 && (
                <text x={x + 2} y={GRID_TOP - 6} fontSize="9" fill="#fff">
                  {h === 0 ? "Mid" : h === 12 ? "Noon" : h}
                </text>
              )}
            </g>
          );
        })}
        {Array.from({ length: 96 }, (_, i) => {
          const x = xAt(i * 15);
          return <line key={`t${i}`} x1={x} y1={GRID_TOP} x2={x} y2={GRID_TOP + 4} stroke="#999" strokeWidth="0.5" />;
        })}

        {ROW_LABELS.map((label, i) => {
          const y = GRID_TOP + i * ROW_H;
          return (
            <g key={label}>
              <text x="8" y={y + ROW_H / 2 + 4} fontSize="11" fill="#15202B">
                {i + 1}. {label}
              </text>
              <line x1={GRID_LEFT} y1={y + ROW_H} x2={GRID_RIGHT} y2={y + ROW_H} stroke="#222" strokeWidth="0.8" />
            </g>
          );
        })}
        <rect x={GRID_LEFT} y={GRID_TOP} width={GRID_W} height={GRID_H} fill="none" stroke="#111" strokeWidth="1.5" />

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
                  stroke="#111"
                  strokeWidth="1.6"
                />
              )}
              <line x1={x1} y1={y} x2={x2} y2={y} stroke="#111" strokeWidth="2.2" strokeLinecap="square" />
              {g.bracket && (
                <path
                  d={`M ${x1} ${y + 8} L ${x1} ${y + 14} L ${x2} ${y + 14} L ${x2} ${y + 8}`}
                  fill="none"
                  stroke="#111"
                  strokeWidth="1.4"
                />
              )}
            </g>
          );
        })}

        <text x={GRID_RIGHT + 8} y={GRID_TOP - 6} fontSize="10" fill="#333">
          Totals
        </text>
        {(
          [
            ["off", log.totals.off],
            ["sb", log.totals.sb],
            ["drive", log.totals.drive],
            ["on", log.totals.on],
          ] as const
        ).map(([k, v], i) => (
          <text key={k} x={GRID_RIGHT + 8} y={GRID_TOP + i * ROW_H + ROW_H / 2 + 4} fontSize="12" fill="#111">
            {v.toFixed(2)}
          </text>
        ))}
        <text x={GRID_RIGHT + 8} y={GRID_TOP + GRID_H + 18} fontSize="12" fontWeight="700" fill="#111">
          ={(log.totals.off + log.totals.sb + log.totals.drive + log.totals.on).toFixed(2)}
        </text>

        <text x="16" y={GRID_TOP + GRID_H + 40} fontSize="13" fontWeight="700" fill="#15202B">
          Remarks
        </text>
        {remarks.map((r, i) => (
          <text key={i} x="16" y={GRID_TOP + GRID_H + 58 + i * 14} fontSize="11" fill="#333">
            {r.time} — {r.location_label} — {r.text}
          </text>
        ))}

        <text x="16" y={svgH - 20} fontSize="11" fill="#333">
          Recap (70/8 approx): on-duty today {log.recap.on_duty_today}h · cycle rem start {log.recap.cycle_remaining_start} · end{" "}
          {log.recap.cycle_remaining_end} · {log.recap.note}
        </text>
      </svg>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5, px: 1 }}>
        Drawn FMCSA-style grid · 15-minute ticks · brackets mark stationary on-duty
      </Typography>
    </Box>
  );
}
