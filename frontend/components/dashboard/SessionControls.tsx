"use client";

import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { useTradingSession } from "@/hooks/useTradingSession";
import { useSessionStore } from "@/stores/sessionStore";

export function SessionControls() {
  const { running, mode } = useSessionStore();
  const { loading, error, startSimulated, startLive, stop, kill } =
    useTradingSession();

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button
        onClick={startSimulated}
        disabled={running || loading}
      >
        Start Simulated
      </Button>
      <Button
        onClick={startLive}
        disabled={running || loading}
        variant="secondary"
      >
        Start Live
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
        <Badge color="green">
          {mode === "live" ? "LIVE" : "SIM"}
        </Badge>
      )}
      {!running && <Badge color="zinc">STOPPED</Badge>}
      {error && (
        <span className="text-xs text-red-400">{error}</span>
      )}
    </div>
  );
}
