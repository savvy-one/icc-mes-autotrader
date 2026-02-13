"""Logging configuration: rotating file handlers for icc.log, trades.log, errors.log."""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(log_dir: str = "logs", level: str = "INFO") -> None:
    """Configure rotating file handlers and console output.

    Creates three log files:
    - icc.log: all messages (5MB, 5 backups)
    - trades.log: only trade-related messages (icc.core.trader, icc.oms)
    - errors.log: WARNING and above
    """
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger("icc")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)
    root.addHandler(console)

    # Main log — all messages
    main_handler = RotatingFileHandler(
        log_path / "icc.log", maxBytes=5 * 1024 * 1024, backupCount=5
    )
    main_handler.setLevel(logging.DEBUG)
    main_handler.setFormatter(fmt)
    root.addHandler(main_handler)

    # Trades log — filtered to trader/oms loggers
    trades_handler = RotatingFileHandler(
        log_path / "trades.log", maxBytes=5 * 1024 * 1024, backupCount=5
    )
    trades_handler.setLevel(logging.INFO)
    trades_handler.setFormatter(fmt)
    for name in ("icc.core.trader", "icc.oms"):
        logging.getLogger(name).addHandler(trades_handler)

    # Errors log — WARNING+
    error_handler = RotatingFileHandler(
        log_path / "errors.log", maxBytes=5 * 1024 * 1024, backupCount=5
    )
    error_handler.setLevel(logging.WARNING)
    error_handler.setFormatter(fmt)
    root.addHandler(error_handler)
