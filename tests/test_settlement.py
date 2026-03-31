"""Tests for settlement tracking and staggered funding."""

from datetime import date, datetime, time
import pytest
import pytz

from icc.core.settlement import (
    FundingSchedule,
    FundingTranche,
    PendingSettlement,
    SettlementTracker,
    is_business_day,
    next_business_day,
    settlement_date_for_trade,
)
from icc.broker.cash_provider import MockCashProvider

_ET = pytz.timezone("US/Eastern")


def _et(year, month, day, hour, minute=0):
    """Create an ET-aware datetime for testing."""
    return _ET.localize(datetime(year, month, day, hour, minute))


# --- Settlement Calendar ---

class TestSettlementCalendar:
    def test_weekday_is_business_day(self):
        # 2026-03-09 is Monday
        assert is_business_day(date(2026, 3, 9))

    def test_weekend_not_business_day(self):
        # 2026-03-14 is Saturday
        assert not is_business_day(date(2026, 3, 14))
        # 2026-03-15 is Sunday
        assert not is_business_day(date(2026, 3, 15))

    def test_holiday_not_business_day(self):
        # 2026-12-25 is Christmas
        assert not is_business_day(date(2026, 12, 25))

    def test_next_business_day_weekday(self):
        # Monday -> Tuesday
        assert next_business_day(date(2026, 3, 9)) == date(2026, 3, 10)

    def test_next_business_day_friday_to_monday(self):
        # Friday -> Monday
        assert next_business_day(date(2026, 3, 13)) == date(2026, 3, 16)

    def test_next_business_day_skips_holiday(self):
        # Day before Christmas (Thursday 12/24) -> Monday 12/28
        # 2026-12-25 is Friday (Christmas), skip to Monday 12/28
        assert next_business_day(date(2026, 12, 24)) == date(2026, 12, 28)

    def test_settlement_date_t_plus_1(self):
        # Monday trade -> settles Tuesday
        assert settlement_date_for_trade(date(2026, 3, 9)) == date(2026, 3, 10)

    def test_settlement_date_friday_trade(self):
        # Friday trade -> settles Monday
        assert settlement_date_for_trade(date(2026, 3, 13)) == date(2026, 3, 16)


# --- Funding Tranche ---

class TestFundingTranche:
    def test_initial_remaining(self):
        t = FundingTranche(name="morning", start_hour=9, start_minute=30, budget=250.0)
        assert t.remaining == 250.0
        assert t.trade_count == 0

    def test_can_afford_within_budget(self):
        t = FundingTranche(name="morning", start_hour=9, start_minute=30, budget=250.0)
        allowed, reason = t.can_afford(50.0, safety_buffer=10.0)
        assert allowed
        assert reason == "OK"

    def test_cannot_afford_exceeds_budget(self):
        t = FundingTranche(name="morning", start_hour=9, start_minute=30, budget=250.0)
        t.spent = 230.0
        allowed, reason = t.can_afford(50.0, safety_buffer=10.0)
        assert not allowed
        assert "insufficient" in reason.lower()

    def test_record_purchase(self):
        t = FundingTranche(name="morning", start_hour=9, start_minute=30, budget=250.0)
        t.record_purchase(50.0)
        assert t.spent == 50.0
        assert t.remaining == 200.0
        assert t.trade_count == 1


# --- Funding Schedule ---

class TestFundingSchedule:
    def test_morning_tranche_active(self):
        schedule = FundingSchedule([
            {"name": "morning", "start_hour": 9, "start_minute": 30, "budget": 250.0},
            {"name": "afternoon", "start_hour": 14, "start_minute": 0, "budget": 250.0},
        ])
        now = _et(2026, 3, 10, 10, 0)
        tranche = schedule.get_active_tranche(now)
        assert tranche is not None
        assert tranche.name == "morning"

    def test_afternoon_tranche_active(self):
        schedule = FundingSchedule([
            {"name": "morning", "start_hour": 9, "start_minute": 30, "budget": 250.0},
            {"name": "afternoon", "start_hour": 14, "start_minute": 0, "budget": 250.0},
        ])
        now = _et(2026, 3, 10, 14, 30)
        tranche = schedule.get_active_tranche(now)
        assert tranche is not None
        assert tranche.name == "afternoon"

    def test_no_tranche_before_market(self):
        schedule = FundingSchedule([
            {"name": "morning", "start_hour": 9, "start_minute": 30, "budget": 250.0},
        ])
        now = _et(2026, 3, 10, 8, 0)
        tranche = schedule.get_active_tranche(now)
        assert tranche is None

    def test_reset(self):
        schedule = FundingSchedule([
            {"name": "morning", "start_hour": 9, "start_minute": 30, "budget": 250.0},
        ])
        schedule.tranches[0].spent = 100.0
        schedule.tranches[0].trade_count = 2
        schedule.reset()
        assert schedule.tranches[0].spent == 0.0
        assert schedule.tranches[0].trade_count == 0


# --- Settlement Tracker ---

# Explicit tranches for tests (independent of production defaults)
_TEST_TRANCHES = [
    {"name": "morning", "start_hour": 9, "start_minute": 30, "budget": 250.0},
    {"name": "afternoon", "start_hour": 14, "start_minute": 0, "budget": 250.0},
]


class TestSettlementTracker:
    def test_full_capital_available(self):
        tracker = SettlementTracker(total_capital=500.0, tranches=_TEST_TRANCHES)
        now = _et(2026, 3, 10, 10, 0)
        allowed, reason = tracker.can_afford_trade(50.0, now)
        assert allowed

    def test_insufficient_tranche_budget(self):
        tracker = SettlementTracker(total_capital=500.0, tranches=_TEST_TRANCHES)
        now = _et(2026, 3, 10, 10, 0)
        # Spend most of morning tranche
        tranche = tracker.schedule.get_active_tranche(now)
        tranche.spent = 245.0
        allowed, reason = tracker.can_afford_trade(50.0, now)
        assert not allowed
        assert "insufficient" in reason.lower()

    def test_morning_blocks_when_spent(self):
        tracker = SettlementTracker(total_capital=500.0, tranches=_TEST_TRANCHES)
        now = _et(2026, 3, 10, 10, 0)
        # Record 5 purchases of $50 each
        for _ in range(5):
            tracker.record_purchase(50.0, now)
        allowed, reason = tracker.can_afford_trade(50.0, now)
        assert not allowed

    def test_afternoon_tranche_unlocks(self):
        tracker = SettlementTracker(total_capital=500.0, tranches=_TEST_TRANCHES)
        morning = _et(2026, 3, 10, 10, 0)
        # Spend morning tranche
        for _ in range(5):
            tracker.record_purchase(50.0, morning)

        # Afternoon tranche should be available
        afternoon = _et(2026, 3, 10, 14, 30)
        allowed, reason = tracker.can_afford_trade(50.0, afternoon)
        assert allowed

    def test_unused_morning_does_not_carry_over(self):
        tracker = SettlementTracker(total_capital=500.0, tranches=_TEST_TRANCHES)
        morning = _et(2026, 3, 10, 10, 0)
        # Only use $50 of morning's $250
        tracker.record_purchase(50.0, morning)

        # Afternoon budget is still $250, not $250 + $200
        afternoon = _et(2026, 3, 10, 14, 30)
        tranche = tracker.schedule.get_active_tranche(afternoon)
        assert tranche.budget == 250.0
        assert tranche.remaining == 250.0

    def test_trade_count_per_tranche_enforced(self):
        tracker = SettlementTracker(total_capital=500.0, tranches=_TEST_TRANCHES, max_trades_per_tranche=2)
        now = _et(2026, 3, 10, 10, 0)
        tracker.record_purchase(5.0, now)
        tracker.record_purchase(5.0, now)
        allowed, reason = tracker.can_afford_trade(5.0, now)
        assert not allowed
        assert "max trades" in reason.lower()

    def test_pending_settlement(self):
        tracker = SettlementTracker(total_capital=500.0)
        pending = tracker.record_sale(100.0, "trade-1", date(2026, 3, 13))
        assert pending.settlement_date == date(2026, 3, 16)  # Friday -> Monday
        assert tracker.pending_total() == 100.0

    def test_settle_matured(self):
        tracker = SettlementTracker(total_capital=500.0)
        tracker.record_sale(100.0, "trade-1", date(2026, 3, 9))
        # Settle date is 2026-03-10
        settled = tracker.settle_matured(date(2026, 3, 10))
        assert settled == 100.0
        assert tracker.pending_total() == 0.0

    def test_mock_cash_provider_fallback(self):
        mock = MockCashProvider(settled=400.0)
        tracker = SettlementTracker(total_capital=500.0, cash_provider=mock)
        result = tracker.refresh()
        assert result == 400.0

    def test_no_cash_provider_fallback(self):
        tracker = SettlementTracker(total_capital=500.0)
        result = tracker.refresh()
        assert result == 500.0

    def test_get_snapshot(self):
        tracker = SettlementTracker(total_capital=500.0)
        snapshot = tracker.get_snapshot()
        assert "total_capital" in snapshot
        assert "tranches" in snapshot
        assert len(snapshot["tranches"]) == 2

    # --- Cash-settled (immediate) settlement ---

    def test_immediate_settlement_is_settled(self):
        """Cash-settled option proceeds are immediately available."""
        tracker = SettlementTracker(total_capital=500.0)
        pending = tracker.record_immediate_settlement(
            150.0, "spx-trade-1", date(2026, 3, 13)
        )
        assert pending.settled is True
        assert pending.settlement_date == date(2026, 3, 13)
        # Should show as settled, not pending
        assert tracker.pending_total() == 0.0
        assert tracker.settled_total() == 150.0

    def test_immediate_settlement_no_t_plus_1(self):
        """Immediate settlement date equals trade date (no T+1)."""
        tracker = SettlementTracker(total_capital=500.0)
        # Friday trade — normally settles Monday, but immediate should stay Friday
        pending = tracker.record_immediate_settlement(
            200.0, "spx-trade-2", date(2026, 3, 13)  # Friday
        )
        assert pending.settlement_date == date(2026, 3, 13)
        assert pending.settled is True

    def test_immediate_vs_t1_side_by_side(self):
        """MES (T+1) and SPX (immediate) in same session."""
        tracker = SettlementTracker(total_capital=500.0)
        trade_date = date(2026, 3, 10)  # Tuesday

        # MES option — T+1 settlement
        mes = tracker.record_sale(100.0, "mes-1", trade_date)
        assert mes.settled is False
        assert mes.settlement_date == date(2026, 3, 11)  # Wednesday

        # SPX option — immediate
        spx = tracker.record_immediate_settlement(200.0, "spx-1", trade_date)
        assert spx.settled is True
        assert spx.settlement_date == trade_date

        # Only MES is pending
        assert tracker.pending_total() == 100.0
        assert tracker.settled_total() == 200.0

    def test_immediate_settlement_in_snapshot(self):
        tracker = SettlementTracker(total_capital=500.0)
        tracker.record_immediate_settlement(100.0, "spx-1", date(2026, 3, 13))
        snapshot = tracker.get_snapshot()
        assert snapshot["pending_settlements"] == 0.0
        assert snapshot["settled_proceeds"] == 100.0
        details = snapshot["pending_details"]
        assert len(details) == 1
        assert details[0]["settled"] is True
