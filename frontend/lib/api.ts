import { API_URL } from "./env";
import type { SessionStatus, TradeRecord } from "./types";

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, init);
  if (!res.ok) throw new Error(`API ${path}: ${res.status}`);
  return res.json() as Promise<T>;
}

async function postJSON<T>(path: string): Promise<T> {
  return fetchJSON<T>(path, { method: "POST" });
}

// Session controls
export const startSimulated = () => postJSON<{ status: string }>("/api/session/start");
export const startLive = (paper = true) =>
  postJSON<{ status: string; mode?: string }>(`/api/session/start-live?paper=${paper}`);
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
