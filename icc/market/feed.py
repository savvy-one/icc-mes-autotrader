"""MarketFeed ABC, ReplayFeed, LiveFeed."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator

from icc.market.candle import Candle


class MarketFeed(ABC):
    @abstractmethod
    def __iter__(self) -> Iterator[Candle]:
        """Yield candles one at a time."""

    @abstractmethod
    def start(self) -> None:
        """Start the feed."""

    @abstractmethod
    def stop(self) -> None:
        """Stop the feed."""


class ReplayFeed(MarketFeed):
    """Replays a list of candles for backtesting."""

    def __init__(self, candles: list[Candle]):
        self._candles = candles
        self._running = False

    def start(self) -> None:
        self._running = True

    def stop(self) -> None:
        self._running = False

    def __iter__(self) -> Iterator[Candle]:
        self.start()
        for candle in self._candles:
            if not self._running:
                break
            yield candle
        self.stop()


class LiveFeed(MarketFeed):
    """Placeholder for live market data feed."""

    def __init__(self) -> None:
        self._running = False

    def start(self) -> None:
        self._running = True

    def stop(self) -> None:
        self._running = False

    def __iter__(self) -> Iterator[Candle]:
        raise NotImplementedError("LiveFeed requires broker integration")
