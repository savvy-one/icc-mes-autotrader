"use client";

import { Panel } from "@/components/ui/Panel";
import { useTradingStore } from "@/stores/tradingStore";
import { formatPrice } from "@/lib/formatters";

export function OptionContractPanel() {
  const contract = useTradingStore((s) => s.optionContract);

  if (!contract) {
    return (
      <Panel title="Option Contract">
        <p className="text-sm text-zinc-500">No active contract</p>
      </Panel>
    );
  }

  return (
    <Panel title="Option Contract">
      <p className="text-lg font-bold font-mono tracking-tight text-zinc-100">
        {contract.symbol}
      </p>
      <div className="mt-2 grid grid-cols-3 gap-2 text-xs text-zinc-400">
        <div>
          <span className="block text-zinc-500">Type</span>
          <span
            className={
              contract.option_type === "CALL"
                ? "text-green-400 font-semibold"
                : "text-red-400 font-semibold"
            }
          >
            {contract.option_type}
          </span>
        </div>
        <div>
          <span className="block text-zinc-500">Strike</span>
          {formatPrice(contract.strike)}
        </div>
        <div>
          <span className="block text-zinc-500">Exp</span>
          {contract.expiration}
        </div>
        <div>
          <span className="block text-zinc-500">Premium</span>
          ${formatPrice(contract.premium)}
        </div>
        <div>
          <span className="block text-zinc-500">Cost</span>
          ${formatPrice(contract.total_cost)}
        </div>
        <div>
          <span className="block text-zinc-500">Delta</span>
          {contract.delta.toFixed(3)}
        </div>
      </div>
    </Panel>
  );
}
