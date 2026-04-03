#!/bin/bash
# ICC AutoTrader — managed by launchd (KeepAlive)
#
# launchd keeps this script alive. When the auto-trader exits (session close
# via os._exit(0), crash, or any reason), launchd respawns it after 30s.
#
# Cycle: start → wait for market → trade → session close → exit → respawn
#
# User only needs: caffeinate running + IB Gateway connected

set -uo pipefail

PROJECT_DIR="$HOME/icc-mes-autotrader"
LOG_DIR="$PROJECT_DIR/logs"
TODAY=$(date +%m%d)
STARTUP_LOG="$LOG_DIR/startup_${TODAY}.log"

mkdir -p "$LOG_DIR"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') [STARTUP] $*" >> "$STARTUP_LOG"; }

log "=== ICC AutoTrader startup ==="

# 1. Ensure caffeinate is running
if ! pgrep caffeinate > /dev/null 2>&1; then
    caffeinate -dims &
    log "Started caffeinate (PID $!)"
else
    log "Caffeinate already running"
fi

# 2. Kill any stale auto-trader process
pkill -9 -f "icc live" 2>/dev/null || true
sleep 1
rm -f "$PROJECT_DIR/.icc_autotrader.pid"

# 3. Check IB Gateway
if ! pgrep -f JavaApplicationStub > /dev/null 2>&1; then
    log "WARNING: IB Gateway is not running"
fi

# 4. Run auto-trader in FOREGROUND (launchd monitors this process)
cd "$PROJECT_DIR"
source venv/bin/activate
set -a && source .env && set +a

log "Starting auto-trader (foreground) — 7 tickers, ORB, OPTIONS"
exec env PYTHONDONTWRITEBYTECODE=1 icc live --auto \
    --instrument OPTIONS --strategy ORB \
    --tickers SPY,QQQ,NVDA,AMZN,TSLA,META,MSFT \
    >> "$LOG_DIR/icc_auto_${TODAY}.log" 2>&1
