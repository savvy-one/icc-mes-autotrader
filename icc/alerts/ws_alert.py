"""WebSocketAlertChannel — pushes alerts through EventBus for WebSocket delivery."""

from __future__ import annotations

from typing import TYPE_CHECKING

from icc.alerts.base import AlertChannel

if TYPE_CHECKING:
    from icc.core.events import EventBus


class WebSocketAlertChannel(AlertChannel):
    """Routes alerts into the EventBus so they reach connected WebSocket clients."""

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus

    def send(self, alert_type: str, message: str) -> bool:
        from icc.core.events import EventType
        self._event_bus.emit(EventType.ALERT, {
            "alert_type": alert_type,
            "message": message,
        })
        return True
