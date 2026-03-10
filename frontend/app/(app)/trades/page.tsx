"use client";

import { useEffect, useState } from "react";
import { getTrades } from "@/lib/api";
import { formatPrice, formatPnL, formatDateTime } from "@/lib/formatters";
import type { TradeRecord } from "@/lib/types";

interface SessionGroup {
  session_id: string;
  trades: TradeRecord[];
  total_gross: number;
  total_net: number;
  total_commission: number;
  win_count: number;
  loss_count: number;
}

function groupBySession(trades: TradeRecord[]): SessionGroup[] {
  const map = new Map<string, TradeRecord[]>();
  for (const t of trades) {
    const key = t.session_id || "unknown";
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(t);
  }

  const groups: SessionGroup[] = [];
  for (const [session_id, sessionTrades] of map) {
    // Sort trades within session by entry_time ascending
    sessionTrades.sort(
      (a, b) =>
        new Date(a.entry_time ?? 0).getTime() -
        new Date(b.entry_time ?? 0).getTime()
    );

    let total_gross = 0;
    let total_net = 0;
    let total_commission = 0;
    let win_count = 0;
    let loss_count = 0;

    for (const t of sessionTrades) {
      if (t.pnl != null) {
        total_net += t.pnl;
        total_gross += t.gross_pnl ?? t.pnl;
        total_commission += t.commission ?? 0;
        if (t.pnl > 0) win_count++;
        else if (t.pnl < 0) loss_count++;
      }
    }

    groups.push({
      session_id,
      trades: sessionTrades,
      total_gross,
      total_net,
      total_commission,
      win_count,
      loss_count,
    });
  }

  // Sort sessions by most recent first (using first trade's entry_time)
  groups.sort((a, b) => {
    const aTime = new Date(a.trades[0]?.entry_time ?? 0).getTime();
    const bTime = new Date(b.trades[0]?.entry_time ?? 0).getTime();
    return bTime - aTime;
  });

  return groups;
}

function formatSessionDate(sessionId: string): string {
  // Session IDs are like "20260304-abc12345" — extract date part
  const match = sessionId.match(/^(\d{4})(\d{2})(\d{2})/);
  if (match) {
    return `${match[1]}-${match[2]}-${match[3]}`;
  }
  return sessionId;
}

export default function TradesPage() {
  const [trades, setTrades] = useState<TradeRecord[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getTrades(200)
      .then(setTrades)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const sessions = groupBySession(trades);

  // Compute running totals across all trades chronologically (oldest first)
  const sortedTrades = [...trades].sort(
    (a, b) =>
      new Date(a.entry_time ?? 0).getTime() -
      new Date(b.entry_time ?? 0).getTime()
  );
  const runningTotalMap = new Map<number, number>();
  let cumulative = 0;
  for (const t of sortedTrades) {
    cumulative += t.pnl ?? 0;
    runningTotalMap.set(t.id, cumulative);
  }

  // Summary stats
  const totalTrades = sortedTrades.filter((t) => t.pnl != null).length;
  const totalNetPnl = sortedTrades.reduce((s, t) => s + (t.pnl ?? 0), 0);
  const totalCommission = sortedTrades.reduce(
    (s, t) => s + (t.commission ?? 0),
    0
  );
  const totalWins = sortedTrades.filter((t) => (t.pnl ?? 0) > 0).length;
  const totalLosses = sortedTrades.filter((t) => (t.pnl ?? 0) < 0).length;
  const overallWinRate =
    totalWins + totalLosses > 0
      ? Math.round((totalWins / (totalWins + totalLosses)) * 100)
      : 0;
  const summaryPnl = formatPnL(totalNetPnl);

  return (
    <div>
      <h1 className="mb-4 text-lg font-bold">Trade History</h1>

      {loading && <p className="text-zinc-500">Loading...</p>}

      {!loading && trades.length === 0 && (
        <p className="text-zinc-500">No trades recorded yet.</p>
      )}

      {!loading && trades.length > 0 && (
        <div className="mb-6 flex flex-wrap items-center gap-6 rounded-lg border border-zinc-700 bg-zinc-900 px-5 py-3">
          <div className="text-center">
            <div className="text-xs text-zinc-500">Total Net P&L</div>
            <div className={`text-lg font-bold ${summaryPnl.className}`}>
              {summaryPnl.text}
            </div>
          </div>
          <div className="text-center">
            <div className="text-xs text-zinc-500">Total Trades</div>
            <div className="text-lg font-bold text-zinc-100">
              {totalTrades}
            </div>
          </div>
          <div className="text-center">
            <div className="text-xs text-zinc-500">Win Rate</div>
            <div className="text-lg font-bold text-zinc-100">
              {overallWinRate}%
            </div>
          </div>
          <div className="text-center">
            <div className="text-xs text-zinc-500">Total Commission</div>
            <div className="text-lg font-bold text-zinc-400">
              -${totalCommission.toFixed(2)}
            </div>
          </div>
        </div>
      )}

      {sessions.map((s) => {
        const netPnl = formatPnL(s.total_net);
        const grossPnl = formatPnL(s.total_gross);
        const winRate =
          s.win_count + s.loss_count > 0
            ? Math.round(
                (s.win_count / (s.win_count + s.loss_count)) * 100
              )
            : 0;

        return (
          <div
            key={s.session_id}
            className="mb-6 rounded-lg border border-zinc-700 bg-zinc-900/50"
          >
            {/* Session Header */}
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-700 px-4 py-3">
              <div>
                <span className="text-sm font-semibold text-zinc-200">
                  {formatSessionDate(s.session_id)}
                </span>
                <span className="ml-2 text-xs text-zinc-500">
                  {s.session_id}
                </span>
              </div>
              <div className="flex gap-4 text-xs">
                <span className="text-zinc-400">
                  {s.trades.length} trade{s.trades.length !== 1 ? "s" : ""}
                </span>
                <span className="text-zinc-400">
                  {winRate}% win ({s.win_count}W / {s.loss_count}L)
                </span>
                <span className={grossPnl.className}>
                  Gross: {grossPnl.text}
                </span>
                <span className="text-zinc-500">
                  Comm: -${s.total_commission.toFixed(2)}
                </span>
                <span className={`font-semibold ${netPnl.className}`}>
                  Net: {netPnl.text}
                </span>
              </div>
            </div>

            {/* Trades Table */}
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-zinc-800 text-xs text-zinc-500">
                    <th className="px-3 py-2">#</th>
                    <th className="px-3 py-2">Side</th>
                    <th className="px-3 py-2">Entry</th>
                    <th className="px-3 py-2">Exit</th>
                    <th className="px-3 py-2">Gross P&L</th>
                    <th className="px-3 py-2">Commission</th>
                    <th className="px-3 py-2">Net P&L</th>
                    <th className="px-3 py-2">Running Total</th>
                    <th className="px-3 py-2">Reason</th>
                    <th className="px-3 py-2">Entry Time</th>
                    <th className="px-3 py-2">Exit Time</th>
                  </tr>
                </thead>
                <tbody>
                  {s.trades.map((t, idx) => {
                    const net = formatPnL(t.pnl);
                    const gross = formatPnL(t.gross_pnl);
                    const rt = formatPnL(runningTotalMap.get(t.id) ?? 0);
                    return (
                      <tr
                        key={t.id}
                        className="border-b border-zinc-800/50 hover:bg-zinc-800/30"
                      >
                        <td className="px-3 py-2 text-zinc-600">
                          {idx + 1}
                        </td>
                        <td
                          className={`px-3 py-2 font-medium ${
                            t.side === "BUY"
                              ? "text-green-400"
                              : "text-red-400"
                          }`}
                        >
                          {t.side}
                        </td>
                        <td className="px-3 py-2">
                          {formatPrice(t.entry_price)}
                        </td>
                        <td className="px-3 py-2">
                          {formatPrice(t.exit_price)}
                        </td>
                        <td className={`px-3 py-2 ${gross.className}`}>
                          {gross.text}
                        </td>
                        <td className="px-3 py-2 text-zinc-500">
                          -${(t.commission ?? 0).toFixed(2)}
                        </td>
                        <td
                          className={`px-3 py-2 font-medium ${net.className}`}
                        >
                          {net.text}
                        </td>
                        <td
                          className={`px-3 py-2 font-medium ${rt.className}`}
                        >
                          {rt.text}
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
          </div>
        );
      })}
    </div>
  );
}
