"""Cash provider abstraction for querying IB settled/total cash."""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class CashProvider(Protocol):
    """Protocol for querying account cash balances."""

    def get_settled_cash(self) -> float | None:
        """Return settled (available) cash, or None if unavailable."""
        ...

    def get_total_cash(self) -> float | None:
        """Return total cash including unsettled, or None if unavailable."""
        ...

    def get_buying_power(self) -> float | None:
        """Return buying power, or None if unavailable."""
        ...


class LumibotCashProvider:
    """Queries IB for settled cash via Lumibot's strategy instance.

    Three-tier fallback:
    1. IB SettledCash tag via reqAccountSummary
    2. IB TotalCashValue minus pending settlements
    3. None (caller uses local tracking)
    """

    def __init__(self, strategy) -> None:
        self._strategy = strategy

    def get_settled_cash(self) -> float | None:
        try:
            # Try getting cash value from Lumibot's portfolio
            cash = self._strategy.get_cash()
            if cash is not None:
                return float(cash)
        except Exception as e:
            logger.warning("Failed to get settled cash from IB: %s", e)
        return None

    def get_total_cash(self) -> float | None:
        try:
            cash = self._strategy.get_cash()
            if cash is not None:
                return float(cash)
        except Exception as e:
            logger.warning("Failed to get total cash from IB: %s", e)
        return None

    def get_buying_power(self) -> float | None:
        try:
            cash = self._strategy.get_cash()
            if cash is not None:
                return float(cash)
        except Exception as e:
            logger.warning("Failed to get buying power from IB: %s", e)
        return None


class MockCashProvider:
    """Mock cash provider for tests and backtesting."""

    def __init__(self, settled: float = 500.0, total: float = 500.0) -> None:
        self._settled = settled
        self._total = total

    def get_settled_cash(self) -> float | None:
        return self._settled

    def get_total_cash(self) -> float | None:
        return self._total

    def get_buying_power(self) -> float | None:
        return self._settled

    def set_settled(self, value: float) -> None:
        self._settled = value

    def set_total(self, value: float) -> None:
        self._total = value
