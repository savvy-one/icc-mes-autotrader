"""Database engine setup and initialization."""

from __future__ import annotations

from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import Session, sessionmaker

from icc.db.models import Base

# Support multiple engines keyed by URL
_engines: dict[str, Engine] = {}
_session_factories: dict[str, sessionmaker[Session]] = {}

_DEFAULT_URL = "sqlite:///icc_trades.db"


def get_engine(db_url: str = _DEFAULT_URL) -> Engine:
    if db_url not in _engines:
        _engines[db_url] = create_engine(db_url, echo=False)
    return _engines[db_url]


def get_session(db_url: str = _DEFAULT_URL) -> Session:
    if db_url not in _session_factories:
        _session_factories[db_url] = sessionmaker(bind=get_engine(db_url))
    return _session_factories[db_url]()


def init_db(db_url: str = _DEFAULT_URL) -> None:
    """Create all tables."""
    engine = get_engine(db_url)
    Base.metadata.create_all(engine)


def reset_engine() -> None:
    """Reset all engines (for testing)."""
    global _engines, _session_factories
    _engines = {}
    _session_factories = {}
