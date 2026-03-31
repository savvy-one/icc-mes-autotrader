"""Simulate what would happen if we fix the continuation check
by NOT updating correction_high/low on each bar."""

import sys
sys.path.insert(0, "/Users/savvybusinessaccelerator/icc-mes-autotrader")

from icc.backtest.data_loader import load_candles_csv
from icc.config import load_config
from icc.constants import FSMState
from icc.core.strategy import StrategyEngine, Signal
from icc.core.fsm import ICCStateMachine
from icc.core.indicators import volume_filter, atr, ema_slope, higher_highs, higher_lows, lower_lows, lower_highs, is_in_fib_zone
from icc.market.candle import CandleBuffer
from icc.constants import MES_TICK_SIZE
from collections import Counter

# Test both data files
for data_file in [
    "/Users/savvybusinessaccelerator/icc-mes-autotrader/data/mes_5min_backtest.csv",
    "/Users/savvybusinessaccelerator/icc-mes-autotrader/data/mes_5min_trending.csv",
]:
    candles = load_candles_csv(data_file)
    config = load_config("backtest")
    print(f"\n{'='*60}")
    print(f"FILE: {data_file.split('/')[-1]} ({len(candles)} candles)")
    print(f"{'='*60}")
    
    # Manually implement the strategy with the fix
    buf = CandleBuffer(maxlen=200)
    state = "FLAT"
    
    impulse_high = None
    impulse_low = None
    correction_high = None
    correction_low = None
    correction_bar_count = 0
    
    indication_count = 0
    correction_count = 0
    continuation_count = 0
    entry_count = 0
    timeout_count = 0
    
    cfg = config.strategy
    
    for i, candle in enumerate(candles):
        buf.append(candle)
        if len(buf) < max(cfg.ema_period + 2, cfg.atr_period + 2):
            continue
        
        closes = buf.closes()
        highs = buf.highs()
        lows = buf.lows()
        volumes = buf.volumes()
        
        if state == "FLAT":
            slope = ema_slope(closes, cfg.ema_period)
            if slope is None:
                continue
            
            # Check UP
            if (slope > 0 and higher_highs(highs, 2) and higher_lows(lows, 2)
                    and volume_filter(volumes, cfg.volume_avg_period)):
                impulse_high = max(highs[-3:])
                impulse_low = min(lows[-3:])
                state = "INDICATION_UP"
                indication_count += 1
                continue
            
            # Check DOWN
            if (slope < 0 and lower_lows(lows, 2) and lower_highs(highs, 2)
                    and volume_filter(volumes, cfg.volume_avg_period)):
                impulse_high = max(highs[-3:])
                impulse_low = min(lows[-3:])
                state = "INDICATION_DOWN"
                indication_count += 1
                continue
        
        elif state == "INDICATION_UP":
            if impulse_high and impulse_low:
                if is_in_fib_zone(candle.close, impulse_low, impulse_high, cfg.fib_min, cfg.fib_max):
                    # FIX: Set correction extremes ONCE and freeze them
                    correction_high = candle.high
                    correction_low = candle.low
                    correction_bar_count = 0
                    state = "CORRECTION_UP"
                    correction_count += 1
                    continue
            # Add timeout: if we've been in indication for 20 bars without correction, reset
            # (The original code has no timeout for indication state)
        
        elif state == "INDICATION_DOWN":
            if impulse_high and impulse_low:
                if is_in_fib_zone(candle.close, impulse_low, impulse_high, cfg.fib_min, cfg.fib_max):
                    correction_high = candle.high
                    correction_low = candle.low
                    correction_bar_count = 0
                    state = "CORRECTION_DOWN"
                    correction_count += 1
                    continue
        
        elif state == "CORRECTION_UP":
            correction_bar_count += 1
            if correction_bar_count > cfg.correction_max_bars:
                state = "FLAT"
                timeout_count += 1
                continue
            
            # FIX: Do NOT update correction_high/low
            # Just check for breakout
            if (candle.close > correction_high
                    and volume_filter(volumes, cfg.continuation_volume_period)):
                state = "CONTINUATION_UP"
                continuation_count += 1
                
                # Immediately build entry
                atr_vals = atr(highs, lows, closes, cfg.atr_period)
                if atr_vals:
                    current_atr = atr_vals[-1]
                    entry_price = correction_high + MES_TICK_SIZE
                    stop_price = correction_low - cfg.stop_atr_mult * current_atr
                    target_price = entry_price + cfg.target_atr_mult * current_atr
                    entry_count += 1
                    if entry_count <= 10:
                        print(f"  ENTRY #{entry_count}: bar {i}, {candle.timestamp}, "
                              f"side=LONG, entry={entry_price:.2f}, stop={stop_price:.2f}, "
                              f"target={target_price:.2f}, ATR={current_atr:.2f}")
                state = "FLAT"
                continue
        
        elif state == "CORRECTION_DOWN":
            correction_bar_count += 1
            if correction_bar_count > cfg.correction_max_bars:
                state = "FLAT"
                timeout_count += 1
                continue
            
            # FIX: Do NOT update correction_low
            if (candle.close < correction_low
                    and volume_filter(volumes, cfg.continuation_volume_period)):
                state = "CONTINUATION_DOWN"
                continuation_count += 1
                
                atr_vals = atr(highs, lows, closes, cfg.atr_period)
                if atr_vals:
                    current_atr = atr_vals[-1]
                    entry_price = correction_low - MES_TICK_SIZE
                    stop_price = correction_high + cfg.stop_atr_mult * current_atr
                    target_price = entry_price - cfg.target_atr_mult * current_atr
                    entry_count += 1
                    if entry_count <= 10:
                        print(f"  ENTRY #{entry_count}: bar {i}, {candle.timestamp}, "
                              f"side=SHORT, entry={entry_price:.2f}, stop={stop_price:.2f}, "
                              f"target={target_price:.2f}, ATR={current_atr:.2f}")
                state = "FLAT"
                continue
    
    print(f"\n  PATTERN FUNNEL:")
    print(f"    Indications:   {indication_count}")
    print(f"    Corrections:   {correction_count}")
    print(f"    Continuations: {continuation_count}")
    print(f"    Entries:       {entry_count}")
    print(f"    Timeouts:      {timeout_count}")
