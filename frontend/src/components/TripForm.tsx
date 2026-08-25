import { useEffect, useMemo, useRef, useState } from "react";
import {
  Autocomplete,
  Box,
  Button,
  Chip,
  Stack,
  TextField,
  CircularProgress,
} from "@mui/material";
import type { PlanRequest } from "../api/types";
import { autocomplete } from "../api/client";

const DEMOS: Record<string, PlanRequest> = {
  Short: {
    current_location: "Dallas, TX",
    pickup_location: "Dallas, TX",
    dropoff_location: "Houston, TX",
    current_cycle_used_hours: 10,
    start_datetime: "2026-08-25T06:00:00",
  },
  Long: {
    current_location: "Chicago, IL",
    pickup_location: "Chicago, IL",
    dropoff_location: "Los Angeles, CA",
    current_cycle_used_hours: 15,
    start_datetime: "2026-08-25T06:00:00",
  },
  Cycle: {
    current_location: "Phoenix, AZ",
    pickup_location: "Phoenix, AZ",
    dropoff_location: "Atlanta, GA",
    current_cycle_used_hours: 65,
    start_datetime: "2026-08-25T06:00:00",
  },
};

type Props = {
  loading: boolean;
  disabled?: boolean;
  onSubmit: (body: PlanRequest) => void;
  initial?: Partial<PlanRequest>;
};

export function TripForm({ loading, disabled = false, onSubmit, initial }: Props) {
  const [current, setCurrent] = useState(initial?.current_location ?? "");
  const [pickup, setPickup] = useState(initial?.pickup_location ?? "");
  const [dropoff, setDropoff] = useState(initial?.dropoff_location ?? "");
  const [cycle, setCycle] = useState(String(initial?.current_cycle_used_hours ?? 10));
  const [start, setStart] = useState(
    (initial?.start_datetime ?? "2026-08-25T06:00:00").slice(0, 16),
  );

  const canSubmit = useMemo(() => {
    const cycleNum = Number(cycle);
    return (
      Boolean(current.trim() && pickup.trim() && dropoff.trim()) &&
      Number.isFinite(cycleNum) &&
      cycleNum >= 0 &&
      cycleNum <= 70
    );
  }, [current, pickup, dropoff, cycle]);

  function applyDemo(key: string) {
    const d = DEMOS[key];
    if (!d) return;
    setCurrent(d.current_location);
    setPickup(d.pickup_location);
    setDropoff(d.dropoff_location);
    setCycle(String(d.current_cycle_used_hours));
    setStart((d.start_datetime || "2026-08-25T06:00").slice(0, 16));
  }

  function submit() {
    const cycleNum = Number(cycle);
    if (!Number.isFinite(cycleNum) || cycleNum < 0 || cycleNum > 70) {
      return;
    }
    onSubmit({
      current_location: current.trim(),
      pickup_location: pickup.trim(),
      dropoff_location: dropoff.trim(),
      current_cycle_used_hours: cycleNum,
      start_datetime: start ? toApiDateTime(start) : null,
    });
  }

  return (
    <Box>
      <Stack direction="row" spacing={1} sx={{ mb: 2, flexWrap: "wrap", gap: 1 }} className="no-print">
        {Object.keys(DEMOS).map((k) => (
          <Chip
            key={k}
            label={`Demo: ${k}`}
            onClick={() => applyDemo(k)}
            clickable={!disabled && !loading}
            disabled={disabled || loading}
            color="secondary"
            variant="outlined"
          />
        ))}
      </Stack>
      <Stack spacing={2}>
        <LocationInput label="Current location" value={current} onChange={setCurrent} />
        <LocationInput label="Pickup location" value={pickup} onChange={setPickup} />
        <LocationInput label="Dropoff location" value={dropoff} onChange={setDropoff} />
        <TextField
          label="Current cycle used (hrs)"
          type="number"
          value={cycle}
          onChange={(e) => setCycle(e.target.value)}
          slotProps={{ htmlInput: { min: 0, max: 70, step: 0.25 } }}
          fullWidth
        />
        <TextField
          label="Start (home terminal)"
          type="datetime-local"
          value={start}
          onChange={(e) => setStart(e.target.value)}
          fullWidth
          slotProps={{ inputLabel: { shrink: true } }}
        />
        <Button
          variant="contained"
          size="large"
          disabled={!canSubmit || loading || disabled}
          onClick={submit}
          startIcon={loading ? <CircularProgress size={18} color="inherit" /> : undefined}
        >
          {loading ? "Planning…" : disabled ? "Waiting for API…" : "Plan trip"}
        </Button>
      </Stack>
    </Box>
  );
}

function toApiDateTime(value: string): string {
  // datetime-local: "YYYY-MM-DDTHH:mm" or already has seconds
  const v = value.trim();
  if (!v) return v;
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/.test(v)) {
    return v.slice(0, 19);
  }
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(v)) {
    return `${v}:00`;
  }
  return v;
}

function LocationInput({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  const [options, setOptions] = useState<string[]>([]);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
    };
  }, []);

  return (
    <Autocomplete
      freeSolo
      options={options}
      inputValue={value}
      onInputChange={(_, v) => {
        onChange(v);
        if (debounceRef.current) {
          clearTimeout(debounceRef.current);
        }
        if (v.trim().length >= 3) {
          debounceRef.current = setTimeout(() => {
            autocomplete(v)
              .then((r) => setOptions(r.map((x) => x.label)))
              .catch(() => setOptions([]));
          }, 350);
        } else {
          setOptions([]);
        }
      }}
      renderInput={(params) => <TextField {...params} label={label} fullWidth />}
    />
  );
}
