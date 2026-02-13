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


@app.command()
def live(
    port: int = typer.Option(7497, "--port", "-p", help="IB Gateway socket port (7497=paper, 7496=live)"),
    client_id: str = typer.Option("100", "--client-id", help="IB client ID"),
    ip: str = typer.Option("127.0.0.1", "--ip", help="IB Gateway IP address"),
    headless: bool = typer.Option(False, "--headless", help="Run without web dashboard"),
    web_port: int = typer.Option(8000, "--web-port", help="Web dashboard port"),
    auto: bool = typer.Option(False, "--auto", help="Autonomous mode: auto-start/stop on schedule with watchdog"),
):
    """Start live autonomous trading via Lumibot + Interactive Brokers."""
    import os
    os.environ["ICC_IB__SOCKET_PORT"] = str(port)
    os.environ["ICC_IB__CLIENT_ID"] = client_id
    os.environ["ICC_IB__IP"] = ip

    if auto:
        _run_auto_live(headless=headless, web_port=web_port)
    elif headless:
        _run_headless_live()
    else:
        import uvicorn
        console.print(Panel(
            f"Starting ICC Live Trading\n"
            f"IB Gateway: [bold]{ip}:{port}[/bold] (client {client_id})\n"
            f"Dashboard: [bold]http://127.0.0.1:{web_port}[/bold]\n\n"
            f"[yellow]Click 'Start Live' on the dashboard to begin trading.[/yellow]\n"
            "Press Ctrl+C to stop.",
            title="ICC Live Trading",
            border_style="red" if port == 7496 else "yellow",
        ))
        uvicorn.run(
            "icc.web.app:app",
            host="127.0.0.1",
            port=web_port,
            log_level="info",
        )


def _run_auto_live(headless: bool = False, web_port: int = 8000):
    """Run fully autonomous live trading with scheduler + watchdog."""
    import signal
    import threading

    from icc.config import load_config
    from icc.core.events import EventBus, EventType
    from icc.core.scheduler import SessionScheduler
    from icc.core.watchdog import Watchdog
    from icc.logging_config import setup_logging
    from icc.web.trading_session import TradingSession

    config = load_config("live")
    setup_logging(log_dir=config.log_dir, level=config.log_level)

    event_bus = EventBus()
    session = TradingSession(event_bus)

    # Set up watchdog
    watchdog = Watchdog(session)
    session.set_watchdog(watchdog)

    # Set up scheduler
    scheduler = SessionScheduler(session)
    scheduler.start()
    watchdog.start()

    console.print(Panel(
        "ICC Autonomous Trading Mode\n"
        f"Scheduler: open=09:30 ET, close=11:00 ET (weekdays)\n"
        f"Watchdog: warn=3min, restart=5min\n"
        f"Logs: {config.log_dir}/\n"
        + (f"Dashboard: http://127.0.0.1:{web_port}\n" if not headless else "Headless mode (no dashboard)\n")
        + "\nPress Ctrl+C to flatten and stop.",
        title="ICC Auto Trading",
        border_style="green",
    ))

    stop_event = threading.Event()

    def _drain_events():
        """Drain events to console and feed watchdog."""
        while not stop_event.is_set():
            for ev in event_bus.drain():
                console.print(f"[dim]{ev.event_type.value}[/dim] {ev.data}")
                if ev.event_type == EventType.CANDLE:
                    session.notify_candle()
            stop_event.wait(0.5)

    def _shutdown(sig, frame):
        console.print("\n[red]Shutting down autonomous mode...[/red]")
        if session.is_running:
            session.flatten_and_stop()
        watchdog.stop()
        scheduler.stop()
        stop_event.set()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    if headless:
        relay = threading.Thread(target=_drain_events, daemon=True)
        relay.start()
        # Block until stopped
        while not stop_event.is_set():
            import time
            time.sleep(1.0)
    else:
        # Share state with web app, then start uvicorn
        from icc.web.app import init_shared_state
        init_shared_state(event_bus, session, scheduler)

        import uvicorn
        uvicorn.run(
            "icc.web.app:app",
            host="127.0.0.1",
            port=web_port,
            log_level="info",
        )

    console.print("[green]Autonomous trading session ended.[/green]")


def _run_headless_live():
    """Run live trading without the web dashboard."""
    import signal
    import threading

    from icc.core.events import EventBus, EventType
    from icc.web.trading_session import TradingSession

    event_bus = EventBus()
    session = TradingSession(event_bus)

    console.print(Panel(
        "Starting headless live trading...\nPress Ctrl+C to stop.",
        title="ICC Headless Live",
        border_style="yellow",
    ))

    session.start_live()

    # Print events to console
    stop_event = threading.Event()

    def _drain_events():
        while not stop_event.is_set():
            for ev in event_bus.drain():
                console.print(f"[dim]{ev.event_type.value}[/dim] {ev.data}")
            stop_event.wait(0.5)

    relay = threading.Thread(target=_drain_events, daemon=True)
    relay.start()

    def _shutdown(sig, frame):
        console.print("\n[red]Shutting down...[/red]")
        session.stop()
        stop_event.set()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # Block until session ends
    while session.is_running:
        import time
        time.sleep(1.0)

    console.print("[green]Live trading session ended.[/green]")


@app.command()
def web(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Bind host"),
    port: int = typer.Option(8000, "--port", "-p", help="Bind port"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload (dev)"),
):
    """Start the web dashboard server."""
    import uvicorn

    console.print(Panel(
        f"Starting ICC Web Dashboard at [bold]http://{host}:{port}[/bold]\n"
        "Press Ctrl+C to stop.",
        title="ICC Web Dashboard",
        border_style="blue",
    ))
    uvicorn.run(
        "icc.web.app:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


if __name__ == "__main__":
    app()
