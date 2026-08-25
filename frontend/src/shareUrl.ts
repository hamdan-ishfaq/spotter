import type { PlanRequest } from "./api/types";

/** Compact query keys for shareable trip URLs (no server storage). */
export function planToSearchParams(body: PlanRequest): URLSearchParams {
  const params = new URLSearchParams();
  params.set("c", body.current_location.trim());
  params.set("p", body.pickup_location.trim());
  params.set("d", body.dropoff_location.trim());
  params.set("cycle", String(body.current_cycle_used_hours));
  if (body.start_datetime) {
    params.set("start", body.start_datetime);
  }
  return params;
}

export function searchParamsToPlan(params: URLSearchParams): PlanRequest | null {
  const current = params.get("c")?.trim();
  const pickup = params.get("p")?.trim();
  const dropoff = params.get("d")?.trim();
  const cycleRaw = params.get("cycle");
  if (!current || !pickup || !dropoff || cycleRaw === null || cycleRaw.trim() === "") {
    return null;
  }
  const cycle = Number(cycleRaw);
  if (!Number.isFinite(cycle) || cycle < 0 || cycle > 70) {
    return null;
  }
  const start = params.get("start")?.trim();
  return {
    current_location: current,
    pickup_location: pickup,
    dropoff_location: dropoff,
    current_cycle_used_hours: cycle,
    start_datetime: start || null,
  };
}

export function buildShareUrl(body: PlanRequest): string {
  const url = new URL(window.location.href);
  url.search = planToSearchParams(body).toString();
  return url.toString();
}

export function readPlanFromLocation(search = window.location.search): PlanRequest | null {
  if (!search || search === "?") {
    return null;
  }
  return searchParamsToPlan(new URLSearchParams(search));
}
