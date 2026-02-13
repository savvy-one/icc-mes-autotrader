"""Tests for RiskEngine."""

import time
import pytest
from icc.config import RiskConfig
from icc.core.risk import RiskEngine


@pytest.fixture
def engine():
    return RiskEngine(RiskConfig())


class TestRiskEngine:
    def test_initial_state(self, engine):
        assert engine.state.daily_pnl == 0.0
        assert engine.state.trade_count == 0
        assert not engine.state.killed

    def test_can_open_trade_initially(self, engine):
        allowed, reason = engine.can_open_trade()
        assert allowed
        assert reason == "OK"

    def test_kill_switch_on_20pct_loss(self, engine):
        engine.update_pnl(-100.0)  # 20% of $500
        assert engine.check_kill_switch()
        assert engine.state.killed

    def test_pre_kill_on_18pct_loss(self, engine):
        engine.update_pnl(-90.0)  # 18% of $500
        assert engine.check_pre_kill()
        allowed, reason = engine.can_open_trade()
        assert not allowed
        assert "Pre-kill" in reason

    def test_max_trades_blocks(self, engine):
        engine.record_trade()
        engine.record_trade()
        allowed, reason = engine.can_open_trade()
        assert not allowed
        assert "Max trades" in reason

    def test_max_open_positions_blocks(self, engine):
        engine.set_open_positions(1)
        allowed, reason = engine.can_open_trade()
        assert not allowed
        assert "Max open positions" in reason

    def test_consecutive_losses_blocks(self, engine):
        engine.update_pnl(-10.0)
        engine.update_pnl(-10.0)
        # Override cooldown by setting last_loss_time far back
        engine.state.last_loss_time = time.time() - 999
        allowed, reason = engine.can_open_trade()
        assert not allowed
        assert "consecutive losses" in reason

    def test_cooldown_blocks(self, engine):
        engine.update_pnl(-10.0)
        # Consecutive losses = 1, under max, but cooldown active
        allowed, reason = engine.can_open_trade()
        assert not allowed
        assert "Cooldown" in reason

    def test_reset_session(self, engine):
        engine.update_pnl(-50.0)
        engine.record_trade()
        engine.reset_session()
        assert engine.state.daily_pnl == 0.0
        assert engine.state.trade_count == 0

    def test_commission(self, engine):
        assert engine.compute_commission(2) == 5.0

    def test_slippage_buy(self, engine):
        price = engine.apply_slippage(100.0, "BUY")
        assert price == 100.25  # 1 tick = 0.25

    def test_slippage_sell(self, engine):
        price = engine.apply_slippage(100.0, "SELL")
        assert price == 99.75
