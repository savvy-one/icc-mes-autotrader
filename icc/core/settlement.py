"""Settlement tracking + staggered funding for cash accounts (T+1 settlement)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Optional

import pytz

_ET = pytz.timezone("US/Eastern")

logger = logging.getLogger(__name__)

# US market holidays (2026) — extend annually
_US_HOLIDAYS_2026 = {
    date(2026, 1, 1),   # New Year's Day
    date(2026, 1, 19),  # MLK Day
    date(2026, 2, 16),  # Presidents' Day
    date(2026, 4, 3),   # Good Friday
    date(2026, 5, 25),  # Memorial Day
    date(2026, 7, 3),   # Independence Day (observed)
    date(2026, 9, 7),   # Labor Day
    date(2026, 11, 26), # Thanksgiving
    date(2026, 12, 25), # Christmas
}

_US_HOLIDAYS_2025 = {
    date(2025, 1, 1),
    date(2025, 1, 20),
    date(2025, 2, 17),
    date(2025, 4, 18),
    date(2025, 5, 26),
    date(2025, 7, 4),
    date(2025, 9, 1),
    date(2025, 11, 27),
    date(2025, 12, 25),
}

US_HOLIDAYS = _US_HOLIDAYS_2025 | _US_HOLIDAYS_2026


def is_business_day(d: date) -> bool:
    """Check if a date is a US business day (weekday and not a holiday)."""
    return d.weekday() < 5 and d not in US_HOLIDAYS


def next_business_day(d: date) -> date:
    """Return the next business day after date d."""
    nxt = d + timedelta(days=1)
    while not is_business_day(nxt):
        nxt += timedelta(days=1)
    return nxt


def settlement_date_for_trade(trade_date: date) -> date:
    """T+1 settlement: next business day after trade date."""
    return next_business_day(trade_date)


@dataclass
class PendingSettlement:
    """Tracks proceeds from a closed trade awaiting settlement."""
    trade_id: str
    proceeds: float
    trade_date: date
    settlement_date: date
    settled: bool = False


@dataclass
class FundingTranche:
    """A time-bounded funding allocation."""
    name: str
    start_hour: int
    start_minute: int
    budget: float
    spent: float = 0.0
    trade_count: int = 0

    @property
    def remaining(self) -> float:
        return max(0.0, self.budget - self.spent)

    @property
    def start_time(self) -> time:
        return time(self.start_hour, self.start_minute)

    def can_afford(self, cost: float, safety_buffer: float = 10.0) -> tuple[bool, str]:
        """Check if this tranche can afford a trade of given cost."""
        if cost > self.remaining - safety_buffer:
            return False, (
                f"Tranche '{self.name}' insufficient: "
                f"need ${cost:.2f} but only ${self.remaining:.2f} remaining "
                f"(${safety_buffer:.2f} safety buffer)"
            )
        return True, "OK"

    def record_purchase(self, cost: float) -> None:
        self.spent += cost
        self.trade_count += 1


class FundingSchedule:
    """Manages staggered morning/afternoon funding tranches."""

    def __init__(self, tranches: list[dict]) -> None:
        self._tranches = [
            FundingTranche(
                name=t["name"],
                start_hour=t["start_hour"],
                start_minute=t["start_minute"],
                budget=t["budget"],
            )
            for t in tranches
        ]

    def get_active_tranche(self, now: Optional[datetime] = None) -> FundingTranche | None:
        """Return the active tranche for the given time.

        The active tranche is the last tranche whose start_time <= now.
        Tranche start times are defined in US/Eastern; we convert now to ET
        before comparing (system may be in a different timezone).
        """
        if now is None:
            now = datetime.now(_ET)
        elif now.tzinfo is None:
            # Naive datetime — assume local, convert to ET
            now = now.astimezone(_ET)
        else:
            now = now.astimezone(_ET)
        current_time = now.time()

        active = None
        for tranche in self._tranches:
            if current_time >= tranche.start_time:
                active = tranche
        return active

    def reset(self) -> None:
        """Reset all tranches for a new trading day."""
        for t in self._tranches:
            t.spent = 0.0
            t.trade_count = 0

    @property
    def tranches(self) -> list[FundingTranche]:
        return self._tranches

    def get_snapshot(self) -> list[dict]:
        return [
            {
                "name": t.name,
                "budget": t.budget,
                "spent": t.spent,
                "remaining": t.remaining,
                "trade_count": t.trade_count,
                "start_time": t.start_time.isoformat(),
            }
            for t in self._tranches
        ]


class SettlementTracker:
    """Tracks settled cash and pending settlements for cash account compliance.

    Integrates with FundingSchedule for staggered funding and CashProvider
    for IB cash queries, with local tracking fallback.
    """

    def __init__(
        self,
        total_capital: float = 500.0,
        safety_buffer: float = 10.0,
        tranches: list[dict] | None = None,
        max_trades_per_tranche: int = 2,
        cash_provider=None,
    ) -> None:
        self.total_capital = total_capital
        self.safety_buffer = safety_buffer
        self.max_trades_per_tranche = max_trades_per_tranche
        self._cash_provider = cash_provider
        self._pending: list[PendingSettlement] = []

        # Default tranches: morning ($1250 at 9:30) + afternoon ($1250 at 13:00)
        if tranches is None:
            tranches = [
                {"name": "morning", "start_hour": 9, "start_minute": 30, "budget": 1250.0},
                {"name": "afternoon", "start_hour": 13, "start_minute": 0, "budget": 1250.0},
            ]
        self.schedule = FundingSchedule(tranches)

    def can_afford_trade(self, cost: float, now: Optional[datetime] = None) -> tuple[bool, str]:
        """Check if a trade can be afforded within the active tranche.

        Returns (allowed, reason).
        """
        tranche = self.schedule.get_active_tranche(now)
        if tranche is None:
            return False, "No active funding tranche at this time"

        # Check tranche trade count
        if tranche.trade_count >= self.max_trades_per_tranche:
            return False, (
                f"Tranche '{tranche.name}' max trades "
                f"({self.max_trades_per_tranche}) reached"
            )

        # Check tranche budget
        return tranche.can_afford(cost, self.safety_buffer)

    def record_purchase(self, cost: float, now: Optional[datetime] = None) -> None:
        """Record a trade purchase against the active tranche."""
        tranche = self.schedule.get_active_tranche(now)
        if tranche is not None:
            tranche.record_purchase(cost)
            logger.info(
                "Settlement: recorded $%.2f purchase on tranche '%s' "
                "(remaining: $%.2f, trades: %d)",
                cost, tranche.name, tranche.remaining, tranche.trade_count,
            )

    def record_sale(self, proceeds: float, trade_id: str,
                    trade_date: Optional[date] = None) -> PendingSettlement:
        """Record sale proceeds as pending settlement (T+1)."""
        if trade_date is None:
            trade_date = date.today()
        settle_date = settlement_date_for_trade(trade_date)
        pending = PendingSettlement(
            trade_id=trade_id,
            proceeds=proceeds,
            trade_date=trade_date,
            settlement_date=settle_date,
        )
        self._pending.append(pending)
        logger.info(
            "Settlement: recorded $%.2f sale for trade %s, "
            "settles on %s",
            proceeds, trade_id, settle_date.isoformat(),
        )
        return pending

    def record_immediate_settlement(self, proceeds: float, trade_id: str,
                                    trade_date: Optional[date] = None) -> PendingSettlement:
        """Record sale proceeds as immediately settled (cash-settled options like SPX).

        Cash-settled options deliver cash at expiration/exercise — no T+1 delay.
        The proceeds are available for trading on the same day.
        """
        if trade_date is None:
            trade_date = date.today()
        pending = PendingSettlement(
            trade_id=trade_id,
            proceeds=proceeds,
            trade_date=trade_date,
            settlement_date=trade_date,
            settled=True,
        )
        self._pending.append(pending)
        logger.info(
            "Settlement: recorded $%.2f immediate settlement for trade %s (cash-settled)",
            proceeds, trade_id,
        )
        return pending

    def settle_matured(self, today: Optional[date] = None) -> float:
        """Mark matured pending settlements as settled. Returns total settled."""
        if today is None:
            today = date.today()
        settled_total = 0.0
        for p in self._pending:
            if not p.settled and p.settlement_date <= today:
                p.settled = True
                settled_total += p.proceeds
        if settled_total > 0:
            logger.info("Settlement: $%.2f matured today", settled_total)
        return settled_total

    def pending_total(self) -> float:
        """Total unsettled proceeds."""
        return sum(p.proceeds for p in self._pending if not p.settled)

    def settled_total(self) -> float:
        """Total settled proceeds."""
        return sum(p.proceeds for p in self._pending if p.settled)

    def refresh(self) -> float | None:
        """Query IB for current settled cash, falling back to local tracking."""
        if self._cash_provider is not None:
            settled = self._cash_provider.get_settled_cash()
            if settled is not None:
                return settled
        # Fallback: total capital minus pending
        return self.total_capital - self.pending_total()

    def reset_day(self) -> None:
        """Reset for a new trading day."""
        self.settle_matured()
        self.schedule.reset()

    def get_snapshot(self) -> dict:
        """Return current settlement state for dashboard/API."""
        return {
            "total_capital": self.total_capital,
            "safety_buffer": self.safety_buffer,
            "pending_settlements": self.pending_total(),
            "settled_proceeds": self.settled_total(),
            "available_cash": self.refresh(),
            "tranches": self.schedule.get_snapshot(),
            "pending_details": [
                {
                    "trade_id": p.trade_id,
                    "proceeds": p.proceeds,
                    "trade_date": p.trade_date.isoformat(),
                    "settlement_date": p.settlement_date.isoformat(),
                    "settled": p.settled,
                }
                for p in self._pending
            ],
        }
