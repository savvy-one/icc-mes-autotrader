"""Typer CLI: backtest, paper, trades, init-db, import-data, config-show."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(
    name="icc",
    help="ICC MES AutoTrader — FSM-driven automated trading for MES futures",
)
console = Console()


@app.command()
def backtest(
    data_file: str = typer.Option(..., "--data", "-d", help="Path to CSV candle data"),
    start: Optional[str] = typer.Option(None, "--start", help="Start date (YYYY-MM-DD)"),
    end: Optional[str] = typer.Option(None, "--end", help="End date (YYYY-MM-DD)"),
    env: str = typer.Option("backtest", "--env", "-e", help="Environment config to use"),
):
    """Run a backtest on historical data."""
    from icc.backtest.data_loader import load_candles_csv
    from icc.backtest.engine import BacktestEngine
    from icc.config import load_config

    config = load_config(env)
    console.print(f"[bold]Loading candles from {data_file}...[/bold]")

    candles = load_candles_csv(data_file)

    if start:
        start_dt = datetime.strptime(start, "%Y-%m-%d")
        candles = [c for c in candles if c.timestamp >= start_dt]
    if end:
        end_dt = datetime.strptime(end, "%Y-%m-%d")
        candles = [c for c in candles if c.timestamp <= end_dt]

    console.print(f"[bold]{len(candles)} candles loaded[/bold]")

    engine = BacktestEngine(config, candles)
    result = engine.run()

    # Display results
    summary = result.summary()
    table = Table(title="Backtest Results")
    table.add_column("Metric", style="bold")
    table.add_column("Value")
    for k, v in summary.items():
        table.add_row(k.replace("_", " ").title(), str(v))
    console.print(table)


@app.command()
def paper():
    """Start paper trading session (placeholder)."""
    from icc.config import load_config

    config = load_config("paper")
    console.print(Panel(
        "Paper trading mode — requires broker API integration.\n"
        "Use [bold]icc backtest[/bold] with historical data for now.",
        title="Paper Trading",
        border_style="yellow",
    ))


@app.command()
def trades(
    session_id: Optional[str] = typer.Option(None, "--session", "-s", help="Filter by session"),
    limit: int = typer.Option(20, "--limit", "-n", help="Number of trades to show"),
):
    """Show recent trades from the database."""
    from icc.config import load_config
    from icc.db.engine import get_session

    config = load_config()
    db = get_session(config.db_url)

    from icc.db.models import TradeRecord
    query = db.query(TradeRecord).order_by(TradeRecord.entry_time.desc())
    if session_id:
        query = query.filter(TradeRecord.session_id == session_id)
    records = query.limit(limit).all()

    if not records:
        console.print("[dim]No trades found.[/dim]")
        return

    table = Table(title="Trade History")
    table.add_column("ID", style="dim")
    table.add_column("Session")
    table.add_column("Side")
    table.add_column("Entry")
    table.add_column("Exit")
    table.add_column("P&L")
    table.add_column("Reason")
    table.add_column("Time")

    for r in records:
        pnl_str = f"${r.pnl:.2f}" if r.pnl is not None else "—"
        exit_str = f"{r.exit_price:.2f}" if r.exit_price is not None else "—"
        table.add_row(
            str(r.id), r.session_id, r.side,
            f"{r.entry_price:.2f}", exit_str, pnl_str,
            r.exit_reason or "—",
            r.entry_time.strftime("%Y-%m-%d %H:%M") if r.entry_time else "—",
        )
    console.print(table)
    db.close()


@app.command("init-db")
def init_db(
    env: str = typer.Option("backtest", "--env", "-e", help="Environment config"),
):
    """Initialize the SQLite database."""
    from icc.config import load_config
    from icc.db.engine import init_db as _init_db

    config = load_config(env)
    _init_db(config.db_url)
    console.print(f"[green]Database initialized:[/green] {config.db_url}")


@app.command("import-data")
def import_data(
    filepath: str = typer.Argument(..., help="Path to CSV file"),
    symbol: str = typer.Option("MES", "--symbol", "-s", help="Symbol name"),
    env: str = typer.Option("backtest", "--env", "-e", help="Environment config"),
):
    """Import candle data from CSV into the database."""
    from icc.backtest.data_loader import import_csv_to_db
    from icc.config import load_config
    from icc.db.engine import get_session, init_db as _init_db

    config = load_config(env)
    _init_db(config.db_url)
    db = get_session(config.db_url)

    count = import_csv_to_db(db, filepath, symbol)
    console.print(f"[green]Imported {count} candles for {symbol}[/green]")
    db.close()


@app.command("config-show")
def config_show(
    env: str = typer.Argument("backtest", help="Environment to show config for"),
):
    """Display the merged configuration for an environment."""
    from icc.config import load_config

    config = load_config(env)
    console.print(Panel(
        config.model_dump_json(indent=2),
        title=f"Config: {env}",
        border_style="blue",
    ))


if __name__ == "__main__":
    app()
