"""Candle dataclass and CandleBuffer ring buffer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from collections import deque


@dataclass(frozen=True, slots=True)
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    symbol: str = "MES"

    @property
    def mid(self) -> float:
        return (self.high + self.low) / 2.0

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def is_bullish(self) -> bool:
        return self.close >= self.open


class CandleBuffer:
    """Fixed-size ring buffer for candles."""

    def __init__(self, maxlen: int = 200):
        self._buf: deque[Candle] = deque(maxlen=maxlen)

    def append(self, candle: Candle) -> None:
        self._buf.append(candle)

    def __len__(self) -> int:
        return len(self._buf)

    def __getitem__(self, index: int | slice) -> Candle | list[Candle]:
        if isinstance(index, slice):
            return list(self._buf)[index]
        return self._buf[index]

    @property
    def last(self) -> Candle | None:
        return self._buf[-1] if self._buf else None

    def closes(self, n: int | None = None) -> list[float]:
        data = list(self._buf) if n is None else list(self._buf)[-n:]
        return [c.close for c in data]

    def highs(self, n: int | None = None) -> list[float]:
        data = list(self._buf) if n is None else list(self._buf)[-n:]
        return [c.high for c in data]

    def lows(self, n: int | None = None) -> list[float]:
        data = list(self._buf) if n is None else list(self._buf)[-n:]
        return [c.low for c in data]

    def volumes(self, n: int | None = None) -> list[int]:
        data = list(self._buf) if n is None else list(self._buf)[-n:]
        return [c.volume for c in data]

    def candles(self, n: int | None = None) -> list[Candle]:
        if n is None:
            return list(self._buf)
        return list(self._buf)[-n:]
