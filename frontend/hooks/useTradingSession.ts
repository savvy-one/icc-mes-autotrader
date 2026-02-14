"use client";

import { useCallback } from "react";
import { useSessionStore } from "@/stores/sessionStore";
import * as api from "@/lib/api";

export function useTradingSession() {
  const { loading, error, setLoading, setError } = useSessionStore();

  const exec = useCallback(
    async (action: () => Promise<unknown>) => {
      setLoading(true);
      setError(null);
      try {
        await action();
      } catch (e) {
        setError(e instanceof Error ? e.message : "Unknown error");
      } finally {
        setLoading(false);
      }
    },
    [setLoading, setError],
  );

  return {
    loading,
    error,
    startSimulated: () => exec(api.startSimulated),
    startLive: () => exec(api.startLive),
    stop: () => exec(api.stopSession),
    kill: () => exec(api.killSession),
  };
}
