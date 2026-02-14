"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { useTradingSession } from "@/hooks/useTradingSession";
import { useSessionStore } from "@/stores/sessionStore";

export function SessionControls() {
  const { running, mode } = useSessionStore();
  const { loading, error, startSimulated, startLive, stop, kill } =
    useTradingSession();
  const [paper, setPaper] = useState(true);

  return (
    <div className="flex flex-wrap items-center gap-3">
      <Button
        onClick={startSimulated}
        disabled={running || loading}
      >
        Start Simulated
      </Button>

      {/* Paper / Cash toggle + Start Live */}
      <div className="flex items-center rounded border border-zinc-700 bg-zinc-800">
        <button
          onClick={() => setPaper(true)}
          disabled={running}
          className={`px-3 py-1.5 text-sm font-medium transition-colors ${
            paper
              ? "bg-blue-600 text-white"
              : "text-zinc-400 hover:text-zinc-200"
          } rounded-l disabled:opacity-50`}
        >
          Paper
        </button>
        <button
          onClick={() => setPaper(false)}
          disabled={running}
          className={`px-3 py-1.5 text-sm font-medium transition-colors ${
            !paper
              ? "bg-red-600 text-white"
              : "text-zinc-400 hover:text-zinc-200"
          } rounded-r disabled:opacity-50`}
        >
          Cash
        </button>
      </div>
      <Button
        onClick={() => startLive(paper)}
        disabled={running || loading}
        variant={paper ? "secondary" : "danger"}
      >
        {paper ? "Start Paper" : "Start Cash"}
      </Button>

      <Button
        onClick={stop}
        disabled={!running || loading}
        variant="secondary"
      >
        Stop
      </Button>
      <Button
        onClick={kill}
        disabled={!running || loading}
        variant="danger"
      >
        KILL
      </Button>

      {running && (
        <Badge color={mode === "live" ? "red" : mode === "paper" ? "blue" : "green"}>
          {mode === "live" ? "CASH" : mode === "paper" ? "PAPER" : "SIM"}
        </Badge>
      )}
      {!running && <Badge color="zinc">STOPPED</Badge>}
      {error && (
        <span className="text-xs text-red-400">{error}</span>
      )}
    </div>
  );
}
