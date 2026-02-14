"use client";

import { useEffect, useState } from "react";
import { getTrades } from "@/lib/api";
import { formatPrice, formatPnL, formatDateTime } from "@/lib/formatters";
import type { TradeRecord } from "@/lib/types";

export default function TradesPage() {
  const [trades, setTrades] = useState<TradeRecord[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getTrades(50)
      .then(setTrades)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <h1 className="mb-4 text-lg font-bold">Trade History</h1>

      {loading && <p className="text-zinc-500">Loading...</p>}

      {!loading && trades.length === 0 && (
        <p className="text-zinc-500">No trades recorded yet.</p>
      )}

      {trades.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-zinc-700 text-xs text-zinc-400">
                <th className="px-3 py-2">Side</th>
                <th className="px-3 py-2">Entry</th>
                <th className="px-3 py-2">Exit</th>
                <th className="px-3 py-2">P&L</th>
                <th className="px-3 py-2">Reason</th>
                <th className="px-3 py-2">Entry Time</th>
                <th className="px-3 py-2">Exit Time</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((t) => {
                const pnl = formatPnL(t.pnl);
                return (
                  <tr
                    key={t.id}
                    className="border-b border-zinc-800 hover:bg-zinc-900"
                  >
                    <td
                      className={`px-3 py-2 font-medium ${
                        t.side === "BUY" ? "text-green-400" : "text-red-400"
                      }`}
                    >
                      {t.side}
                    </td>
                    <td className="px-3 py-2">{formatPrice(t.entry_price)}</td>
                    <td className="px-3 py-2">
                      {formatPrice(t.exit_price)}
                    </td>
                    <td className={`px-3 py-2 ${pnl.className}`}>
                      {pnl.text}
                    </td>
                    <td className="px-3 py-2 text-zinc-400">
                      {t.exit_reason ?? "—"}
                    </td>
                    <td className="px-3 py-2 text-zinc-500">
                      {formatDateTime(t.entry_time)}
                    </td>
                    <td className="px-3 py-2 text-zinc-500">
                      {formatDateTime(t.exit_time)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
