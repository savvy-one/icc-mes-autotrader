/** Format a price with 2 decimal places */
export function formatPrice(price: number | null | undefined): string {
  if (price == null) return "—";
  return price.toFixed(2);
}

/** Format P&L with $ sign and color class */
export function formatPnL(pnl: number | null | undefined): {
  text: string;
  className: string;
} {
  if (pnl == null) return { text: "—", className: "text-zinc-400" };
  const sign = pnl >= 0 ? "+" : "";
  return {
    text: `${sign}$${pnl.toFixed(2)}`,
    className: pnl > 0 ? "text-green-400" : pnl < 0 ? "text-red-400" : "text-zinc-400",
  };
}

/** Format ISO date string to local time */
export function formatTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString();
}

/** Format ISO date string to local date+time */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}
