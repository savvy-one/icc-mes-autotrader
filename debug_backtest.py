"""Debug backtest — trace FSM transitions and strategy evaluations."""

import sys
import logging
from collections import Counter

sys.path.insert(0, "/Users/savvybusinessaccelerator/icc-mes-autotrader")

from icc.backtest.data_loader import load_candles_csv
from icc.config import load_config
from icc.constants import FSMState
from icc.core.strategy import StrategyEngine
from icc.core.fsm import ICCStateMachine
from icc.market.candle import CandleBuffer

# Load data
candles = load_candles_csv("/Users/savvybusinessaccelerator/icc-mes-autotrader/data/mes_5min_backtest.csv")
config = load_config("backtest")
print(f"Loaded {len(candles)} candles")
print(f"Strategy config: {config.strategy}")
print(f"Risk config: {config.risk}")
print()

# Manual replay to track states
fsm = ICCStateMachine()
strategy = StrategyEngine(config.strategy)
buf = CandleBuffer(maxlen=200)

state_counts = Counter()
signal_counts = Counter()
fsm_transitions = []
max_state_reached = FSMState.FLAT

state_order = {
    FSMState.FLAT: 0,
    FSMState.INDICATION_UP: 1,
    FSMState.INDICATION_DOWN: 1,
    FSMState.CORRECTION_UP: 2,
    FSMState.CORRECTION_DOWN: 2,
    FSMState.CONTINUATION_UP: 3,
    FSMState.CONTINUATION_DOWN: 3,
    FSMState.IN_TRADE_UP: 4,
    FSMState.IN_TRADE_DOWN: 4,
}

indication_count = 0
correction_count = 0
continuation_count = 0
entry_count = 0
timeout_count = 0

for i, candle in enumerate(candles):
    buf.append(candle)
    
    signal = strategy.evaluate(fsm.state, buf)
    state_counts[fsm.state.value] += 1
    
    if signal.action != "none":
        signal_counts[signal.action] += 1
        
        # Track progression
        if signal.action in ("indication_up", "indication_down"):
            indication_count += 1
            if indication_count <= 5:
                print(f"  [{i}] INDICATION: {signal.action} at {candle.timestamp} "
                      f"close={candle.close} reason='{signal.reason}'")
        elif signal.action in ("correction_up", "correction_down"):
            correction_count += 1
            if correction_count <= 5:
                print(f"  [{i}] CORRECTION: {signal.action} at {candle.timestamp} "
                      f"close={candle.close} reason='{signal.reason}'")
        elif signal.action in ("continuation_up", "continuation_down"):
            continuation_count += 1
            if continuation_count <= 5:
                print(f"  [{i}] CONTINUATION: {signal.action} at {candle.timestamp} "
                      f"close={candle.close} reason='{signal.reason}'")
        elif signal.action in ("enter_long", "enter_short"):
            entry_count += 1
            print(f"  [{i}] ENTRY: {signal.action} at {candle.timestamp} "
                  f"entry={signal.entry_price} stop={signal.stop_price} "
                  f"target={signal.target_price}")
        elif signal.action == "timeout":
            timeout_count += 1
        
        # Attempt FSM transition
        old_state = fsm.state
        if signal.action in ("enter_long", "enter_short"):
            # These are trade entries, not FSM transitions per se
            fsm.transition(signal.action)
        else:
            fsm.transition(signal.action)
        
        if old_state != fsm.state:
            fsm_transitions.append((i, old_state.value, signal.action, fsm.state.value))

print("\n" + "="*60)
print("SIGNAL COUNTS:")
for sig, count in sorted(signal_counts.items(), key=lambda x: -x[1]):
    print(f"  {sig:25s}: {count}")

print(f"\nFSM STATE TIME (bars spent in each state):")
for state, count in sorted(state_counts.items(), key=lambda x: -x[1]):
    print(f"  {state:25s}: {count} bars ({count/len(candles)*100:.1f}%)")

print(f"\nPATTERN COMPLETION FUNNEL:")
print(f"  Total candles:     {len(candles)}")
print(f"  Indications found: {indication_count}")
print(f"  Corrections found: {correction_count}")
print(f"  Continuations:     {continuation_count}")
print(f"  Entries triggered:  {entry_count}")
print(f"  Timeouts:          {timeout_count}")

print(f"\nFSM TRANSITIONS (first 20):")
for idx, old, action, new in fsm_transitions[:20]:
    print(f"  bar {idx}: {old} --[{action}]--> {new}")

# Also check: why are indications not being found?
# Let's check the raw indicator values for a few candles
print("\n" + "="*60)
print("INDICATOR DIAGNOSTICS (checking why patterns don't form):")

from icc.core.indicators import ema_slope, higher_highs, higher_lows, lower_lows, lower_highs, volume_filter

buf2 = CandleBuffer(maxlen=200)
no_ema = 0
no_hh = 0
no_hl = 0
no_ll = 0
no_lh = 0
no_vol = 0
ema_up_count = 0
ema_down_count = 0
hh_count = 0
hl_count = 0
ll_count = 0
lh_count = 0
vol_above_count = 0

for candle in candles:
    buf2.append(candle)
    if len(buf2) < 22:
        continue
    
    closes = buf2.closes()
    highs = buf2.highs()
    lows = buf2.lows()
    volumes = buf2.volumes()
    
    slope = ema_slope(closes, config.strategy.ema_period)
    if slope is None:
        no_ema += 1
        continue
    
    if slope > 0:
        ema_up_count += 1
    else:
        ema_down_count += 1
    
    hh = higher_highs(highs, count=2)
    hl = higher_lows(lows, count=2)
    ll = lower_lows(lows, count=2)
    lh = lower_highs(highs, count=2)
    vol = volume_filter(volumes, config.strategy.volume_avg_period)
    
    if hh: hh_count += 1
    if hl: hl_count += 1
    if ll: ll_count += 1
    if lh: lh_count += 1
    if vol: vol_above_count += 1

total_evaluated = len(candles) - 22
print(f"  Total bars evaluated: {total_evaluated}")
print(f"  EMA slope > 0: {ema_up_count} ({ema_up_count/total_evaluated*100:.1f}%)")
print(f"  EMA slope < 0: {ema_down_count} ({ema_down_count/total_evaluated*100:.1f}%)")
print(f"  Higher Highs (2): {hh_count} ({hh_count/total_evaluated*100:.1f}%)")
print(f"  Higher Lows (2): {hl_count} ({hl_count/total_evaluated*100:.1f}%)")
print(f"  Lower Lows (2): {ll_count} ({ll_count/total_evaluated*100:.1f}%)")
print(f"  Lower Highs (2): {lh_count} ({lh_count/total_evaluated*100:.1f}%)")
print(f"  Volume > avg: {vol_above_count} ({vol_above_count/total_evaluated*100:.1f}%)")

# Combined conditions for bullish indication
bull_indication = 0
bear_indication = 0
for candle in candles[22:]:
    buf3 = CandleBuffer(maxlen=200)
    # We need to rebuild... let's just count overlaps
    pass

# Better: simultaneous checks
buf4 = CandleBuffer(maxlen=200)
bull_all = 0
bear_all = 0
for candle in candles:
    buf4.append(candle)
    if len(buf4) < 22:
        continue
    closes = buf4.closes()
    highs = buf4.highs()
    lows = buf4.lows()
    volumes = buf4.volumes()
    slope = ema_slope(closes, config.strategy.ema_period)
    if slope is None:
        continue
    hh = higher_highs(highs, count=2)
    hl = higher_lows(lows, count=2)
    ll = lower_lows(lows, count=2)
    lh = lower_highs(highs, count=2)
    vol = volume_filter(volumes, config.strategy.volume_avg_period)
    
    if slope > 0 and hh and hl and vol:
        bull_all += 1
    if slope < 0 and ll and lh and vol:
        bear_all += 1

print(f"\n  COMBINED (all conditions simultaneously):")
print(f"  Bullish indication (slope>0 + HH + HL + vol): {bull_all}")
print(f"  Bearish indication (slope<0 + LL + LH + vol): {bear_all}")
print(f"  Total potential indications: {bull_all + bear_all}")
