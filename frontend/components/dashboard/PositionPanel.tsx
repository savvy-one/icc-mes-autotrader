"use client";

import { Panel } from "@/components/ui/Panel";
import { useTradingStore } from "@/stores/tradingStore";
import { formatPrice, formatPnL } from "@/lib/formatters";

export function PositionPanel() {
  const position = useTradingStore((s) => s.position);

  if (!position || position.side === "FLAT") {
    return (
      <Panel title="Position">
        <p className="text-2xl font-bold text-zinc-500">FLAT</p>
      </Panel>
    );
  }

  const { text: pnlText, className: pnlClass } = formatPnL(
    position.unrealized_pnl,
  );

  return (
    <Panel title="Position">
      <p
        className={`text-xl font-bold ${
          position.side === "LONG" ? "text-green-400" : "text-red-400"
        }`}
      >
        {position.side} @ {formatPrice(position.entry_price)}
      </p>
      <div className="mt-2 grid grid-cols-3 gap-2 text-xs text-zinc-400">
        <div>
          <span className="block text-zinc-500">Stop</span>
          {formatPrice(position.stop_price)}
        </div>
        <div>
          <span className="block text-zinc-500">Target</span>
          {formatPrice(position.target_price)}
        </div>
        <div>
          <span className="block text-zinc-500">Unrealized</span>
          <span className={pnlClass}>{pnlText}</span>
        </div>
      </div>
    </Panel>
  );
}
