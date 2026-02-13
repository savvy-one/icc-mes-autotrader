"""Rich Live 4-panel dashboard."""

from __future__ import annotations

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from icc.constants import FSMState
from icc.core.risk import RiskState


def build_status_panel(fsm_state: FSMState, risk_state: RiskState,
                       current_price: float = 0.0) -> Panel:
    table = Table(show_header=False, box=None)
    table.add_column("Key", style="bold")
    table.add_column("Value")
    table.add_row("FSM State", fsm_state.value)
    table.add_row("Daily P&L", f"${risk_state.daily_pnl:.2f}")
    table.add_row("Trades", str(risk_state.trade_count))
    table.add_row("Consec. Losses", str(risk_state.consecutive_losses))
    table.add_row("Kill Switch", "YES" if risk_state.killed else "No")
    table.add_row("Current Price", f"{current_price:.2f}")
    return Panel(table, title="Status", border_style="blue")


def build_position_panel(position_info: dict | None) -> Panel:
    if position_info is None:
        return Panel("FLAT — No open position", title="Position", border_style="dim")
    table = Table(show_header=False, box=None)
    table.add_column("Key", style="bold")
    table.add_column("Value")
    for k, v in position_info.items():
        table.add_row(k, str(v))
    return Panel(table, title="Position", border_style="green")


def build_trades_panel(trades: list[dict]) -> Panel:
    table = Table()
    table.add_column("#", style="dim")
    table.add_column("Side")
    table.add_column("Entry")
    table.add_column("Exit")
    table.add_column("P&L")
    table.add_column("Reason")
    for i, t in enumerate(trades[-10:], 1):
        pnl_style = "green" if t.get("pnl", 0) > 0 else "red"
        table.add_row(
            str(i),
            t.get("side", ""),
            f"{t.get('entry', 0):.2f}",
            f"{t.get('exit', 0):.2f}",
            Text(f"${t.get('pnl', 0):.2f}", style=pnl_style),
            t.get("reason", ""),
        )
    return Panel(table, title="Recent Trades", border_style="yellow")


def build_risk_panel(risk_state: RiskState, account_size: float = 500.0) -> Panel:
    table = Table(show_header=False, box=None)
    table.add_column("Metric", style="bold")
    table.add_column("Value")
    pnl_pct = (risk_state.daily_pnl / account_size * 100) if account_size else 0
    table.add_row("Daily P&L %", f"{pnl_pct:.1f}%")
    table.add_row("Open Positions", str(risk_state.open_positions))
    table.add_row("Pre-Kill", "YES" if risk_state.pre_kill_triggered else "No")
    table.add_row("Killed", "YES" if risk_state.killed else "No")
    return Panel(table, title="Risk", border_style="red")


def build_dashboard(fsm_state: FSMState, risk_state: RiskState,
                    position_info: dict | None, trades: list[dict],
                    current_price: float = 0.0,
                    account_size: float = 500.0) -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(name="top", size=10),
        Layout(name="bottom"),
    )
    layout["top"].split_row(
        Layout(build_status_panel(fsm_state, risk_state, current_price)),
        Layout(build_risk_panel(risk_state, account_size)),
    )
    layout["bottom"].split_row(
        Layout(build_position_panel(position_info)),
        Layout(build_trades_panel(trades)),
    )
    return layout
