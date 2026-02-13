"""Rich panel alerts."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel

from icc.alerts.base import AlertChannel

console = Console()

ALERT_STYLES = {
    "kill_switch": "bold red",
    "risk_veto": "yellow",
    "trade_loss": "red",
    "trade_win": "green",
    "info": "blue",
}


class ConsoleAlertChannel(AlertChannel):
    def send(self, alert_type: str, message: str) -> bool:
        style = ALERT_STYLES.get(alert_type, "white")
        console.print(Panel(
            message,
            title=f"[{style}]ALERT: {alert_type.upper()}[/{style}]",
            border_style=style,
        ))
        return True
