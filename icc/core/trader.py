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
from icc.core.win_tracker import WinRateTracker
from icc.oms.position_tracker import PositionTracker

if TYPE_CHECKING:
    from sqlalchemy.orm import Session as DBSession

    from icc.alerts.base import AlertRouter
    from icc.broker.option_chain import OptionChainResolver, OptionContract
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
        db_session: Optional[DBSession] = None,
        session_id: Optional[str] = None,
        settlement_tracker=None,
        research_agent=None,
        option_chain_resolver: Optional[OptionChainResolver] = None,
        shared_risk_engine: Optional[RiskEngine] = None,
    ):
        self.config = config
        self.fsm = ICCStateMachine()
        self.risk = shared_risk_engine or RiskEngine(config.risk, settlement_tracker=settlement_tracker)

        # Select strategy engine based on config
        if config.strategy_name == "ORB":
            from icc.core.orb_strategy import ORBStrategyEngine
            self.strategy = ORBStrategyEngine(config.orb)
        else:
            self.strategy = StrategyEngine(config.strategy)

        self.oms = order_manager
        self.positions = PositionTracker()
        self.buffer = CandleBuffer(maxlen=200)
        self.alert_router = alert_router
        self.event_bus = event_bus
        self._db = db_session
        self._session_id = session_id or "default"
        self._trade_count = 0
        self._open_trade_id: Optional[int] = None
        self._settlement = settlement_tracker
        self._research = research_agent
        self._option_resolver = option_chain_resolver
        self._active_contract: Optional[OptionContract] = None
        self._premium_feed = None  # Callable(contract) -> float | None, set by live strategy
        self._cached_premium: float | None = None  # Updated each candle for PnL display
        self._win_tracker = WinRateTracker()

        is_options = config.options.instrument_type == "OPTIONS"
        print(f"[ICC] Trader initialized: strategy={config.strategy_name}, "
              f"instrument={config.options.instrument_type}, "
              f"underlying={config.options.underlying}, "
              f"option_resolver={'YES' if option_chain_resolver else 'NO'}, "
              f"research={'ON' if research_agent else 'OFF'}, "
              f"settlement={'ON' if settlement_tracker else 'OFF'}",
              flush=True)

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

            # Option-specific exits: premium stop + expiration guard
            if self._active_contract is not None:
                self._check_option_exit(candle)
                if self.positions.is_flat:
                    return

            # Trailing stop management
            if self._should_trail():
                self._update_trailing(candle)

            # Increment bar counter and check timeout
            bars = self.positions.increment_bars()
            timeout = (self.config.orb.trade_timeout_bars
                       if self.config.strategy_name == "ORB"
                       else self.config.strategy.trade_timeout_bars)
            if bars >= timeout:
                self._exit_position(candle.close, "timeout_exit")
                return

        # Update risk engine position count
        self.risk.set_open_positions(self.positions.open_position_count)

        # Check kill switch (state.killed avoids re-logging every candle)
        if self.risk.state.killed:
            return
        if self.risk.check_kill_switch():
            self._handle_kill_switch(candle)
            return

        # Get signal from strategy
        signal = self.strategy.evaluate(self.fsm.state, self.buffer)

        if signal.action == "none":
            return

        print(f"[ICC] Signal: {signal.action} | FSM: {self.fsm.state.value} | price={candle.close:.2f}", flush=True)

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
            # For options: only exit on underlying target if premium is profitable.
            # Underlying target_hit doesn't guarantee premium profit (theta/IV crush).
            if pos and pos.is_option:
                premium = self._get_current_premium_safe()
                if premium is not None and pos.entry_premium is not None:
                    if premium < pos.entry_premium:
                        logger.info(
                            "Underlying target hit but premium down ($%.2f < $%.2f) — skipping exit",
                            premium, pos.entry_premium,
                        )
                        return
                    # Premium is profitable — exit with premium as price
                    self._exit_position(premium, "target_hit")
                    return
            self._exit_position(exit_price, "target_hit")

    def _get_current_premium(self, candle: Candle) -> float:
        """Get current option premium — live feed if available, else candle.close."""
        contract = self._active_contract
        if self._premium_feed is not None and contract is not None:
            try:
                live_premium = self._premium_feed(contract)
                if live_premium is not None:
                    return live_premium
            except Exception as e:
                logger.debug("Live premium feed error: %s", e)
        return candle.close

    def _get_current_premium_safe(self) -> float | None:
        """Get current option premium from live feed only (no fallback to underlying price)."""
        contract = self._active_contract
        if self._premium_feed is not None and contract is not None:
            try:
                return self._premium_feed(contract)
            except Exception as e:
                logger.debug("Live premium feed error: %s", e)
        return None

    def _check_option_exit(self, candle: Candle) -> None:
        """Check option-specific exit conditions: premium trailing, premium stop, expiration guard."""
        pos = self.positions.position
        contract = self._active_contract
        if pos is None or contract is None:
            return

        # --- Premium tracking and trailing ---
        if pos.entry_premium is not None and pos.entry_premium > 0:
            current_premium = self._get_current_premium(candle)
            self._cached_premium = current_premium  # Cache for snapshot PnL

            # Track high-water mark for premium trailing
            if not hasattr(pos, '_premium_high'):
                pos._premium_high = pos.entry_premium
            if current_premium > pos._premium_high:
                pos._premium_high = current_premium

            # Premium trailing: if premium went up 20%+ then drops 15% from peak, exit
            if pos._premium_high > pos.entry_premium * 1.20:
                drop_from_peak = (pos._premium_high - current_premium) / pos._premium_high
                if drop_from_peak >= 0.15:
                    logger.info(
                        "Premium trail stop: peaked at $%.2f, now $%.2f (%.1f%% drop from peak)",
                        pos._premium_high, current_premium, drop_from_peak * 100,
                    )
                    self._exit_position(current_premium, "premium_trail_stop")
                    return

            # Premium stop: exit if premium drops by premium_stop_pct from entry
            stop_pct = self.config.options.premium_stop_pct
            pnl_pct = (current_premium - pos.entry_premium) / pos.entry_premium
            if pnl_pct <= -stop_pct:
                logger.info(
                    "Premium stop: dropped %.1f%% (threshold %.1f%%)",
                    abs(pnl_pct) * 100, stop_pct * 100,
                )
                self._exit_position(current_premium, "premium_stop")
                return

        # --- Expiration guard: exit N minutes before expiry ---
        guard_min = self.config.options.expiration_guard_minutes
        exp = contract.expiration
        ts = candle.timestamp
        if ts.date() == exp:
            close_minutes = 16 * 60  # 4:00 PM
            now_minutes = ts.hour * 60 + ts.minute
            if (close_minutes - now_minutes) <= guard_min:
                logger.info(
                    "Expiration guard: %d min to close (guard=%d)",
                    close_minutes - now_minutes, guard_min,
                )
                current_premium = self._get_current_premium(candle)
                self._exit_position(current_premium, "expiration_guard")
                return

    def _estimate_trade_cost(self, signal, contract=None) -> float:
        """Estimate cost of a trade for settlement checking.

        Futures: commission only (~$5 round trip).
        Options: premium * multiplier * qty + commission.
        """
        commission = self.risk.compute_commission(sides=2)
        if self.config.options.instrument_type == "OPTIONS":
            option_commission = self.config.options.option_commission_per_side * 2
            if contract is not None:
                return contract.total_cost + option_commission
            return commission + option_commission
        return commission

    def _resolve_option_contract(self, signal, candle: Candle):
        """Resolve option contract if instrument_type is OPTIONS.

        Returns (contract, trade_cost) or (None, commission_cost).
        """
        if (
            self.config.options.instrument_type != "OPTIONS"
            or self._option_resolver is None
        ):
            return None, self._estimate_trade_cost(signal)

        direction = "long" if signal.action == "enter_long" else "short"
        contract = self._option_resolver.resolve(direction, candle.close)
        if contract is None:
            return None, 0.0  # signals caller to abort
        trade_cost = self._estimate_trade_cost(signal, contract=contract)
        return contract, trade_cost

    def _handle_entry(self, signal, candle: Candle) -> None:
        # Research gate (before risk — returns to FLAT, not RISK_BLOCKED)
        if self._research is not None:
            direction = "long" if signal.action == "enter_long" else "short"
            allowed, reason, confidence = self._research.assess_entry(
                self.buffer, direction,
                win_rate_adj=self._win_tracker.confidence_adjustment,
            )
            if not allowed:
                print(f"[ICC] Research VETO: {reason} (confidence={confidence:.2f})", flush=True)
                logger.info("Research veto: %s", reason)
                self.fsm.transition("invalidate")
                self._emit("research_veto", {
                    "reason": reason,
                    "confidence": confidence,
                })
                if self.alert_router:
                    self.alert_router.send("research_veto", f"Entry vetoed: {reason}")
                return

        # Resolve option contract (if OPTIONS mode) and compute trade cost
        contract, trade_cost = self._resolve_option_contract(signal, candle)
        if self.config.options.instrument_type == "OPTIONS" and contract is None:
            print("[ICC] Option resolve FAILED — no suitable contract (will retry)", flush=True)
            logger.info("Option resolve failed — no suitable contract")
            # Don't transition FSM — stay in ORB_ARMED to retry next candle
            return
        if contract is not None:
            print(f"[ICC] Option resolved: {contract.underlying} {contract.strike} {contract.option_type} exp={contract.expiration} premium=${contract.premium:.2f}", flush=True)

        # Risk gate (includes settlement check if trade_cost > 0)
        allowed, reason = self.risk.can_open_trade(trade_cost=trade_cost)
        if not allowed:
            print(f"[ICC] Risk VETO: {reason} (will retry)", flush=True)
            logger.info("Risk veto: %s", reason)
            # For ORB, don't go to RISK_BLOCKED — stay armed to retry
            if self.config.strategy_name != "ORB":
                self.fsm.transition("risk_block")
            self._emit("risk_veto", {"reason": reason})
            if self.alert_router:
                self.alert_router.send("risk_veto", f"Trade blocked: {reason}")
            return

        # For options, buy calls (long) or puts (short) — always BUY side
        if contract is not None:
            side = OrderSide.BUY
            order = Order(
                order_type=OrderType.MARKET,
                side=side,
                price=contract.premium,
                quantity=self.config.options.quantity,
                asset_info={
                    "asset_type": "OPTION",
                    "underlying": contract.underlying,
                    "option_type": contract.option_type,
                    "strike": contract.strike,
                    "expiration": contract.expiration.isoformat(),
                    "premium": contract.premium,
                    "multiplier": contract.multiplier,
                },
            )
        else:
            side = OrderSide.BUY if signal.action == "enter_long" else OrderSide.SELL
            order = Order(
                order_type=OrderType.STOP,
                side=side,
                price=signal.entry_price,
                quantity=1,
            )

        result = self.oms.submit(order)
        if result.filled_price is not None:
            fsm_action = "enter_long" if signal.action == "enter_long" else "enter_short"
            self.fsm.transition(fsm_action)

            # For options, entry_price is the premium paid
            entry_price = result.filled_price
            open_kwargs: dict[str, Any] = dict(
                side=OrderSide.BUY if signal.action == "enter_long" else OrderSide.SELL,
                entry_price=entry_price,
                stop_price=signal.stop_price,
                target_price=signal.target_price,
            )
            if contract is not None:
                open_kwargs["multiplier"] = contract.multiplier
                open_kwargs["entry_premium"] = result.filled_price
            self.positions.open_position(**open_kwargs)
            self.risk.record_trade()
            self._trade_count += 1
            self._active_contract = contract

            # Mark ORB trade as taken (only after fill, not on signal)
            from icc.core.orb_strategy import ORBStrategyEngine
            if isinstance(self.strategy, ORBStrategyEngine):
                self.strategy.mark_trade_taken()

            # Record purchase in settlement tracker
            if self._settlement is not None:
                self._settlement.record_purchase(trade_cost)

            entry_label = "enter_long" if signal.action == "enter_long" else "enter_short"
            contract_label = f" ({contract.symbol})" if contract else ""
            print(f"[ICC] ENTRY: {entry_label} at {entry_price:.2f}{contract_label}", flush=True)
            logger.info("Trade entered: %s at %.2f%s", entry_label, entry_price, contract_label)
            entry_data: dict[str, Any] = {
                "side": side.value,
                "entry_price": entry_price,
                "stop_price": signal.stop_price,
                "target_price": signal.target_price,
            }
            if contract is not None:
                entry_data["option"] = {
                    "symbol": contract.symbol,
                    "strike": contract.strike,
                    "expiration": contract.expiration.isoformat(),
                    "premium": contract.premium,
                    "total_cost": contract.total_cost,
                    "delta": contract.delta,
                }
            self._emit("entry", entry_data)

            # Persist to DB
            if self._db is not None:
                try:
                    from icc.db.repo import create_trade
                    trade_kwargs: dict[str, Any] = {
                        "session_id": self._session_id,
                        "side": side.value,
                        "entry_price": entry_price,
                        "stop_price": signal.stop_price or 0.0,
                        "target_price": signal.target_price or 0.0,
                        "instrument_type": self.config.options.instrument_type,
                    }
                    if contract is not None:
                        trade_kwargs.update({
                            "option_underlying": contract.underlying,
                            "option_right": contract.option_type,
                            "option_strike": contract.strike,
                            "option_expiration": contract.expiration.isoformat(),
                            "option_entry_premium": contract.premium,
                            "option_multiplier": contract.multiplier,
                        })
                    rec = create_trade(self._db, **trade_kwargs)
                    self._open_trade_id = rec.id
                except Exception as e:
                    logger.error("Failed to persist trade entry: %s", e)
        else:
            logger.warning("Order rejected, resetting FSM")
            self.fsm.transition("invalidate")

    def _exit_position(self, exit_price: float, reason: str) -> None:
        pos = self.positions.position
        entry_price = pos.entry_price if pos else 0.0
        side = pos.side.value if pos else "UNKNOWN"
        was_option = pos.is_option if pos else False

        # For options, exit_price must be the option premium, not the underlying price.
        # Callers like _check_exit pass the underlying stop/target price — override here.
        if was_option and reason not in ("premium_stop", "premium_trail_stop", "expiration_guard"):
            # These two reasons already pass the premium; all others need conversion.
            live_premium = self._get_current_premium_safe()
            if live_premium is not None:
                exit_price = live_premium
            else:
                # No live premium available — use entry premium as fallback (flat exit)
                exit_price = pos.entry_premium if pos and pos.entry_premium else 0.0
                logger.warning(
                    "No live premium for option exit (%s), using entry premium %.2f",
                    reason, exit_price,
                )

        # For options, use option commission instead of futures commission
        if was_option:
            commission = self.config.options.option_commission_per_side * 2
        else:
            commission = self.risk.compute_commission(sides=2)

        pnl = self.positions.close_position(exit_price, commission)
        self._win_tracker.record(pnl)
        self.risk.update_pnl(pnl)

        valid_fsm_exits = ("stop_hit", "target_hit", "timeout_exit")
        fsm_reason = reason if reason in valid_fsm_exits else "exit"
        # Treat premium_trail_stop as a premium exit in option handler

        self.fsm.transition(fsm_reason)
        self.fsm.transition("reset")
        self.strategy.reset()
        print(f"[ICC] EXIT ({reason}): PnL=${pnl:.2f}, daily=${self.risk.state.daily_pnl:.2f}", flush=True)
        logger.info("Exit (%s): PnL=%.2f, daily=%.2f", reason, pnl, self.risk.state.daily_pnl)

        # Record sale in settlement tracker
        if self._settlement is not None:
            trade_id = str(self._open_trade_id or self._trade_count)
            if was_option:
                # Option proceeds = exit premium * multiplier * qty
                contract = self._active_contract
                mult = contract.multiplier if contract else 5.0
                proceeds = max(0.0, exit_price * mult)
                # Cash-settled underlyings (e.g. SPX) — no T+1 delay
                underlying = contract.underlying if contract else self.config.options.underlying
                if underlying in self.config.options.cash_settled_underlyings:
                    self._settlement.record_immediate_settlement(proceeds, trade_id)
                else:
                    self._settlement.record_sale(proceeds, trade_id)
            else:
                proceeds = max(0.0, pnl + self.risk.compute_commission(sides=2))
                self._settlement.record_sale(proceeds, trade_id)

        exit_data: dict[str, Any] = {
            "side": side,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "pnl": pnl,
            "reason": reason,
            "daily_pnl": self.risk.state.daily_pnl,
        }
        if self._active_contract is not None:
            exit_data["option"] = {"symbol": self._active_contract.symbol}
        self._emit("exit", exit_data)

        # Capture exit premium before clearing contract
        option_exit_premium = exit_price if was_option else None

        # Clear option contract and cached premium on exit
        self._active_contract = None
        self._cached_premium = None
        # Persist exit to DB
        if self._db is not None and self._open_trade_id is not None:
            try:
                from icc.db.repo import close_trade
                close_trade(self._db, self._open_trade_id, exit_price, pnl, reason,
                            option_exit_premium=option_exit_premium)
                self._open_trade_id = None
            except Exception as e:
                logger.error("Failed to persist trade exit: %s", e)

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

    def _should_trail(self) -> bool:
        if self.config.strategy_name == "ORB":
            return self.config.orb.trailing_stop_enabled
        return self.config.strategy.trailing_stop_enabled

    def _update_trailing(self, candle: Candle) -> None:
        if self.config.strategy_name == "ORB":
            from icc.core.orb_strategy import ORBStrategyEngine
            if isinstance(self.strategy, ORBStrategyEngine):
                rh = self.strategy.range_height or 0.0
                self.positions.update_trailing_stop(
                    candle.close, rh,
                    self.config.orb.breakeven_range_pct,
                    self.config.orb.trail_range_pct,
                )
        else:
            closes = self.buffer.closes()
            highs = self.buffer.highs()
            lows = self.buffer.lows()
            from icc.core.indicators import atr as calc_atr
            atr_vals = calc_atr(highs, lows, closes, self.config.strategy.atr_period)
            if atr_vals:
                self.positions.update_trailing_stop(
                    candle.close, atr_vals[-1],
                    self.config.strategy.breakeven_atr_mult,
                    self.config.strategy.trail_atr_mult,
                )

    def get_snapshot(self) -> dict[str, Any]:
        """Return current trader state as a serializable dict."""
        pos = self.positions.position
        last_candle = self.buffer.last
        last_price = last_candle.close if last_candle else 0.0

        snapshot: dict[str, Any] = {
            "fsm_state": self.fsm.state.value,
            "strategy_name": self.config.strategy_name,
            "daily_pnl": self.risk.state.daily_pnl,
            "trade_count": self._trade_count,
            "is_flat": self.positions.is_flat,
            "candle_count": len(self.buffer),
            "risk_killed": self.risk.state.killed,
        }

        if pos is not None:
            # For options, use cached premium for PnL (not underlying price)
            pnl_price = last_price
            if pos.is_option and self._cached_premium is not None:
                pnl_price = self._cached_premium

            snapshot["position"] = {
                "side": pos.side.value,
                "entry_price": pos.entry_price,
                "stop_price": pos.stop_price,
                "target_price": pos.target_price,
                "bars_held": pos.bars_held,
                "unrealized_pnl": pos.unrealized_pnl(pnl_price),
                "original_stop_price": pos.original_stop_price,
                "breakeven_triggered": pos.breakeven_triggered,
                "trailing_active": pos.trailing_active,
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

        # Settlement snapshot
        if self._settlement is not None:
            snapshot["settlement"] = self._settlement.get_snapshot()

        # Research snapshot
        if self._research is not None:
            snapshot["research"] = self._research.get_snapshot()

        # Win rate snapshot
        snapshot["win_rate"] = self._win_tracker.get_snapshot()

        # Option contract snapshot
        if self._active_contract is not None:
            c = self._active_contract
            snapshot["option_contract"] = {
                "symbol": c.symbol,
                "underlying": c.underlying,
                "option_type": c.option_type,
                "strike": c.strike,
                "expiration": c.expiration.isoformat(),
                "premium": c.premium,
                "total_cost": c.total_cost,
                "delta": c.delta,
                "theta": c.theta,
                "implied_vol": c.implied_vol,
            }
        elif self._option_resolver is not None:
            snapshot["option_contract"] = None

        return snapshot
