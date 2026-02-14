"use client";

import type { WSReadyState } from "@/hooks/useWebSocket";

const stateConfig: Record<WSReadyState, { color: string; label: string }> = {
  connected: { color: "bg-green-400", label: "Connected" },
  connecting: { color: "bg-yellow-400", label: "Connecting" },
  disconnected: { color: "bg-red-400", label: "Disconnected" },
};

export function WSStatus({ state }: { state: WSReadyState }) {
  const { color, label } = stateConfig[state];
  return (
    <div className="flex items-center gap-1.5 text-xs text-zinc-400">
      <span className={`inline-block h-2 w-2 rounded-full ${color}`} />
      {label}
    </div>
  );
}
