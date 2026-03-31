"""Quick funnel analysis on the trending data."""
import sys
sys.path.insert(0, "/Users/savvybusinessaccelerator/icc-mes-autotrader")

from icc.backtest.data_loader import load_candles_csv
from icc.config import load_config
from icc.constants import FSMState
from icc.core.strategy import StrategyEngine
from icc.core.fsm import ICCStateMachine
from icc.market.candle import CandleBuffer
from collections import Counter

candles = load_candles_csv("/Users/savvybusinessaccelerator/icc-mes-autotrader/data/mes_5min_trending.csv")
config = load_config("backtest")

fsm = ICCStateMachine()
strategy = StrategyEngine(config.strategy)
buf = CandleBuffer(maxlen=200)

signal_counts = Counter()
state_counts = Counter()

for candle in candles:
    buf.append(candle)
    state_counts[fsm.state.value] += 1
    signal = strategy.evaluate(fsm.state, buf)
    if signal.action != "none":
        signal_counts[signal.action] += 1
        fsm.transition(signal.action)

print("SIGNAL COUNTS:")
for sig, cnt in sorted(signal_counts.items(), key=lambda x: -x[1]):
    print(f"  {sig:25s}: {cnt}")

print(f"\nSTATE TIME:")
for st, cnt in sorted(state_counts.items(), key=lambda x: -x[1]):
    print(f"  {st:25s}: {cnt} ({cnt/len(candles)*100:.1f}%)")

# The critical question: does the continuation check have a bug with the moving target?
# Let's check: for a DOWN correction, we need close < correction_low with volume
# But correction_low keeps moving DOWN as the price makes new lows...
# Wait -- that's WRONG. For a bearish continuation, the price should break BELOW
# the correction low. But the correction low keeps moving lower, so the target
# keeps moving away from the price.

# For UP: close > correction_high, but correction_high keeps moving up.
# This is a design issue: the correction extreme should be SET at entry, not updated.

print("\n\nDIAGNOSIS: The _check_continuation_up/down methods update correction_high/low")
print("on every bar. This means the breakout target keeps moving AWAY from the price.")
print("A bullish continuation needs close > correction_high, but as highs form,")
print("correction_high increases. Same for bearish: correction_low decreases.")
print("This makes completion essentially impossible with realistic data.")
