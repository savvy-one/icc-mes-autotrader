"""BrokerAdapter ABC."""

from __future__ import annotations

from abc import ABC, abstractmethod

from icc.oms.orders import Fill, Order


class BrokerAdapter(ABC):
    @abstractmethod
    def submit_order(self, order: Order) -> Fill | None:
        """Submit order and return fill, or None if rejected."""

    @abstractmethod
    def cancel_order(self, order: Order) -> bool:
        """Cancel an order. Returns True if successful."""

    @abstractmethod
    def get_positions(self) -> list[dict]:
        """Get current positions from broker."""

    @abstractmethod
    def connect(self) -> bool:
        """Establish connection. Returns True if successful."""

    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect from broker."""
