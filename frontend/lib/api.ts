import { API_URL } from "./env";
import type { SessionStatus, TradeRecord } from "./types";

function getToken(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(/(?:^|; )icc_token=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : null;
}

function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "ngrok-skip-browser-warning": "1", ...authHeaders(), ...init?.headers },
  });
  if (!res.ok) throw new Error(`API ${path}: ${res.status}`);
  return res.json() as Promise<T>;
}

async function postJSON<T>(path: string, body?: unknown): Promise<T> {
  return fetchJSON<T>(path, {
    method: "POST",
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
}

// Auth
export const login = (username: string, password: string) =>
  postJSON<{ token: string; user: string; error?: string }>("/api/auth/login", { username, password });

export const verifyToken = () =>
  fetchJSON<{ valid: boolean; user?: string }>("/api/auth/verify");

// Session controls
export const startSimulated = (instrumentType = "FUTURES", strategy = "ICC") =>
  postJSON<{ status: string }>(`/api/session/start?instrument_type=${instrumentType}&strategy=${strategy}`);
export const startLive = (paper = true, instrumentType = "FUTURES", optionUnderlying = "MES", strategy = "ICC", tickers?: string[]) => {
  let url = `/api/session/start-live?paper=${paper}&instrument_type=${instrumentType}&option_underlying=${optionUnderlying}&strategy=${strategy}`;
  if (tickers && tickers.length > 0) {
    url += `&tickers=${tickers.join(",")}`;
  }
  return postJSON<{ status: string; mode?: string; instrument_type?: string; strategy?: string; tickers?: string[] }>(url);
};
export const stopSession = () => postJSON<{ status: string }>("/api/session/stop");
export const killSession = () => postJSON<{ status: string }>("/api/session/kill");

// Status
export const getSessionStatus = () => fetchJSON<SessionStatus>("/api/session/status");
export const getSchedulerStatus = () => fetchJSON<Record<string, unknown>>("/api/scheduler/status");

// Data
export const getTrades = (limit = 50) =>
  fetchJSON<TradeRecord[]>(`/api/trades?limit=${limit}`);
export const getConfig = () =>
  fetchJSON<Record<string, unknown>>("/api/config");

// Health
export const getHealth = () => fetchJSON<{ status: string }>("/health");
