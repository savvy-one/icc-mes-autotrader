"""Economic calendar filter — avoid trading during high-impact events."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Blackout windows in minutes: (before_event, after_event)
EVENT_BLACKOUTS = {
    "FOMC": (30, 60),
    "CPI": (15, 30),
    "NFP": (15, 30),
    "PPI": (10, 20),
    "GDP": (10, 20),
    "ISM": (10, 15),
    "RETAIL_SALES": (10, 15),
    "JOBLESS_CLAIMS": (5, 10),
    "DEFAULT": (10, 15),
}


@dataclass
class CalendarEvent:
    name: str
    event_type: str  # FOMC, CPI, NFP, etc.
    timestamp: datetime
    impact: str = "high"  # high, medium, low


@dataclass
class CalendarState:
    in_blackout: bool
    active_event: Optional[str] = None
    blackout_end: Optional[datetime] = None
    confidence_mult: float = 1.0


class EconomicCalendar:
    """Loads economic events from JSON and checks for blackout windows."""

    def __init__(self, calendar_file: str = "data/econ_calendar.json") -> None:
        self._events: list[CalendarEvent] = []
        self._load(calendar_file)

    def _load(self, path: str) -> None:
        """Load events from JSON file."""
        filepath = Path(path)
        if not filepath.is_absolute():
            # Resolve relative to project root
            filepath = Path(__file__).resolve().parent.parent.parent / path
        if not filepath.exists():
            logger.warning("Economic calendar file not found: %s", filepath)
            return
        try:
            with open(filepath) as f:
                data = json.load(f)
            for entry in data.get("events", []):
                self._events.append(CalendarEvent(
                    name=entry["name"],
                    event_type=entry.get("type", "DEFAULT"),
                    timestamp=datetime.fromisoformat(entry["timestamp"]),
                    impact=entry.get("impact", "high"),
                ))
            logger.info("Loaded %d economic calendar events", len(self._events))
        except Exception as e:
            logger.error("Failed to load economic calendar: %s", e)

    def check(self, now: Optional[datetime] = None) -> CalendarState:
        """Check if `now` falls within any event's blackout window."""
        if now is None:
            now = datetime.now()

        for event in self._events:
            before_min, after_min = EVENT_BLACKOUTS.get(
                event.event_type, EVENT_BLACKOUTS["DEFAULT"]
            )
            blackout_start = event.timestamp - timedelta(minutes=before_min)
            blackout_end = event.timestamp + timedelta(minutes=after_min)

            if blackout_start <= now <= blackout_end:
                return CalendarState(
                    in_blackout=True,
                    active_event=f"{event.event_type}: {event.name}",
                    blackout_end=blackout_end,
                    confidence_mult=0.0,
                )

        return CalendarState(in_blackout=False, confidence_mult=1.0)

    @property
    def event_count(self) -> int:
        return len(self._events)
