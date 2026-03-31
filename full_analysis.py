"""Complete analysis: simulate the full backtest engine with the fixed strategy,
including position management, stop/target, risk limits, etc."""

import sys
sys.path.insert(0, "/Users/savvybusinessaccelerator/icc-mes-autotrader")

from icc.backtest.data_loader import load_candles_csv
from icc.backtest.engine import BacktestEngine
from icc.config import load_config
from icc.constants import FSMState
from icc.core.strategy import StrategyEngine
from icc.market.candle import CandleBuffer

# Monkey-patch the strategy to fix the moving target bug
original_check_continuation_up = StrategyEngine._check_continuation_up
original_check_continuation_down = StrategyEngine._check_continuation_down

def fixed_check_continuation_up(self, buf):
    if self._correction_high is None:
        from icc.core.strategy import Signal
        return Signal(action="none", reason="No correction reference")
    
    self._correction_bar_count += 1
    if self._correction_bar_count > self.config.correction_max_bars:
        from icc.core.strategy import Signal
        return Signal(action="timeout", reason="Correction exceeded max bars")
    
    candle = buf.last
    if candle is None:
        from icc.core.strategy import Signal
        return Signal(action="none")
    
    # FIX: Do NOT update correction_high/low
    # (removed the lines that update self._correction_high and self._correction_low)
    
    from icc.core.indicators import volume_filter
    volumes = buf.volumes()
    if (candle.close > self._correction_high
            and volume_filter(volumes, self.config.continuation_volume_period)):
        from icc.core.strategy import Signal
        return Signal(action="continuation_up",
                      reason="Break above correction high with volume")
    
    from icc.core.strategy import Signal
    return Signal(action="none", reason="Waiting for continuation break")

def fixed_check_continuation_down(self, buf):
    if self._correction_low is None:
        from icc.core.strategy import Signal
        return Signal(action="none", reason="No correction reference")
    
    self._correction_bar_count += 1
    if self._correction_bar_count > self.config.correction_max_bars:
        from icc.core.strategy import Signal
        return Signal(action="timeout", reason="Correction exceeded max bars")
    
    candle = buf.last
    if candle is None:
        from icc.core.strategy import Signal
        return Signal(action="none")
    
    # FIX: Do NOT update correction_low
    
    from icc.core.indicators import volume_filter
    volumes = buf.volumes()
    if (candle.close < self._correction_low
            and volume_filter(volumes, self.config.continuation_volume_period)):
        from icc.core.strategy import Signal
        return Signal(action="continuation_down",
                      reason="Break below correction low with volume")
    
    from icc.core.strategy import Signal
    return Signal(action="none", reason="Waiting for continuation break")

# Apply fixes
StrategyEngine._check_continuation_up = fixed_check_continuation_up
StrategyEngine._check_continuation_down = fixed_check_continuation_down

# Also fix: add timeout for indication state (not in original code)
original_check_correction_up = StrategyEngine._check_correction_up
original_check_correction_down = StrategyEngine._check_correction_down

# Not needed for now — let's just test with the continuation fix

data_file = "/Users/savvybusinessaccelerator/icc-mes-autotrader/data/mes_5min_backtest.csv"
candles = load_candles_csv(data_file)
config = load_config("backtest")

print(f"Running FIXED backtest on {len(candles)} candles...")
print(f"Strategy: {config.strategy}")
print(f"Risk: {config.risk}")
print()

import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

engine = BacktestEngine(config, candles)
result = engine.run()

summary = result.summary()
print("\n" + "="*60)
print("BACKTEST RESULTS (with continuation fix)")
print("="*60)
for k, v in summary.items():
    print(f"  {k:20s}: {v}")

print(f"\n  Individual trade P&Ls: {result.trades}")
print(f"  Equity curve points: {len(result.equity_curve)}")
if result.equity_curve:
    print(f"  Starting equity: {result.equity_curve[0]:.2f}")
    print(f"  Ending equity: {result.equity_curve[-1]:.2f}")
    print(f"  Min equity: {min(result.equity_curve):.2f}")
    print(f"  Max equity: {max(result.equity_curve):.2f}")
