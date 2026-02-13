"""Database engine setup and initialization."""

from __future__ import annotations

from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import Session, sessionmaker

from icc.db.models import Base

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine(db_url: str = "sqlite:///icc_trades.db") -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(db_url, echo=False)
    return _engine


def get_session(db_url: str = "sqlite:///icc_trades.db") -> Session:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(db_url))
    return _session_factory()


def init_db(db_url: str = "sqlite:///icc_trades.db") -> None:
    """Create all tables."""
    engine = get_engine(db_url)
    Base.metadata.create_all(engine)


def reset_engine() -> None:
    """Reset global engine (for testing)."""
    global _engine, _session_factory
    _engine = None
    _session_factory = None
