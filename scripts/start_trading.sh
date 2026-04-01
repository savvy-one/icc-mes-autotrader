#!/bin/bash
# ICC AutoTrader — pre-market startup script
# Launched by launchd at 6:20 AM PT (9:20 AM ET) on weekdays
# Starts caffeinate, backend auto-trader, and frontend dashboard

set -euo pipefail

PROJECT_DIR="$HOME/icc-mes-autotrader"
LOG_DIR="$PROJECT_DIR/logs"
TODAY=$(date +%m%d)
LOG_FILE="$LOG_DIR/icc_auto_${TODAY}.log"
STARTUP_LOG="$LOG_DIR/startup_${TODAY}.log"

mkdir -p "$LOG_DIR"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') [STARTUP] $*" >> "$STARTUP_LOG"; }

log "=== ICC AutoTrader startup ==="

# 1. Check if IB Gateway is running
if ! pgrep -f JavaApplicationStub > /dev/null 2>&1; then
    log "WARNING: IB Gateway is not running — auto-trader will fail to connect"
    # Still continue — IB Gateway might start before 9:30
fi

# 2. Prevent Mac sleep
if ! pgrep caffeinate > /dev/null 2>&1; then
    caffeinate -dims &
    log "Started caffeinate (PID $!)"
else
    log "Caffeinate already running"
fi

# 3. Kill any stale auto-trader process
if [ -f "$PROJECT_DIR/.icc_autotrader.pid" ]; then
    OLD_PID=$(cat "$PROJECT_DIR/.icc_autotrader.pid")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        log "Killing stale auto-trader PID $OLD_PID"
        kill "$OLD_PID" 2>/dev/null || true
        sleep 2
        # Force kill if still alive (zombie/hung process)
        if kill -0 "$OLD_PID" 2>/dev/null; then
            log "Force killing PID $OLD_PID (SIGKILL)"
            kill -9 "$OLD_PID" 2>/dev/null || true
            sleep 1
        fi
    fi
    rm -f "$PROJECT_DIR/.icc_autotrader.pid"
fi
# Also kill any icc process by name (catches processes without PID file)
pkill -f "icc live" 2>/dev/null || true
sleep 1

# 4. Start backend auto-trader
cd "$PROJECT_DIR"
source venv/bin/activate
set -a && source .env && set +a

PYTHONDONTWRITEBYTECODE=1 nohup icc live --auto \
    --instrument OPTIONS --strategy ORB \
    --tickers SPY,QQQ,NVDA,AMZN,TSLA,META,MSFT \
    >> "$LOG_FILE" 2>&1 &

BACKEND_PID=$!
log "Started backend auto-trader (PID $BACKEND_PID) — log: $LOG_FILE"

# 5. Kill stale frontend / lock files
if lsof -i :3000 -t > /dev/null 2>&1; then
    kill $(lsof -i :3000 -t) 2>/dev/null || true
    sleep 1
fi
rm -f "$PROJECT_DIR/frontend/.next/dev/lock"

# 6. Start frontend dashboard
cd "$PROJECT_DIR/frontend"
nohup npm run dev >> "$LOG_DIR/frontend_${TODAY}.log" 2>&1 &
FRONTEND_PID=$!
log "Started frontend dashboard (PID $FRONTEND_PID) on http://localhost:3000"

log "Startup complete — backend PID $BACKEND_PID, frontend PID $FRONTEND_PID"
