"""CSV/DB candle loader."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from icc.db.models import CandleRecord
from icc.market.candle import Candle


def load_candles_csv(filepath: str | Path, symbol: str = "MES",
                     date_format: str = "%Y-%m-%d %H:%M:%S") -> list[Candle]:
    """Load candles from CSV. Expected columns: timestamp,open,high,low,close,volume."""
    candles: list[Candle] = []
    path = Path(filepath)
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            candles.append(Candle(
                timestamp=datetime.strptime(row["timestamp"], date_format),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=int(row["volume"]),
                symbol=symbol,
            ))
    return candles


def load_candles_db(db: Session, symbol: str, start: datetime,
                    end: datetime) -> list[Candle]:
    """Load candles from database."""
    records = (
        db.query(CandleRecord)
        .filter(
            CandleRecord.symbol == symbol,
            CandleRecord.timestamp >= start,
            CandleRecord.timestamp <= end,
        )
        .order_by(CandleRecord.timestamp)
        .all()
    )
    return [
        Candle(
            timestamp=r.timestamp,
            open=r.open,
            high=r.high,
            low=r.low,
            close=r.close,
            volume=r.volume,
            symbol=r.symbol,
        )
        for r in records
    ]


def import_csv_to_db(db: Session, filepath: str | Path, symbol: str = "MES",
                     date_format: str = "%Y-%m-%d %H:%M:%S") -> int:
    """Import CSV candles into database. Returns count of records inserted."""
    candles = load_candles_csv(filepath, symbol, date_format)
    records = [
        CandleRecord(
            symbol=c.symbol, timestamp=c.timestamp,
            open=c.open, high=c.high, low=c.low, close=c.close, volume=c.volume,
        )
        for c in candles
    ]
    db.add_all(records)
    db.commit()
    return len(records)
