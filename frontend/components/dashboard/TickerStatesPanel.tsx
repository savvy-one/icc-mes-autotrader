"use client";

import { Panel } from "@/components/ui/Panel";
import { useTradingStore } from "@/stores/tradingStore";

const fsmColor: Record<string, string> = {
  FLAT: "text-zinc-500",
  ORB_BUILDING: "text-amber-400",
  ORB_ARMED: "text-amber-300",
  IN_TRADE_UP: "text-green-400",
  IN_TRADE_DOWN: "text-red-400",
};

export function TickerStatesPanel() {
  const { multiTicker, tickers, activeTicker, tickerStates } = useTradingStore();

  if (!multiTicker || tickers.length === 0) return null;

  return (
    <Panel title="Multi-Ticker ORB" className="col-span-full">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {tickers.map((ticker) => {
          const ts = tickerStates[ticker];
          if (!ts) return null;

          const isActive = activeTicker === ticker;
          const stateColor = fsmColor[ts.fsm_state] ?? "text-zinc-400";
          const hasRange = ts.range_high != null && ts.range_low != null;

          return (
            <div
              key={ticker}
              className={`rounded-lg border p-3 ${
                isActive
                  ? "border-amber-500 bg-amber-950/30"
                  : "border-zinc-700 bg-zinc-800/50"
              }`}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="font-mono font-bold text-sm">
                  {ticker}
                </span>
                <span className={`text-xs font-medium ${stateColor}`}>
                  {ts.fsm_state.replace(/_/g, " ")}
                </span>
              </div>

              {ts.last_price != null && (
                <p className="text-lg font-bold text-zinc-100">
                  ${ts.last_price.toFixed(2)}
                </p>
              )}

              {hasRange && (
                <div className="mt-1 text-xs text-zinc-400 space-y-0.5">
                  <div className="flex justify-between">
                    <span>Range H</span>
                    <span className="text-zinc-300">{ts.range_high!.toFixed(2)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Range L</span>
                    <span className="text-zinc-300">{ts.range_low!.toFixed(2)}</span>
                  </div>
                  {ts.range_height != null && (
                    <div className="flex justify-between">
                      <span>Height</span>
                      <span className="text-zinc-300">${ts.range_height.toFixed(2)}</span>
                    </div>
                  )}
                </div>
              )}

              <div className="mt-1.5 flex items-center gap-2 text-xs text-zinc-500">
                <span>{ts.candle_count} bars</span>
                {ts.trade_taken && (
                  <span className="text-emerald-500">traded</span>
                )}
                {isActive && (
                  <span className="text-amber-400 font-medium">ACTIVE</span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}
