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

/** Parse ISO string as UTC (backend stores UTC without Z suffix) */
function parseUTC(iso: string): Date {
  return new Date(iso.endsWith("Z") ? iso : iso + "Z");
}

const ET_FMT: Intl.DateTimeFormatOptions = {
  timeZone: "America/New_York",
  hour: "numeric",
  minute: "2-digit",
  second: "2-digit",
  hour12: true,
};

const ET_DATETIME_FMT: Intl.DateTimeFormatOptions = {
  timeZone: "America/New_York",
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
  hour12: true,
};

/** Format ISO date string to ET time */
export function formatTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return parseUTC(iso).toLocaleTimeString("en-US", ET_FMT);
}

/** Format ISO date string to ET date+time */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return parseUTC(iso).toLocaleString("en-US", ET_DATETIME_FMT) + " ET";
}
