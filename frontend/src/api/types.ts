export type DutyStatus = "OFF" | "SB" | "D" | "ON";

export interface PlanRequest {
  current_location: string;
  pickup_location: string;
  dropoff_location: string;
  current_cycle_used_hours: number;
  start_datetime?: string | null;
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    fields?: Record<string, unknown>;
  };
}

export interface PlanResponse {
  summary: Record<string, unknown>;
  places: Record<string, unknown>;
  route: {
    geometry: [number, number][];
    stops: Array<Record<string, unknown>>;
  };
  instructions: Array<Record<string, unknown>>;
  timeline: Array<Record<string, unknown>>;
  daily_logs: Array<Record<string, unknown>>;
  assumptions: string[];
}

export interface AutocompleteResult {
  label: string;
  lat?: number;
  lng?: number;
}
