"""FastAPI web application: routes, WebSocket, session API."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Header, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from jose import JWTError, jwt
from pydantic import BaseModel

from icc.core.events import EventBus
from icc.web.trading_session import TradingSession
from icc.web.ws_manager import ConnectionManager

logger = logging.getLogger(__name__)

app = FastAPI(title="ICC MES AutoTrader", version="0.1.0")

# CORS — allow Next.js frontend (dev + production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://icc-autotrader.onrender.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Auth Configuration ---
_ADMIN_USER = os.environ.get("ICC_ADMIN_USER", "admin")
_ADMIN_PASS = os.environ.get("ICC_ADMIN_PASS", "")
_JWT_SECRET = os.environ.get("ICC_JWT_SECRET", "dev-secret-change-me")
_JWT_ALGORITHM = "HS256"
_JWT_EXPIRE_HOURS = 24


class LoginRequest(BaseModel):
    username: str
    password: str


# Shared state (can be replaced by init_shared_state for CLI auto-mode)
event_bus = EventBus()
ws_manager = ConnectionManager()
session = TradingSession(event_bus)
_scheduler = None  # Optional: set by init_shared_state in auto mode

# Background task for event relay
_relay_task: asyncio.Task | None = None


def init_shared_state(
    shared_event_bus: EventBus,
    shared_session: TradingSession,
    shared_scheduler=None,
) -> None:
    """Replace module-level shared state so CLI auto-mode and web dashboard share instances."""
    global event_bus, session, _scheduler
    event_bus = shared_event_bus
    session = shared_session
    _scheduler = shared_scheduler


async def _event_relay() -> None:
    """Relay events from the sync EventBus to WebSocket clients, feed watchdog."""
    from icc.core.events import EventType

    while True:
        events = event_bus.drain()
        for ev in events:
            await ws_manager.broadcast({
                "type": ev.event_type.value,
                "data": ev.data,
                "ts": ev.timestamp,
            })
            if ev.event_type == EventType.CANDLE:
                session.notify_candle()
        await asyncio.sleep(0.1)


@app.on_event("startup")
async def startup() -> None:
    global _relay_task
    _relay_task = asyncio.create_task(_event_relay())


@app.on_event("shutdown")
async def shutdown() -> None:
    if _relay_task:
        _relay_task.cancel()
    if session.is_running:
        session.stop()


# --- Health Check ---

@app.get("/health")
async def health():
    return {"status": "ok"}


# --- Auth Endpoints ---

@app.post("/api/auth/login")
async def api_auth_login(body: LoginRequest):
    if not _ADMIN_PASS:
        return {"error": "ICC_ADMIN_PASS not configured"}, 500
    if body.username != _ADMIN_USER or body.password != _ADMIN_PASS:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=401, content={"error": "Invalid credentials"})
    expire = datetime.now(timezone.utc) + timedelta(hours=_JWT_EXPIRE_HOURS)
    token = jwt.encode(
        {"sub": body.username, "exp": expire},
        _JWT_SECRET,
        algorithm=_JWT_ALGORITHM,
    )
    return {"token": token, "user": body.username}


@app.get("/api/auth/verify")
async def api_auth_verify(authorization: str = Header(default="")):
    if not authorization.startswith("Bearer "):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=401, content={"valid": False})
    token = authorization[7:]
    try:
        payload = jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGORITHM])
        return {"valid": True, "user": payload.get("sub")}
    except JWTError:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=401, content={"valid": False})


# --- API Endpoints ---

@app.post("/api/session/start")
async def api_start_session():
    try:
        session.start(delay=1.0)
        return {"status": "started"}
    except RuntimeError as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/session/start-live")
async def api_start_live_session(paper: bool = Query(default=True)):
    try:
        session.start_live(paper=paper)
        return {"status": "started", "mode": "paper" if paper else "live"}
    except RuntimeError as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/session/stop")
async def api_stop_session():
    session.stop()
    return {"status": "stopped"}


@app.post("/api/session/kill")
async def api_kill_session():
    session.kill()
    return {"status": "killed"}


@app.get("/api/session/status")
async def api_session_status():
    return {
        "running": session.is_running,
        "snapshot": session.get_snapshot(),
        "ws_clients": ws_manager.client_count,
    }


@app.get("/api/scheduler/status")
async def api_scheduler_status():
    if _scheduler is None:
        return {"enabled": False, "message": "Scheduler not active (use --auto mode)"}
    return {"enabled": True, **_scheduler.get_status()}


@app.get("/api/trades")
async def api_trades(limit: int = Query(default=50, ge=1, le=500)):
    """Return recent trade history from the database."""
    from icc.db.engine import get_session
    from icc.db.models import TradeRecord

    try:
        db = get_session()
        trades = (
            db.query(TradeRecord)
            .order_by(TradeRecord.entry_time.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": t.id,
                "session_id": t.session_id,
                "side": t.side,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "stop_price": t.stop_price,
                "target_price": t.target_price,
                "quantity": t.quantity,
                "pnl": t.pnl,
                "commission": t.commission,
                "entry_time": t.entry_time.isoformat() if t.entry_time else None,
                "exit_time": t.exit_time.isoformat() if t.exit_time else None,
                "exit_reason": t.exit_reason,
            }
            for t in trades
        ]
    except Exception as e:
        logger.warning("Failed to fetch trades: %s", e)
        return []
    finally:
        db.close()


@app.get("/api/config")
async def api_config():
    """Return merged application configuration as JSON."""
    from icc.config import load_config

    config = load_config("paper")
    dump = config.model_dump()
    # Strip sensitive broker fields
    dump.get("broker", {}).pop("api_key", None)
    dump.get("alerts", {}).pop("smtp_pass", None)
    return dump


# --- WebSocket ---

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        # Send initial snapshot
        await websocket.send_json({
            "type": "snapshot",
            "data": session.get_snapshot(),
        })
        # Keep connection alive, listen for client messages
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong"})
            elif data == "snapshot":
                await websocket.send_json({
                    "type": "snapshot",
                    "data": session.get_snapshot(),
                })
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)
