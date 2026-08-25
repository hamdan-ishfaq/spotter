import { API_BASE_URL } from "../constants";
import type { AutocompleteResult, PlanRequest, PlanResponse } from "./types";

export class ApiError extends Error {
  code: string;
  fields?: Record<string, unknown>;

  constructor(code: string, message: string, fields?: Record<string, unknown>) {
    super(message);
    this.code = code;
    this.fields = fields;
  }
}

async function parseError(res: Response): Promise<never> {
  try {
    const body = await res.json();
    throw new ApiError(
      body?.error?.code ?? "INTERNAL_ERROR",
      body?.error?.message ?? res.statusText,
      body?.error?.fields,
    );
  } catch (e) {
    if (e instanceof ApiError) throw e;
    throw new ApiError("INTERNAL_ERROR", res.statusText || "Request failed");
  }
}

/** Wake Render Free instance — retries for cold starts (up to ~40s). */
export async function healthCheck(
  maxAttempts = 5,
  pauseMs = 8000,
): Promise<boolean> {
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      const res = await fetch(`${API_BASE_URL}/api/health/`, {
        signal: AbortSignal.timeout(60000),
      });
      if (res.ok) {
        return true;
      }
    } catch {
      /* Render may still be waking */
    }
    if (attempt < maxAttempts - 1) {
      await new Promise((resolve) => setTimeout(resolve, pauseMs));
    }
  }
  return false;
}

export async function autocomplete(q: string): Promise<AutocompleteResult[]> {
  const res = await fetch(
    `${API_BASE_URL}/api/autocomplete/?q=${encodeURIComponent(q)}`,
  );
  if (!res.ok) await parseError(res);
  const data = await res.json();
  return data.results ?? [];
}

export async function planTrip(body: PlanRequest): Promise<PlanResponse> {
  const res = await fetch(`${API_BASE_URL}/api/plan/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) await parseError(res);
  return res.json();
}
