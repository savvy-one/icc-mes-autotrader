"use client";

import { useCallback } from "react";
import { useSessionStore } from "@/stores/sessionStore";
import * as api from "@/lib/api";
import type { InstrumentType, OptionUnderlying, StrategyName } from "@/lib/types";

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
    startSimulated: (instrumentType: InstrumentType = "FUTURES", strategy: StrategyName = "ICC") =>
      exec(() => api.startSimulated(instrumentType, strategy)),
    startLive: (
      paper = true,
      instrumentType: InstrumentType = "FUTURES",
      optionUnderlying: OptionUnderlying = "MES",
      strategy: StrategyName = "ICC",
      tickers?: string[],
    ) => exec(() => api.startLive(paper, instrumentType, optionUnderlying, strategy, tickers)),
    stop: () => exec(api.stopSession),
    kill: () => exec(api.killSession),
  };
}
