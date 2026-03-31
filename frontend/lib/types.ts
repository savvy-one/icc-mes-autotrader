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
  | "RISK_BLOCKED"
  | "ORB_BUILDING"
  | "ORB_ARMED";

/** Position info from snapshot */
export interface Position {
  side: "LONG" | "SHORT" | "FLAT";
  entry_price: number | null;
  stop_price: number | null;
  target_price: number | null;
  quantity: number;
  unrealized_pnl: number;
}

/** Option contract info from snapshot */
export interface OptionContract {
  symbol: string;
  underlying: string;
  option_type: "CALL" | "PUT";
  strike: number;
  expiration: string; // ISO date
  premium: number;
  total_cost: number;
  delta: number;
  theta: number;
  implied_vol: number;
}

/** Per-ticker state in multi-ticker ORB mode */
export interface TickerState {
  fsm_state: FSMState;
  candle_count: number;
  is_flat: boolean;
  range_high: number | null;
  range_low: number | null;
  range_height: number | null;
  armed_bars: number;
  trade_taken: boolean;
  last_price?: number;
}

/** Trading snapshot from /api/session/status or WS snapshot event */
export interface TradingSnapshot {
  fsm_state: FSMState;
  strategy_name?: StrategyName;
  candle_count: number;
  daily_pnl: number;
  trade_count: number;
  position: Position | null;
  last_candle: Candle | null;
  running: boolean;
  mode?: string;
  option_contract?: OptionContract | null;
  // Multi-ticker fields
  multi_ticker?: boolean;
  tickers?: string[];
  active_ticker?: string | null;
  ticker_states?: Record<string, TickerState>;
}

/** WebSocket event from backend */
export interface TradingEvent {
  type: string;
  data: Record<string, unknown>;
  ts: number;
}

/** Strategy name for session selection */
export type StrategyName = "ICC" | "ORB";

/** Instrument type for session selection */
export type InstrumentType = "FUTURES" | "OPTIONS";

/** Option underlying for session selection */
export type OptionUnderlying = "MES" | "SPX" | "SPY" | "QQQ" | "NVDA" | "AAPL" | "AMZN" | "TSLA" | "META" | "MSFT";

/** Trade record from GET /api/trades */
export interface TradeRecord {
  id: number;
  session_id: string;
  side: string;
  entry_price: number;
  exit_price: number | null;
  stop_price: number | null;
  target_price: number | null;
  quantity: number;
  pnl: number | null;
  gross_pnl: number | null;
  commission: number;
  entry_time: string | null;
  exit_time: string | null;
  exit_reason: string | null;
  instrument_type?: string;
  option_underlying?: string | null;
  option_right?: string | null;
  option_strike?: number | null;
  option_expiration?: string | null;
  option_entry_premium?: number | null;
  option_exit_premium?: number | null;
  underlying_stop?: number | null;
  underlying_target?: number | null;
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
