"use client";

import { useEffect, useRef } from "react";
import { useEventStore } from "@/stores/eventStore";

const typeColors: Record<string, string> = {
  entry: "text-green-400",
  exit: "text-orange-400",
  fsm_transition: "text-blue-400",
  kill_switch: "text-red-500",
  risk_veto: "text-yellow-400",
  session_started: "text-cyan-400",
  session_stopped: "text-zinc-400",
  alert: "text-yellow-300",
};

export function EventLog() {
  const events = useEventStore((s) => s.events);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events.length]);

  return (
    <div className="rounded-lg border border-zinc-700 bg-zinc-900 p-4">
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-zinc-400">
        Event Log
      </h3>
      <div className="h-48 overflow-y-auto font-mono text-xs">
        {events.length === 0 && (
          <p className="text-zinc-600">No events yet</p>
        )}
        {events.map((ev) => (
          <div key={ev.id} className="flex gap-2 py-0.5">
            <span className="shrink-0 text-zinc-600">
              {new Date(ev.ts * 1000).toLocaleTimeString()}
            </span>
            <span
              className={`shrink-0 ${typeColors[ev.type] ?? "text-zinc-400"}`}
            >
              [{ev.type}]
            </span>
            <span className="text-zinc-300">{ev.message}</span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
