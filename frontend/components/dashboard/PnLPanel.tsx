"use client";

import { Panel } from "@/components/ui/Panel";
import { useTradingStore } from "@/stores/tradingStore";
import { formatPnL } from "@/lib/formatters";

export function PnLPanel() {
  const { dailyPnl, tradeCount } = useTradingStore();
  const { text, className } = formatPnL(dailyPnl);

  return (
    <Panel title="Daily P&L">
      <p className={`text-2xl font-bold ${className}`}>{text}</p>
      <p className="mt-1 text-xs text-zinc-500">
        Trades: {tradeCount}
      </p>
    </Panel>
  );
}
