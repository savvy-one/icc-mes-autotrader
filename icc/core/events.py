"""EventBus — thread-safe bridge between sync trading thread and async web layer."""

from __future__ import annotations

import logging
import queue
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    CANDLE = "candle"
    FSM_TRANSITION = "fsm_transition"
    ENTRY = "entry"
    EXIT = "exit"
    KILL_SWITCH = "kill_switch"
    RISK_VETO = "risk_veto"
    SNAPSHOT = "snapshot"
    ALERT = "alert"
    SESSION_STARTED = "session_started"
    SESSION_STOPPED = "session_stopped"
    SESSION_FLATTEN = "session_flatten"


@dataclass(frozen=True, slots=True)
class TradingEvent:
    event_type: EventType
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class EventBus:
    """Thread-safe event queue bridging sync producer → async consumer."""

    def __init__(self, maxsize: int = 1000) -> None:
        self._queue: queue.Queue[TradingEvent] = queue.Queue(maxsize=maxsize)

    def emit(self, event_type: EventType, data: dict[str, Any] | None = None) -> None:
        event = TradingEvent(event_type=event_type, data=data or {})
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            logger.warning("EventBus queue full, dropping event: %s", event_type)

    def get(self, timeout: float = 0.1) -> TradingEvent | None:
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def get_nowait(self) -> TradingEvent | None:
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            return None

    def drain(self) -> list[TradingEvent]:
        """Drain all pending events from the queue."""
        events: list[TradingEvent] = []
        while True:
            try:
                events.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return events
