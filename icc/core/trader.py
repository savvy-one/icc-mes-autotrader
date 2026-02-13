"""Trader — orchestrator wiring FSM + Risk + Strategy + OMS."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional

from icc.config import AppSettings
from icc.constants import FSMState, OrderSide, OrderType
from icc.core.fsm import ICCStateMachine
from icc.core.risk import RiskEngine
from icc.core.strategy import StrategyEngine
from icc.market.candle import Candle, CandleBuffer
from icc.oms.manager import OrderManager
from icc.oms.orders import Order
from icc.oms.position_tracker import PositionTracker

if TYPE_CHECKING:
    from icc.alerts.base import AlertRouter
    from icc.core.events import EventBus

logger = logging.getLogger(__name__)


class Trader:
    """Main orchestrator: receives candles, drives FSM + risk + strategy + OMS."""

    def __init__(
        self,
        config: AppSettings,
        order_manager: OrderManager,
        alert_router: Optional[AlertRouter] = None,
        event_bus: Optional[EventBus] = None,
    ):
        self.config = config
        self.fsm = ICCStateMachine()
        self.risk = RiskEngine(config.risk)
        self.strategy = StrategyEngine(config.strategy)
        self.oms = order_manager
        self.positions = PositionTracker()
        self.buffer = CandleBuffer(maxlen=200)
        self.alert_router = alert_router
        self.event_bus = event_bus
        self._trade_count = 0

    def _emit(self, event_type_str: str, data: dict[str, Any] | None = None) -> None:
        """Emit an event if event_bus is available."""
        if self.event_bus is None:
            return
        from icc.core.events import EventType
        try:
            et = EventType(event_type_str)
        except ValueError:
            et = EventType.ALERT
        self.event_bus.emit(et, data or {})

    def on_candle(self, candle: Candle) -> None:
        """Single integration point for the full pipeline."""
        self.buffer.append(candle)

        self._emit("candle", {
            "timestamp": candle.timestamp.isoformat(),
            "open": candle.open,
            "high": candle.high,
            "low": candle.low,
            "close": candle.close,
            "volume": candle.volume,
        })

        # Check stop/target on open positions
        if not self.positions.is_flat:
            self._check_exit(candle)
            if self.positions.is_flat:
                return

            # Increment bar counter and check timeout
            bars = self.positions.increment_bars()
            if bars >= self.config.strategy.trade_timeout_bars:
                self._exit_position(candle.close, "timeout_exit")
                return

        # Update risk engine position count
        self.risk.set_open_positions(self.positions.open_position_count)

        # Check kill switch
        if self.risk.check_kill_switch():
            self._handle_kill_switch(candle)
            return

        # Get signal from strategy
        signal = self.strategy.evaluate(self.fsm.state, self.buffer)

        if signal.action == "none":
            return

        # Attempt FSM transition
        if signal.action in ("enter_long", "enter_short"):
            self._handle_entry(signal, candle)
        elif signal.action == "timeout":
            self.fsm.transition("timeout")
            self.strategy.reset()
            self._emit("fsm_transition", {"state": self.fsm.state.value})
        else:
            self.fsm.transition(signal.action)
            self._emit("fsm_transition", {"state": self.fsm.state.value})

    def _check_exit(self, candle: Candle) -> None:
        result = self.positions.check_stop_target(candle.high, candle.low)
        if result == "stop_hit":
            pos = self.positions.position
            exit_price = pos.stop_price if pos else candle.close
            self._exit_position(exit_price, "stop_hit")
        elif result == "target_hit":
            pos = self.positions.position
            exit_price = pos.target_price if pos else candle.close
            self._exit_position(exit_price, "target_hit")

    def _handle_entry(self, signal, candle: Candle) -> None:
        # Risk gate
        allowed, reason = self.risk.can_open_trade()
        if not allowed:
            logger.info("Risk veto: %s", reason)
            self.fsm.transition("risk_block")
            self._emit("risk_veto", {"reason": reason})
            if self.alert_router:
                self.alert_router.send("risk_veto", f"Trade blocked: {reason}")
            return

        side = OrderSide.BUY if signal.action == "enter_long" else OrderSide.SELL
        order = Order(
            order_type=OrderType.STOP,
            side=side,
            price=signal.entry_price,
            quantity=1,
        )
        result = self.oms.submit(order)
        if result.filled_price is not None:
            fsm_action = "enter_long" if side == OrderSide.BUY else "enter_short"
            self.fsm.transition(fsm_action)
            self.positions.open_position(
                side=side,
                entry_price=result.filled_price,
                stop_price=signal.stop_price,
                target_price=signal.target_price,
            )
            self.risk.record_trade()
            self._trade_count += 1
            logger.info("Trade entered: %s at %.2f", side.value, result.filled_price)
            self._emit("entry", {
                "side": side.value,
                "entry_price": result.filled_price,
                "stop_price": signal.stop_price,
                "target_price": signal.target_price,
            })
        else:
            logger.warning("Order rejected, resetting FSM")
            self.fsm.transition("invalidate")

    def _exit_position(self, exit_price: float, reason: str) -> None:
        pos = self.positions.position
        entry_price = pos.entry_price if pos else 0.0
        side = pos.side.value if pos else "UNKNOWN"

        commission = self.risk.compute_commission(sides=2)
        pnl = self.positions.close_position(exit_price, commission)
        self.risk.update_pnl(pnl)
        self.fsm.transition(reason if reason in ("stop_hit", "target_hit", "timeout_exit") else "exit")
        self.fsm.transition("reset")
        self.strategy.reset()
        logger.info("Exit (%s): PnL=%.2f, daily=%.2f", reason, pnl, self.risk.state.daily_pnl)

        self._emit("exit", {
            "side": side,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "pnl": pnl,
            "reason": reason,
            "daily_pnl": self.risk.state.daily_pnl,
        })

        if self.alert_router and pnl < 0:
            self.alert_router.send("trade_loss", f"Loss: ${pnl:.2f}")

    def _handle_kill_switch(self, candle: Candle) -> None:
        logger.critical("KILL SWITCH ACTIVATED — daily PnL: %.2f", self.risk.state.daily_pnl)
        if not self.positions.is_flat:
            self._exit_position(candle.close, "kill_switch")
        self.fsm.force_state(FSMState.RISK_BLOCKED)
        self._emit("kill_switch", {"daily_pnl": self.risk.state.daily_pnl})
        if self.alert_router:
            self.alert_router.send(
                "kill_switch",
                f"Kill switch activated! Daily PnL: ${self.risk.state.daily_pnl:.2f}",
            )

    def get_snapshot(self) -> dict[str, Any]:
        """Return current trader state as a serializable dict."""
        pos = self.positions.position
        last_candle = self.buffer.last
        last_price = last_candle.close if last_candle else 0.0

        snapshot: dict[str, Any] = {
            "fsm_state": self.fsm.state.value,
            "daily_pnl": self.risk.state.daily_pnl,
            "trade_count": self._trade_count,
            "is_flat": self.positions.is_flat,
            "candle_count": len(self.buffer),
            "risk_killed": self.risk.state.killed,
        }

        if pos is not None:
            snapshot["position"] = {
                "side": pos.side.value,
                "entry_price": pos.entry_price,
                "stop_price": pos.stop_price,
                "target_price": pos.target_price,
                "bars_held": pos.bars_held,
                "unrealized_pnl": pos.unrealized_pnl(last_price),
            }
        else:
            snapshot["position"] = None

        if last_candle is not None:
            snapshot["last_candle"] = {
                "timestamp": last_candle.timestamp.isoformat(),
                "open": last_candle.open,
                "high": last_candle.high,
                "low": last_candle.low,
                "close": last_candle.close,
                "volume": last_candle.volume,
            }
        else:
            snapshot["last_candle"] = None

        return snapshot
