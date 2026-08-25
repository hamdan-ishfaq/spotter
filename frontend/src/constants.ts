/** API + HOS display constants (authoritative rules live on backend). */
export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") || "http://127.0.0.1:8080";

export const HOME_TERMINAL_TZ = "America/Chicago";
