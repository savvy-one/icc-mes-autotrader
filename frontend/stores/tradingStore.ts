import { create } from "zustand";
import type { Candle, FSMState, OptionContract, Position, TickerState, TradingSnapshot } from "@/lib/types";

const MAX_CANDLES = 200;

interface TradingStore {
  // State
  fsmState: FSMState;
  dailyPnl: number;
  tradeCount: number;
  candleCount: number;
  position: Position | null;
  lastCandle: Candle | null;
  candles: Candle[];
  running: boolean;
  mode: string;
  optionContract: OptionContract | null;
  // Multi-ticker
  multiTicker: boolean;
  tickers: string[];
  activeTicker: string | null;
  tickerStates: Record<string, TickerState>;

  // Actions
  updateSnapshot: (snap: TradingSnapshot) => void;
  addCandle: (candle: Candle) => void;
  updateFSMState: (state: FSMState) => void;
  setRunning: (running: boolean) => void;
  reset: () => void;
}

const initialState = {
  fsmState: "FLAT" as FSMState,
  dailyPnl: 0,
  tradeCount: 0,
  candleCount: 0,
  position: null,
  lastCandle: null,
  candles: [] as Candle[],
  running: false,
  mode: "",
  optionContract: null as OptionContract | null,
  multiTicker: false,
  tickers: [] as string[],
  activeTicker: null as string | null,
  tickerStates: {} as Record<string, TickerState>,
};

export const useTradingStore = create<TradingStore>((set) => ({
  ...initialState,

  updateSnapshot: (snap) =>
    set({
      fsmState: snap.fsm_state,
      dailyPnl: snap.daily_pnl,
      tradeCount: snap.trade_count,
      candleCount: snap.candle_count,
      position: snap.position,
      lastCandle: snap.last_candle,
      running: snap.running,
      mode: snap.mode ?? "",
      optionContract: snap.option_contract ?? null,
      multiTicker: snap.multi_ticker ?? false,
      tickers: snap.tickers ?? [],
      activeTicker: snap.active_ticker ?? null,
      tickerStates: snap.ticker_states ?? {},
    }),

  addCandle: (candle) =>
    set((state) => {
      const candles = [...state.candles, candle];
      if (candles.length > MAX_CANDLES) candles.shift();
      return { candles, lastCandle: candle, candleCount: state.candleCount + 1 };
    }),

  updateFSMState: (fsmState) => set({ fsmState }),

  setRunning: (running) => set({ running }),

  reset: () => set(initialState),
}));
