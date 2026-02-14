"use client";

import { Panel } from "@/components/ui/Panel";
import { useTradingStore } from "@/stores/tradingStore";
import type { FSMState } from "@/lib/types";

const stateColors: Record<FSMState, string> = {
  FLAT: "text-zinc-300",
  INDICATION_UP: "text-blue-400",
  INDICATION_DOWN: "text-blue-400",
  CORRECTION_UP: "text-yellow-400",
  CORRECTION_DOWN: "text-yellow-400",
  CONTINUATION_UP: "text-cyan-400",
  CONTINUATION_DOWN: "text-cyan-400",
  IN_TRADE_UP: "text-green-400",
  IN_TRADE_DOWN: "text-red-400",
  EXIT: "text-orange-400",
  RISK_BLOCKED: "text-red-500",
};

export function FSMStatePanel() {
  const { fsmState, candleCount } = useTradingStore();
  const colorClass = stateColors[fsmState] ?? "text-zinc-300";

  return (
    <Panel title="FSM State">
      <p className={`text-2xl font-bold ${colorClass}`}>
        {fsmState.replace(/_/g, " ")}
      </p>
      <p className="mt-1 text-xs text-zinc-500">
        Candles: {candleCount}
      </p>
    </Panel>
  );
}
