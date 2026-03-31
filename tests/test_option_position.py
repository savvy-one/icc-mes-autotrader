"""Tests for option position PnL, premium stop, and expiration guard."""

from datetime import date, datetime

import pytest

from icc.constants import OrderSide
from icc.oms.orders import Position
from icc.oms.position_tracker import PositionTracker


# ---------------------------------------------------------------------------
# Option PnL
# ---------------------------------------------------------------------------

class TestOptionPnL:
    def test_option_pnl_profit(self):
        """Premium rises from 10.0 to 15.0 on MES option (mult=5)."""
        pos = Position(
            side=OrderSide.BUY,
            entry_price=10.0,
            entry_premium=10.0,
            multiplier=5.0,
        )
        # current premium = 15.0 → (15 - 10) * 5 * 1 = +25.0
        assert pos.unrealized_pnl(15.0) == 25.0

    def test_option_pnl_loss(self):
        """Premium drops from 10.0 to 5.0."""
        pos = Position(
            side=OrderSide.BUY,
            entry_price=10.0,
            entry_premium=10.0,
            multiplier=5.0,
        )
        # (5 - 10) * 5 * 1 = -25.0
        assert pos.unrealized_pnl(5.0) == -25.0

    def test_option_pnl_spx_multiplier(self):
        """SPX option with multiplier=100."""
        pos = Position(
            side=OrderSide.BUY,
            entry_price=8.0,
            entry_premium=8.0,
            multiplier=100.0,
        )
        # (12 - 8) * 100 * 1 = +400.0
        assert pos.unrealized_pnl(12.0) == 400.0

    def test_option_pnl_quantity(self):
        """Multiple contracts."""
        pos = Position(
            side=OrderSide.BUY,
            entry_price=10.0,
            quantity=2,
            entry_premium=10.0,
            multiplier=5.0,
        )
        # (12 - 10) * 5 * 2 = 20.0
        assert pos.unrealized_pnl(12.0) == 20.0

    def test_option_pnl_zero(self):
        """Flat — premium unchanged."""
        pos = Position(
            side=OrderSide.BUY,
            entry_price=10.0,
            entry_premium=10.0,
            multiplier=5.0,
        )
        assert pos.unrealized_pnl(10.0) == 0.0

    def test_is_option_flag(self):
        """Position.is_option returns True when entry_premium is set."""
        opt = Position(side=OrderSide.BUY, entry_price=10.0, entry_premium=10.0, multiplier=5.0)
        fut = Position(side=OrderSide.BUY, entry_price=5420.0)
        assert opt.is_option is True
        assert fut.is_option is False

    def test_futures_pnl_unchanged(self):
        """Futures PnL still uses MES_POINT_VALUE=5.0."""
        pos = Position(side=OrderSide.BUY, entry_price=5420.0)
        # Long: (5425 - 5420) * 5 * 1 = 25.0
        assert pos.unrealized_pnl(5425.0) == 25.0

    def test_futures_short_pnl_unchanged(self):
        pos = Position(side=OrderSide.SELL, entry_price=5420.0)
        # Short: (5420 - 5415) * 5 * 1 = 25.0
        assert pos.unrealized_pnl(5415.0) == 25.0


# ---------------------------------------------------------------------------
# PositionTracker with options
# ---------------------------------------------------------------------------

class TestPositionTrackerOptions:
    def test_open_option_position(self):
        pt = PositionTracker()
        pos = pt.open_position(
            side=OrderSide.BUY, entry_price=10.0,
            stop_price=5.0, target_price=20.0,
            multiplier=5.0, entry_premium=10.0,
        )
        assert pos.is_option
        assert pos.multiplier == 5.0
        assert pos.entry_premium == 10.0

    def test_close_option_position_pnl(self):
        pt = PositionTracker()
        pt.open_position(
            side=OrderSide.BUY, entry_price=10.0,
            stop_price=5.0, target_price=20.0,
            multiplier=5.0, entry_premium=10.0,
        )
        # Exit at premium 15.0, commission=3.0
        # PnL = (15 - 10) * 5 * 1 - 3.0 = 22.0
        pnl = pt.close_position(15.0, commission=3.0)
        assert pnl == 22.0
        assert pt.is_flat

    def test_close_option_position_loss(self):
        pt = PositionTracker()
        pt.open_position(
            side=OrderSide.BUY, entry_price=10.0,
            stop_price=5.0, target_price=20.0,
            multiplier=5.0, entry_premium=10.0,
        )
        # Exit at premium 4.0, commission=3.0
        # PnL = (4 - 10) * 5 - 3.0 = -33.0
        pnl = pt.close_position(4.0, commission=3.0)
        assert pnl == -33.0

    def test_futures_position_unaffected(self):
        """Regular futures positions still work as before."""
        pt = PositionTracker()
        pt.open_position(
            side=OrderSide.BUY, entry_price=5420.0,
            stop_price=5410.0, target_price=5430.0,
        )
        pos = pt.position
        assert not pos.is_option
        assert pos.multiplier is None
        pnl = pt.close_position(5425.0, commission=5.0)
        # (5425 - 5420) * 5 - 5.0 = 20.0
        assert pnl == 20.0
