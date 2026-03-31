"""Full backtest with fixed continuation AND session-aware risk reset."""

import sys
sys.path.insert(0, "/Users/savvybusinessaccelerator/icc-mes-autotrader")

from icc.backtest.data_loader import load_candles_csv
from icc.config import load_config
from icc.constants import FSMState, MES_TICK_SIZE
from icc.core.strategy import StrategyEngine, Signal
from icc.core.indicators import volume_filter, atr
from icc.core.fsm import ICCStateMachine
from icc.core.risk import RiskEngine
from icc.market.candle import CandleBuffer
from icc.oms.position_tracker import PositionTracker
from icc.broker.backtest import BacktestBrokerAdapter
from icc.oms.manager import OrderManager
from icc.oms.orders import Order
from icc.constants import OrderSide, OrderType

# Monkey-patch continuation fix
def fixed_check_continuation_up(self, buf):
    if self._correction_high is None:
        return Signal(action="none", reason="No correction reference")
    self._correction_bar_count += 1
    if self._correction_bar_count > self.config.correction_max_bars:
        return Signal(action="timeout", reason="Correction exceeded max bars")
    candle = buf.last
    if candle is None:
        return Signal(action="none")
    # NO update to correction_high/low
    volumes = buf.volumes()
    if (candle.close > self._correction_high
            and volume_filter(volumes, self.config.continuation_volume_period)):
        return Signal(action="continuation_up", reason="Break above correction high with volume")
    return Signal(action="none", reason="Waiting for continuation break")

def fixed_check_continuation_down(self, buf):
    if self._correction_low is None:
        return Signal(action="none", reason="No correction reference")
    self._correction_bar_count += 1
    if self._correction_bar_count > self.config.correction_max_bars:
        return Signal(action="timeout", reason="Correction exceeded max bars")
    candle = buf.last
    if candle is None:
        return Signal(action="none")
    # NO update to correction_low
    volumes = buf.volumes()
    if (candle.close < self._correction_low
            and volume_filter(volumes, self.config.continuation_volume_period)):
        return Signal(action="continuation_down", reason="Break below correction low with volume")
    return Signal(action="none", reason="Waiting for continuation break")

StrategyEngine._check_continuation_up = fixed_check_continuation_up
StrategyEngine._check_continuation_down = fixed_check_continuation_down

# Load data
data_file = "/Users/savvybusinessaccelerator/icc-mes-autotrader/data/mes_5min_backtest.csv"
candles = load_candles_csv(data_file)
config = load_config("backtest")

# Manual replay with session-aware risk reset
broker = BacktestBrokerAdapter(
    slippage_ticks=config.risk.slippage_ticks,
    commission_per_side=config.risk.commission_per_side,
)
broker.connect()
oms = OrderManager(broker)

fsm = ICCStateMachine()
risk = RiskEngine(config.risk)
strategy = StrategyEngine(config.strategy)
buf = CandleBuffer(maxlen=200)
positions = PositionTracker()

trade_count = 0
equity = config.risk.account_size
equity_curve = [equity]
trade_log = []
current_session_date = None

for i, candle in enumerate(candles):
    buf.append(candle)
    
    # Session reset: when the date changes, reset risk engine
    candle_date = candle.timestamp.date()
    if current_session_date is not None and candle_date != current_session_date:
        risk.reset_session()
    current_session_date = candle_date
    
    # Check stop/target on open positions
    if not positions.is_flat:
        result = positions.check_stop_target(candle.high, candle.low)
        if result == "stop_hit":
            pos = positions.position
            exit_price = pos.stop_price if pos else candle.close
            commission = risk.compute_commission(sides=2)
            pnl = positions.close_position(exit_price, commission)
            risk.update_pnl(pnl)
            trade_log.append({
                "bar": i, "timestamp": candle.timestamp, 
                "exit_price": exit_price, "pnl": pnl, "reason": "stop_hit"
            })
            fsm.transition("stop_hit")
            fsm.transition("reset")
            strategy.reset()
            equity += pnl
            equity_curve.append(equity)
            continue
        elif result == "target_hit":
            pos = positions.position
            exit_price = pos.target_price if pos else candle.close
            commission = risk.compute_commission(sides=2)
            pnl = positions.close_position(exit_price, commission)
            risk.update_pnl(pnl)
            trade_log.append({
                "bar": i, "timestamp": candle.timestamp,
                "exit_price": exit_price, "pnl": pnl, "reason": "target_hit"
            })
            fsm.transition("target_hit")
            fsm.transition("reset")
            strategy.reset()
            equity += pnl
            equity_curve.append(equity)
            continue
        
        # Timeout check
        bars = positions.increment_bars()
        if bars >= config.strategy.trade_timeout_bars:
            commission = risk.compute_commission(sides=2)
            pnl = positions.close_position(candle.close, commission)
            risk.update_pnl(pnl)
            trade_log.append({
                "bar": i, "timestamp": candle.timestamp,
                "exit_price": candle.close, "pnl": pnl, "reason": "timeout"
            })
            fsm.transition("timeout_exit")
            fsm.transition("reset")
            strategy.reset()
            equity += pnl
            equity_curve.append(equity)
            continue
    
    # Risk check
    risk.set_open_positions(positions.open_position_count)
    if risk.check_kill_switch():
        if not positions.is_flat:
            commission = risk.compute_commission(sides=2)
            pnl = positions.close_position(candle.close, commission)
            equity += pnl
        fsm.force_state(FSMState.RISK_BLOCKED)
        continue
    
    # Strategy evaluation
    signal = strategy.evaluate(fsm.state, buf)
    
    if signal.action == "none":
        unrealized = positions.unrealized_pnl(candle.close)
        equity_curve.append(equity + unrealized)
        continue
    
    if signal.action in ("enter_long", "enter_short"):
        allowed, reason = risk.can_open_trade()
        if not allowed:
            fsm.transition("risk_block")
            equity_curve.append(equity)
            continue
        
        side = OrderSide.BUY if signal.action == "enter_long" else OrderSide.SELL
        order = Order(order_type=OrderType.STOP, side=side,
                      price=signal.entry_price, quantity=1)
        fill = oms.submit(order)
        if fill.filled_price is not None:
            fsm.transition(signal.action)
            positions.open_position(
                side=side, entry_price=fill.filled_price,
                stop_price=signal.stop_price, target_price=signal.target_price,
            )
            risk.record_trade()
            trade_count += 1
            trade_log.append({
                "bar": i, "timestamp": candle.timestamp,
                "side": side.value, "entry_price": fill.filled_price,
                "stop": signal.stop_price, "target": signal.target_price,
                "pnl": None, "reason": "entry"
            })
    elif signal.action == "timeout":
        fsm.transition("timeout")
        strategy.reset()
    else:
        fsm.transition(signal.action)
    
    unrealized = positions.unrealized_pnl(candle.close)
    equity_curve.append(equity + unrealized)

# Results
print("="*70)
print("BACKTEST RESULTS (Fixed Continuation + Session-Aware Risk Reset)")
print("="*70)

trade_pnls = [t["pnl"] for t in trade_log if t["pnl"] is not None]
wins = [p for p in trade_pnls if p > 0]
losses = [p for p in trade_pnls if p <= 0]

print(f"\n  Total candles:    {len(candles)}")
print(f"  Sessions:         60")
print(f"  Trade count:      {len(trade_pnls)}")
print(f"  Win count:        {len(wins)}")
print(f"  Loss count:       {len(losses)}")
print(f"  Win rate:         {len(wins)/len(trade_pnls)*100:.1f}%" if trade_pnls else "  Win rate:         N/A")
print(f"  Total PnL:        ${sum(trade_pnls):.2f}")
print(f"  Avg Win:          ${sum(wins)/len(wins):.2f}" if wins else "  Avg Win:          N/A")
print(f"  Avg Loss:         ${sum(losses)/len(losses):.2f}" if losses else "  Avg Loss:         N/A")

gross_profit = sum(w for w in wins)
gross_loss = abs(sum(l for l in losses))
pf = gross_profit / gross_loss if gross_loss > 0 else float('inf')
print(f"  Profit Factor:    {pf:.2f}")

if equity_curve:
    peak = equity_curve[0]
    max_dd = 0
    for eq in equity_curve:
        if eq > peak:
            peak = eq
        dd = peak - eq
        if dd > max_dd:
            max_dd = dd
    print(f"  Max Drawdown:     ${max_dd:.2f}")
    print(f"  Starting Equity:  ${equity_curve[0]:.2f}")
    print(f"  Ending Equity:    ${equity_curve[-1]:.2f}")

print(f"\n  TRADE LOG:")
entries_pending = {}
for t in trade_log:
    if t["reason"] == "entry":
        print(f"    [{t['timestamp']}] ENTRY {t['side']} at {t['entry_price']:.2f} "
              f"(stop={t['stop']:.2f}, target={t['target']:.2f})")
    else:
        pnl = t['pnl']
        marker = "WIN" if pnl > 0 else "LOSS"
        print(f"    [{t['timestamp']}] EXIT ({t['reason']}) at {t['exit_price']:.2f} -> "
              f"PnL=${pnl:.2f} [{marker}]")

# ICC Pattern completion analysis
print(f"\n  ICC PATTERN FUNNEL (what the strategy SAW, ignoring risk limits):")
# Re-run without risk to count raw patterns
fsm2 = ICCStateMachine()
strategy2 = StrategyEngine(config.strategy)
strategy2._check_continuation_up = lambda self=strategy2, buf=None: fixed_check_continuation_up(strategy2, buf)
buf2 = CandleBuffer(maxlen=200)
from collections import Counter
sig_counts = Counter()
for candle in candles:
    buf2.append(candle)
    sig = strategy2.evaluate(fsm2.state, buf2)
    if sig.action != "none":
        sig_counts[sig.action] += 1
        if sig.action in ("enter_long", "enter_short"):
            fsm2.transition(sig.action)
            # Auto-exit after transition to keep going
            fsm2.transition("target_hit")
            fsm2.transition("reset")
            strategy2.reset()
        else:
            fsm2.transition(sig.action)

for sig, cnt in sorted(sig_counts.items(), key=lambda x: -x[1]):
    print(f"    {sig:30s}: {cnt}")
