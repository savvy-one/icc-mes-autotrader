"""Tests for RiskEngine."""

import time
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from icc.config import RiskConfig
from icc.core.risk import RiskEngine
from icc.db.models import Base, RiskStateRecord


@pytest.fixture
def db_session():
    """In-memory SQLite session for persistence tests."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def engine():
    return RiskEngine(RiskConfig(
        account_size=500.0,
        max_trades_per_session=2,
    ))


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

    def test_scratch_loss_not_counted(self, engine):
        engine.update_pnl(-5.0)
        engine.update_pnl(-5.0)
        assert engine.state.consecutive_losses == 0

    def test_mixed_scratch_and_real_loss(self, engine):
        # Stay under the $100 daily kill threshold so consecutive-losses gate fires first
        engine.update_pnl(-30.0)
        engine.update_pnl(-3.0)   # scratch — doesn't count
        engine.update_pnl(-30.0)
        engine.state.last_loss_time = time.time() - 999
        allowed, reason = engine.can_open_trade()
        assert not allowed
        assert "consecutive losses" in reason
        assert engine.state.consecutive_losses == 2


class TestRiskEnginePersistence:
    """RiskState must survive process restarts within a trading day."""

    def _cfg(self):
        return RiskConfig(account_size=500.0, max_trades_per_session=10)

    def test_state_persists_across_restart(self, db_session):
        """A second RiskEngine on the same date hydrates from the first's writes."""
        today = "2026-05-18"
        e1 = RiskEngine(self._cfg(), db_session=db_session, today_provider=lambda: today)
        e1.update_pnl(-50.0)
        e1.record_trade()
        e1.update_pnl(-40.0)
        e1.record_trade()

        # Simulate process restart: brand new engine, same DB, same date
        e2 = RiskEngine(self._cfg(), db_session=db_session, today_provider=lambda: today)
        assert e2.state.daily_pnl == pytest.approx(-90.0)
        assert e2.state.trade_count == 2
        assert e2.state.consecutive_losses == 2

    def test_kill_switch_survives_restart(self, db_session):
        """The kill flag must persist — restarting can't bypass it."""
        today = "2026-05-18"
        e1 = RiskEngine(self._cfg(), db_session=db_session, today_provider=lambda: today)
        e1.update_pnl(-100.0)  # 20% of $500 → kill switch
        e1.check_kill_switch()
        assert e1.state.killed

        e2 = RiskEngine(self._cfg(), db_session=db_session, today_provider=lambda: today)
        assert e2.state.killed
        allowed, reason = e2.can_open_trade()
        assert not allowed
        assert "Kill switch" in reason

    def test_different_dates_isolated(self, db_session):
        """Yesterday's state must not bleed into today."""
        e1 = RiskEngine(
            self._cfg(), db_session=db_session, today_provider=lambda: "2026-05-17"
        )
        e1.update_pnl(-80.0)
        e1.record_trade()

        e2 = RiskEngine(
            self._cfg(), db_session=db_session, today_provider=lambda: "2026-05-18"
        )
        assert e2.state.daily_pnl == 0.0
        assert e2.state.trade_count == 0

    def test_reset_session_clears_persisted_state(self, db_session):
        today = "2026-05-18"
        e1 = RiskEngine(self._cfg(), db_session=db_session, today_provider=lambda: today)
        e1.update_pnl(-50.0)
        e1.record_trade()
        e1.reset_session()

        e2 = RiskEngine(self._cfg(), db_session=db_session, today_provider=lambda: today)
        assert e2.state.daily_pnl == 0.0
        assert e2.state.trade_count == 0
        assert not e2.state.killed

    def test_no_db_session_is_backward_compatible(self):
        """Without db_session, RiskEngine behaves as it always has."""
        e = RiskEngine(self._cfg())  # no db_session
        e.update_pnl(-30.0)
        e.record_trade()
        assert e.state.daily_pnl == -30.0
        assert e.state.trade_count == 1

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
