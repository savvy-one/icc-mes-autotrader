"""Repository CRUD functions."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from icc.db.models import (
    AuditLogRecord,
    CandleRecord,
    OrderRecord,
    RiskEventRecord,
    SessionRecord,
    TradeRecord,
)


# --- Trades ---

def create_trade(db: Session, **kwargs) -> TradeRecord:
    record = TradeRecord(**kwargs)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def close_trade(db: Session, trade_id: int, exit_price: float, pnl: float,
                exit_reason: str) -> TradeRecord:
    record = db.get(TradeRecord, trade_id)
    if record is None:
        raise ValueError(f"Trade {trade_id} not found")
    record.exit_price = exit_price
    record.pnl = pnl
    record.exit_time = datetime.utcnow()
    record.exit_reason = exit_reason
    db.commit()
    db.refresh(record)
    return record


def get_session_trades(db: Session, session_id: str) -> list[TradeRecord]:
    return db.query(TradeRecord).filter(TradeRecord.session_id == session_id).all()


# --- Orders ---

def create_order(db: Session, **kwargs) -> OrderRecord:
    record = OrderRecord(**kwargs)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def update_order_status(db: Session, order_id: int, status: str,
                        broker_order_id: Optional[str] = None) -> OrderRecord:
    record = db.get(OrderRecord, order_id)
    if record is None:
        raise ValueError(f"Order {order_id} not found")
    record.status = status
    if broker_order_id:
        record.broker_order_id = broker_order_id
    record.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(record)
    return record


# --- Risk Events ---

def log_risk_event(db: Session, event_type: str, daily_pnl: float,
                   details: Optional[str] = None) -> RiskEventRecord:
    record = RiskEventRecord(event_type=event_type, daily_pnl=daily_pnl, details=details)
    db.add(record)
    db.commit()
    return record


# --- Audit Log ---

def log_audit(db: Session, action: str, fsm_state: Optional[str] = None,
              details: Optional[str] = None,
              indicator_values: Optional[str] = None) -> AuditLogRecord:
    record = AuditLogRecord(
        action=action, fsm_state=fsm_state, details=details,
        indicator_values=indicator_values,
    )
    db.add(record)
    db.commit()
    return record


# --- Sessions ---

def create_session(db: Session, session_id: str, environment: str,
                   start_time: datetime) -> SessionRecord:
    record = SessionRecord(
        session_id=session_id, environment=environment, start_time=start_time,
    )
    db.add(record)
    db.commit()
    return record


def close_session(db: Session, session_id: str, total_pnl: float,
                  trade_count: int) -> SessionRecord:
    record = db.query(SessionRecord).filter(
        SessionRecord.session_id == session_id
    ).first()
    if record is None:
        raise ValueError(f"Session {session_id} not found")
    record.end_time = datetime.utcnow()
    record.total_pnl = total_pnl
    record.trade_count = trade_count
    record.status = "closed"
    db.commit()
    return record


# --- Candles ---

def insert_candles(db: Session, candles: list[dict]) -> int:
    records = [CandleRecord(**c) for c in candles]
    db.add_all(records)
    db.commit()
    return len(records)


def get_candles(db: Session, symbol: str, start: datetime,
                end: datetime) -> list[CandleRecord]:
    return (
        db.query(CandleRecord)
        .filter(
            CandleRecord.symbol == symbol,
            CandleRecord.timestamp >= start,
            CandleRecord.timestamp <= end,
        )
        .order_by(CandleRecord.timestamp)
        .all()
    )
