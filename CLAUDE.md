# CLAUDE.md

## Project Overview

**ICC MES AutoTrader** — FSM-driven automated trading engine for MES futures using the ICC (Indication → Correction → Continuation) methodology, with strict risk controls for a $500 account.

## Commands

```bash
cd ~/icc-mes-autotrader && source venv/bin/activate

# CLI
icc --help
icc backtest --start 2024-01-01 --end 2024-03-01
icc paper
icc trades
icc init-db
icc import-data data.csv
icc config-show backtest

# Development
pip install -e ".[dev]"
pytest
pytest tests/test_indicators.py -v
```

## Architecture

- **FSM drives everything** — strategy produces signals, FSM decides actions, risk engine vetoes
- **Package:** `icc/` with submodules: core, market, oms, broker, db, alerts, backtest, dashboard
- **Config:** Pydantic Settings + YAML merge (`configs/`)
- **DB:** SQLAlchemy 2.0 + SQLite
- **CLI:** Typer + Rich

## Key Design Decisions

- Sync core, async broker I/O
- Risk engine is a gate — only vetoes, never initiates (except kill switch)
- Pure indicator functions — no state, easy to test
- `Trader.on_candle()` — single integration point
- 11 FSM states: FLAT, INDICATION_UP/DOWN, CORRECTION_UP/DOWN, CONTINUATION_UP/DOWN, IN_TRADE_UP/DOWN, EXIT, RISK_BLOCKED

## Risk Parameters

- 20% daily kill ($100 on $500), 18% pre-kill warning
- Max 2 trades/session, max 1 position
- 5min cooldown after loss, max 2 consecutive losses
- $2.50/side commission, 1 tick slippage
