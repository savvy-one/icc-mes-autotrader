#!/bin/bash
# Pre-market cleanup — runs 5 min before start_trading.sh
# Ensures no zombie icc process is holding the IB connection

LOG="$HOME/icc-mes-autotrader/logs/cleanup_$(date +%m%d).log"
log() { echo "$(date '+%Y-%m-%d %H:%M:%S') [CLEANUP] $*" >> "$LOG"; }

log "=== Pre-market cleanup ==="

# Kill any icc process by name
if pgrep -f "icc live" > /dev/null 2>&1; then
    log "Found stale icc process — killing"
    pkill -9 -f "icc live" 2>/dev/null || true
    sleep 2
    log "Done"
else
    log "No stale icc process found"
fi

# Remove stale PID file
rm -f "$HOME/icc-mes-autotrader/.icc_autotrader.pid"

# Remove stale frontend lock
rm -f "$HOME/icc-mes-autotrader/frontend/.next/dev/lock"

# Kill stale frontend
if lsof -i :3000 -t > /dev/null 2>&1; then
    kill $(lsof -i :3000 -t) 2>/dev/null || true
    log "Killed stale frontend on port 3000"
fi

log "Cleanup complete"
