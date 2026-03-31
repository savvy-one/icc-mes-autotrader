"""Deep debug: trace exactly what happens during CORRECTION_UP/DOWN phases."""

import sys
sys.path.insert(0, "/Users/savvybusinessaccelerator/icc-mes-autotrader")

from icc.backtest.data_loader import load_candles_csv
from icc.config import load_config
from icc.constants import FSMState
from icc.core.strategy import StrategyEngine
from icc.core.fsm import ICCStateMachine
from icc.core.indicators import volume_filter
from icc.market.candle import CandleBuffer

candles = load_candles_csv("/Users/savvybusinessaccelerator/icc-mes-autotrader/data/mes_5min_backtest.csv")
config = load_config("backtest")

fsm = ICCStateMachine()
strategy = StrategyEngine(config.strategy)
buf = CandleBuffer(maxlen=200)

correction_phases = []  # list of dicts with details

in_correction = False
corr_detail = {}

for i, candle in enumerate(candles):
    buf.append(candle)
    old_state = fsm.state
    signal = strategy.evaluate(fsm.state, buf)
    
    if signal.action != "none":
        fsm.transition(signal.action)
    
    # Track correction phases in detail
    if old_state in (FSMState.INDICATION_UP, FSMState.INDICATION_DOWN):
        if fsm.state in (FSMState.CORRECTION_UP, FSMState.CORRECTION_DOWN):
            # Just entered correction
            direction = "UP" if fsm.state == FSMState.CORRECTION_UP else "DOWN"
            in_correction = True
            corr_detail = {
                "start_bar": i,
                "direction": direction,
                "timestamp": candle.timestamp,
                "impulse_high": strategy._impulse_high,
                "impulse_low": strategy._impulse_low,
                "correction_high": strategy._correction_high,
                "correction_low": strategy._correction_low,
                "candle_close": candle.close,
                "bars": [],
            }
    
    if in_correction and fsm.state in (FSMState.CORRECTION_UP, FSMState.CORRECTION_DOWN):
        volumes = buf.volumes()
        vol_ok = volume_filter(volumes, config.strategy.continuation_volume_period)
        
        direction = corr_detail["direction"]
        if direction == "UP":
            needs_break = f"close > {strategy._correction_high:.2f}"
            gap = candle.close - (strategy._correction_high if strategy._correction_high else 0)
        else:
            needs_break = f"close < {strategy._correction_low:.2f}"
            gap = (strategy._correction_low if strategy._correction_low else 0) - candle.close
        
        corr_detail["bars"].append({
            "bar": i,
            "close": candle.close,
            "high": candle.high,
            "low": candle.low,
            "volume": candle.volume,
            "vol_above_avg": vol_ok,
            "correction_high": strategy._correction_high,
            "correction_low": strategy._correction_low,
            "needs": needs_break,
            "gap_to_break": gap,
            "bar_count": strategy._correction_bar_count,
        })
    
    if in_correction and fsm.state == FSMState.FLAT:
        # Correction ended (timeout or invalidate)
        corr_detail["outcome"] = signal.action if signal.action != "none" else "timeout"
        correction_phases.append(corr_detail)
        in_correction = False

print(f"Total correction phases: {len(correction_phases)}")
print()

for idx, phase in enumerate(correction_phases):
    print(f"--- Correction Phase {idx+1}: {phase['direction']} at bar {phase['start_bar']} ({phase['timestamp']}) ---")
    print(f"  Impulse range: {phase['impulse_low']:.2f} - {phase['impulse_high']:.2f} "
          f"(range={phase['impulse_high']-phase['impulse_low']:.2f})")
    print(f"  Entry close: {phase['candle_close']:.2f}")
    print(f"  Outcome: {phase['outcome']}")
    print(f"  Bars in correction: {len(phase['bars'])}")
    
    for bar_info in phase['bars']:
        vol_marker = "V" if bar_info['vol_above_avg'] else " "
        print(f"    bar {bar_info['bar']:4d}: close={bar_info['close']:8.2f} "
              f"H={bar_info['high']:8.2f} L={bar_info['low']:8.2f} "
              f"vol={bar_info['volume']:5d} [{vol_marker}] "
              f"corr_H={bar_info['correction_high']:8.2f} corr_L={bar_info['correction_low']:8.2f} "
              f"gap={bar_info['gap_to_break']:+.2f} "
              f"cnt={bar_info['bar_count']}")
    print()
