"""LumibotLiveFeed — MarketFeed stub for Lumibot-driven data.

Lumibot drives the iteration loop via on_trading_iteration(), so this
feed does not iterate on its own. It exists for type compatibility with
code that expects a MarketFeed reference.
"""

from __future__ import annotations

from typing import Iterator

from icc.market.candle import Candle
from icc.market.feed import MarketFeed


class LumibotLiveFeed(MarketFeed):
    """Placeholder MarketFeed — Lumibot owns the data loop."""

    def __init__(self) -> None:
        self._running = False

    def start(self) -> None:
        self._running = True

    def stop(self) -> None:
        self._running = False

    def __iter__(self) -> Iterator[Candle]:
        # Lumibot drives candle delivery; this feed is never iterated directly.
        return iter([])
