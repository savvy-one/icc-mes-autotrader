"""Shared test fixtures."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from icc.config import AppSettings, StrategyConfig, RiskConfig
from icc.db.models import Base
from icc.market.candle import Candle, CandleBuffer


@pytest.fixture
def db_session() -> Session:
    """In-memory SQLite session for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def default_config() -> AppSettings:
    return AppSettings()


@pytest.fixture
def strategy_config() -> StrategyConfig:
    return StrategyConfig()


@pytest.fixture
def risk_config() -> RiskConfig:
    return RiskConfig()


def make_candle(
    close: float,
    high: float | None = None,
    low: float | None = None,
    open_: float | None = None,
    volume: int = 1000,
    ts: datetime | None = None,
) -> Candle:
    """Helper to create a candle with sensible defaults."""
    if high is None:
        high = close + 1.0
    if low is None:
        low = close - 1.0
    if open_ is None:
        open_ = close - 0.5
    if ts is None:
        ts = datetime(2024, 1, 2, 9, 30)
    return Candle(
        timestamp=ts, open=open_, high=high, low=low, close=close, volume=volume,
    )


def make_candle_series(
    closes: list[float],
    base_time: datetime | None = None,
    volume: int = 1000,
) -> list[Candle]:
    """Create a series of candles from close prices."""
    if base_time is None:
        base_time = datetime(2024, 1, 2, 9, 30)
    candles = []
    for i, c in enumerate(closes):
        candles.append(make_candle(
            close=c, volume=volume,
            ts=base_time + timedelta(minutes=i),
        ))
    return candles


@pytest.fixture
def sample_buffer() -> CandleBuffer:
    """Buffer with 30 candles of increasing prices."""
    buf = CandleBuffer(maxlen=200)
    base = datetime(2024, 1, 2, 9, 30)
    for i in range(30):
        buf.append(Candle(
            timestamp=base + timedelta(minutes=i),
            open=100.0 + i * 0.25,
            high=101.0 + i * 0.25,
            low=99.0 + i * 0.25,
            close=100.5 + i * 0.25,
            volume=1000 + i * 10,
        ))
    return buf
