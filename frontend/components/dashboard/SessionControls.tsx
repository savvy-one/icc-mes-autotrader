"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { useTradingSession } from "@/hooks/useTradingSession";
import { useSessionStore } from "@/stores/sessionStore";
import type { InstrumentType, OptionUnderlying, StrategyName } from "@/lib/types";

const AVAILABLE_TICKERS = ["SPY", "QQQ", "NVDA", "AAPL"];

export function SessionControls() {
  const { running, mode } = useSessionStore();
  const { loading, error, startSimulated, startLive, stop, kill } =
    useTradingSession();
  const [paper, setPaper] = useState(true);
  const [instrumentType, setInstrumentType] = useState<InstrumentType>("FUTURES");
  const [underlying, setUnderlying] = useState<OptionUnderlying>("MES");
  const [strategy, setStrategy] = useState<StrategyName>("ICC");
  const [selectedTickers, setSelectedTickers] = useState<string[]>(["SPY", "QQQ", "NVDA", "AAPL"]);

  const isOptions = instrumentType === "OPTIONS";
  const isMultiTicker = isOptions && strategy === "ORB";

  // When switching instrument type, auto-select the recommended strategy
  const handleInstrumentChange = (type: InstrumentType) => {
    setInstrumentType(type);
    setStrategy(type === "OPTIONS" ? "ORB" : "ICC");
  };

  const toggleTicker = (ticker: string) => {
    setSelectedTickers((prev) =>
      prev.includes(ticker)
        ? prev.filter((t) => t !== ticker)
        : [...prev, ticker]
    );
  };

  const handleStartLive = () => {
    const tickers = isMultiTicker && selectedTickers.length > 0
      ? selectedTickers
      : undefined;
    startLive(paper, instrumentType, underlying, strategy, tickers);
  };

  return (
    <div className="space-y-3">
      {/* Row 1: Instrument type toggle + underlying selector */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Futures / Options toggle */}
        <div className="flex items-center rounded border border-zinc-700 bg-zinc-800">
          <button
            onClick={() => handleInstrumentChange("FUTURES")}
            disabled={running}
            className={`px-4 py-1.5 text-sm font-medium transition-colors ${
              !isOptions
                ? "bg-emerald-600 text-white"
                : "text-zinc-400 hover:text-zinc-200"
            } rounded-l disabled:opacity-50`}
          >
            Futures
          </button>
          <button
            onClick={() => handleInstrumentChange("OPTIONS")}
            disabled={running}
            className={`px-4 py-1.5 text-sm font-medium transition-colors ${
              isOptions
                ? "bg-purple-600 text-white"
                : "text-zinc-400 hover:text-zinc-200"
            } rounded-r disabled:opacity-50`}
          >
            Options
          </button>
        </div>

        {/* Underlying selector (only visible for options, hidden in multi-ticker ORB) */}
        {isOptions && !isMultiTicker && (
          <div className="flex items-center rounded border border-zinc-700 bg-zinc-800">
            <button
              onClick={() => setUnderlying("MES")}
              disabled={running}
              className={`px-3 py-1.5 text-sm font-medium transition-colors ${
                underlying === "MES"
                  ? "bg-purple-600 text-white"
                  : "text-zinc-400 hover:text-zinc-200"
              } rounded-l disabled:opacity-50`}
            >
              MES
            </button>
            <button
              onClick={() => setUnderlying("SPX")}
              disabled={running}
              className={`px-3 py-1.5 text-sm font-medium transition-colors ${
                underlying === "SPX"
                  ? "bg-purple-600 text-white"
                  : "text-zinc-400 hover:text-zinc-200"
              } rounded-r disabled:opacity-50`}
            >
              SPX
            </button>
          </div>
        )}

        {/* Strategy toggle: ICC / ORB */}
        <div className="flex items-center rounded border border-zinc-700 bg-zinc-800">
          <button
            onClick={() => setStrategy("ICC")}
            disabled={running}
            className={`px-3 py-1.5 text-sm font-medium transition-colors ${
              strategy === "ICC"
                ? "bg-cyan-600 text-white"
                : "text-zinc-400 hover:text-zinc-200"
            } rounded-l disabled:opacity-50`}
          >
            ICC
          </button>
          <button
            onClick={() => setStrategy("ORB")}
            disabled={running}
            className={`px-3 py-1.5 text-sm font-medium transition-colors ${
              strategy === "ORB"
                ? "bg-amber-600 text-white"
                : "text-zinc-400 hover:text-zinc-200"
            } rounded-r disabled:opacity-50`}
          >
            ORB
          </button>
        </div>

        {/* Mode badge */}
        {running && (
          <>
            <Badge color={isOptions ? "purple" : "emerald"}>
              {isOptions ? `OPTIONS (${underlying})` : "FUTURES"}
            </Badge>
            <Badge color={strategy === "ORB" ? "amber" : "cyan"}>
              {strategy}
            </Badge>
            <Badge color={mode === "live" ? "red" : mode === "paper" ? "blue" : "green"}>
              {mode === "live" ? "CASH" : mode === "paper" ? "PAPER" : "SIM"}
            </Badge>
          </>
        )}
        {!running && <Badge color="zinc">STOPPED</Badge>}
      </div>

      {/* Row 1.5: Multi-ticker selector (ORB + OPTIONS only) */}
      {isMultiTicker && !running && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-zinc-400 mr-1">Tickers:</span>
          {AVAILABLE_TICKERS.map((ticker) => (
            <button
              key={ticker}
              onClick={() => toggleTicker(ticker)}
              className={`px-3 py-1 text-xs font-mono font-bold rounded transition-colors ${
                selectedTickers.includes(ticker)
                  ? "bg-amber-600 text-white"
                  : "bg-zinc-800 text-zinc-500 border border-zinc-700 hover:text-zinc-300"
              }`}
            >
              {ticker}
            </button>
          ))}
          <span className="text-xs text-zinc-500 ml-2">
            {selectedTickers.length} selected — first breakout wins
          </span>
        </div>
      )}

      {/* Row 2: Session controls */}
      <div className="flex flex-wrap items-center gap-3">
        <Button
          onClick={() => startSimulated(instrumentType, strategy)}
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
          onClick={handleStartLive}
          disabled={running || loading || (isMultiTicker && selectedTickers.length === 0)}
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

        {error && (
          <span className="text-xs text-red-400">{error}</span>
        )}
      </div>
    </div>
  );
}
