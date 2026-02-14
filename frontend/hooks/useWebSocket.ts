"use client";

import { useEffect, useRef, useCallback, useState } from "react";
import { WS_URL } from "@/lib/env";
import { useTradingStore } from "@/stores/tradingStore";
import { useSessionStore } from "@/stores/sessionStore";
import { useEventStore } from "@/stores/eventStore";
import type { Candle, FSMState, TradingSnapshot } from "@/lib/types";

const MIN_RECONNECT_MS = 1000;
const MAX_RECONNECT_MS = 30000;
const PING_INTERVAL_MS = 30000;

export type WSReadyState = "connecting" | "connected" | "disconnected";

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectDelayRef = useRef(MIN_RECONNECT_MS);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pingTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [readyState, setReadyState] = useState<WSReadyState>("disconnected");

  const { updateSnapshot, addCandle, updateFSMState, setRunning } =
    useTradingStore.getState();
  const { setRunning: setSessionRunning, setMode } =
    useSessionStore.getState();
  const addEvent = useEventStore.getState().addEvent;

  const handleMessage = useCallback(
    (raw: string) => {
      let msg: { type: string; data: Record<string, unknown>; ts?: number };
      try {
        msg = JSON.parse(raw);
      } catch {
        return;
      }

      const { type, data, ts } = msg;

      switch (type) {
        case "snapshot": {
          const snap = data as unknown as TradingSnapshot;
          updateSnapshot(snap);
          setSessionRunning(snap.running);
          if (snap.mode) setMode(snap.mode);
          break;
        }
        case "candle": {
          const candle = data as unknown as Candle;
          addCandle(candle);
          break;
        }
        case "fsm_transition": {
          const newState = (data.new_state ?? data.state) as FSMState;
          if (newState) {
            updateFSMState(newState);
            addEvent("fsm_transition", `FSM → ${newState}`, ts);
          }
          break;
        }
        case "entry": {
          addEvent(
            "entry",
            `ENTRY ${data.side} @ ${data.price}`,
            ts,
          );
          break;
        }
        case "exit": {
          addEvent(
            "exit",
            `EXIT @ ${data.price} | PnL: $${Number(data.pnl ?? 0).toFixed(2)} | ${data.reason}`,
            ts,
          );
          break;
        }
        case "kill_switch": {
          addEvent("kill_switch", "KILL SWITCH ACTIVATED", ts);
          setRunning(false);
          setSessionRunning(false);
          break;
        }
        case "risk_veto": {
          addEvent("risk_veto", `Risk veto: ${data.reason ?? "unknown"}`, ts);
          break;
        }
        case "session_started": {
          setRunning(true);
          setSessionRunning(true);
          setMode((data.mode as string) ?? "simulated");
          addEvent("session_started", "Session started", ts);
          break;
        }
        case "session_stopped": {
          setRunning(false);
          setSessionRunning(false);
          addEvent("session_stopped", "Session stopped", ts);
          break;
        }
        case "alert": {
          addEvent("alert", String(data.message ?? data.text ?? "Alert"), ts);
          break;
        }
        case "pong":
          break;
        default:
          addEvent(type, JSON.stringify(data).slice(0, 120), ts);
      }
    },
    [updateSnapshot, addCandle, updateFSMState, setRunning, setSessionRunning, setMode, addEvent],
  );

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    setReadyState("connecting");
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => {
      setReadyState("connected");
      reconnectDelayRef.current = MIN_RECONNECT_MS;
      // Start ping interval
      pingTimerRef.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send("ping");
      }, PING_INTERVAL_MS);
    };

    ws.onmessage = (ev) => handleMessage(ev.data);

    ws.onclose = () => {
      setReadyState("disconnected");
      if (pingTimerRef.current) clearInterval(pingTimerRef.current);
      // Exponential backoff reconnect
      const delay = reconnectDelayRef.current;
      reconnectTimerRef.current = setTimeout(connect, delay);
      reconnectDelayRef.current = Math.min(delay * 2, MAX_RECONNECT_MS);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [handleMessage]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      if (pingTimerRef.current) clearInterval(pingTimerRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  const requestSnapshot = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send("snapshot");
    }
  }, []);

  return { readyState, requestSnapshot };
}
