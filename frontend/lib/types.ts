/** Matches backend Candle dataclass */
export interface Candle {
  timestamp: string; // ISO string
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  symbol?: string;
}

/** FSM states matching icc/constants.py FSMState enum */
export type FSMState =
  | "FLAT"
  | "INDICATION_UP"
  | "INDICATION_DOWN"
  | "CORRECTION_UP"
  | "CORRECTION_DOWN"
  | "CONTINUATION_UP"
  | "CONTINUATION_DOWN"
  | "IN_TRADE_UP"
  | "IN_TRADE_DOWN"
  | "EXIT"
  | "RISK_BLOCKED";

/** Position info from snapshot */
export interface Position {
  side: "LONG" | "SHORT" | "FLAT";
  entry_price: number | null;
  stop_price: number | null;
  target_price: number | null;
  quantity: number;
  unrealized_pnl: number;
}

/** Trading snapshot from /api/session/status or WS snapshot event */
export interface TradingSnapshot {
  fsm_state: FSMState;
  candle_count: number;
  daily_pnl: number;
  trade_count: number;
  position: Position | null;
  last_candle: Candle | null;
  running: boolean;
  mode?: string;
}

/** WebSocket event from backend */
export interface TradingEvent {
  type: string;
  data: Record<string, unknown>;
  ts: number;
}

/** Trade record from GET /api/trades */
export interface TradeRecord {
  id: number;
  session_id: string;
  side: string;
  entry_price: number;
  exit_price: number | null;
  stop_price: number;
  target_price: number;
  quantity: number;
  pnl: number | null;
  commission: number;
  entry_time: string | null;
  exit_time: string | null;
  exit_reason: string | null;
}

/** Scheduler status from GET /api/scheduler/status */
export interface SchedulerStatus {
  enabled: boolean;
  message?: string;
  next_start?: string;
  next_stop?: string;
}

/** Session status from GET /api/session/status */
export interface SessionStatus {
  running: boolean;
  snapshot: TradingSnapshot | null;
  ws_clients: number;
}
