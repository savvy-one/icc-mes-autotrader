"""RiskEngine — kill switch, limits, cooldown."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from icc.config import RiskConfig


@dataclass
class RiskState:
    daily_pnl: float = 0.0
    trade_count: int = 0
    open_positions: int = 0
    consecutive_losses: int = 0
    last_loss_time: float | None = None
    killed: bool = False
    pre_kill_triggered: bool = False
    last_large_loss_time: float | None = None


class RiskEngine:
    """Gate-style risk engine: vetoes actions, never initiates (except kill switch)."""

    def __init__(self, config: RiskConfig, settlement_tracker=None):
        self.config = config
        self.state = RiskState()
        self._kill_cap = config.account_size * config.daily_loss_kill_pct
        self._prekill_cap = config.account_size * config.daily_loss_prekill_pct
        self._settlement = settlement_tracker

    def reset_session(self) -> None:
        self.state = RiskState()

    def update_pnl(self, pnl_change: float) -> None:
        self.state.daily_pnl += pnl_change
        if pnl_change < 0:
            self.state.consecutive_losses += 1
            self.state.last_loss_time = time.time()
            if abs(pnl_change) >= self.config.large_loss_threshold:
                self.state.last_large_loss_time = time.time()
        else:
            self.state.consecutive_losses = 0

    def record_trade(self) -> None:
        self.state.trade_count += 1

    def set_open_positions(self, count: int) -> None:
        self.state.open_positions = count

    def check_kill_switch(self) -> bool:
        """Returns True if kill switch should activate."""
        if abs(self.state.daily_pnl) >= self._kill_cap and self.state.daily_pnl < 0:
            self.state.killed = True
            return True
        return False

    def check_pre_kill(self) -> bool:
        """Returns True if pre-kill warning threshold breached."""
        if abs(self.state.daily_pnl) >= self._prekill_cap and self.state.daily_pnl < 0:
            self.state.pre_kill_triggered = True
            return True
        return False

    def can_open_trade(self, trade_cost: float = 0.0) -> tuple[bool, str]:
        """Check all risk rules. Returns (allowed, reason).

        Args:
            trade_cost: Estimated cost of the trade (for settlement check).
                        Pass 0.0 to skip settlement check (backward-compatible).
        """
        if self.state.killed:
            return False, "Kill switch active"

        if self.check_kill_switch():
            return False, "Daily loss kill triggered"

        if self.check_pre_kill():
            return False, "Pre-kill threshold breached — no new entries"

        if self.state.trade_count >= self.config.max_trades_per_session:
            return False, f"Max trades ({self.config.max_trades_per_session}) reached"

        if self.state.open_positions >= self.config.max_open_positions:
            return False, f"Max open positions ({self.config.max_open_positions}) reached"

        if self.state.consecutive_losses >= self.config.max_consecutive_losses:
            return False, f"Max consecutive losses ({self.config.max_consecutive_losses}) reached"

        if self.state.last_loss_time is not None:
            elapsed = time.time() - self.state.last_loss_time
            if elapsed < self.config.cooldown_seconds:
                remaining = int(self.config.cooldown_seconds - elapsed)
                return False, f"Cooldown active ({remaining}s remaining)"

        # Large loss cooldown (longer cooldown after big losses)
        if self.state.last_large_loss_time is not None:
            elapsed = time.time() - self.state.last_large_loss_time
            if elapsed < self.config.large_loss_cooldown_seconds:
                remaining = int(self.config.large_loss_cooldown_seconds - elapsed)
                return False, f"Large loss cooldown ({remaining}s remaining)"

        # Settlement / funding tranche check
        if trade_cost > 0 and self._settlement is not None:
            allowed, reason = self._settlement.can_afford_trade(trade_cost)
            if not allowed:
                return False, reason

        return True, "OK"

    def compute_commission(self, sides: int = 2) -> float:
        return self.config.commission_per_side * sides

    def apply_slippage(self, price: float, side: str) -> float:
        from icc.constants import MES_TICK_SIZE
        slip = self.config.slippage_ticks * MES_TICK_SIZE
        if side == "BUY":
            return price + slip
        return price - slip
