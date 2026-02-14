import { create } from "zustand";

interface SessionStore {
  running: boolean;
  mode: string; // "simulated" | "live" | ""
  loading: boolean;
  error: string | null;

  setRunning: (running: boolean) => void;
  setMode: (mode: string) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
}

export const useSessionStore = create<SessionStore>((set) => ({
  running: false,
  mode: "",
  loading: false,
  error: null,

  setRunning: (running) => set({ running }),
  setMode: (mode) => set({ mode }),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),
}));
