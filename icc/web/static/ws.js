// ICC MES AutoTrader — WebSocket client + DOM updates

let ws = null;
let reconnectTimer = null;
const MAX_ALERTS = 200;
let tradeCounter = 0;

function connectWS() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    ws = new WebSocket(`${proto}//${location.host}/ws`);

    ws.onopen = () => {
        setWSStatus(true);
        if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
    };

    ws.onclose = () => {
        setWSStatus(false);
        reconnectTimer = setTimeout(connectWS, 3000);
    };

    ws.onerror = () => { ws.close(); };

    ws.onmessage = (evt) => {
        const msg = JSON.parse(evt.data);
        handleEvent(msg);
    };
}

function setWSStatus(connected) {
    const dot = document.getElementById("ws-status");
    const label = document.getElementById("ws-label");
    if (!dot || !label) return;
    if (connected) {
        dot.className = "status-dot connected";
        label.textContent = "Connected";
    } else {
        dot.className = "status-dot disconnected";
        label.textContent = "Disconnected";
    }
}

function handleEvent(msg) {
    const type = msg.type;
    const data = msg.data || {};

    // Add to event log
    addAlertLine(type, data);

    switch (type) {
        case "snapshot":
            updateSnapshot(data);
            break;
        case "candle":
            updateCandle(data);
            break;
        case "entry":
            updateEntry(data);
            break;
        case "exit":
            updateExit(data);
            break;
        case "fsm_transition":
            updateFSM(data);
            break;
        case "kill_switch":
            updateKillSwitch(data);
            break;
        case "session_started":
            setSessionStatus("running");
            break;
        case "session_stopped":
            setSessionStatus("stopped");
            break;
    }
}

function updateSnapshot(s) {
    setText("fsm-state", s.fsm_state || "FLAT");
    setText("candle-count", s.candle_count || 0);
    setText("trade-count", s.trade_count || 0);
    updatePnL(s.daily_pnl || 0);

    if (s.position) {
        const p = s.position;
        const el = document.getElementById("position-info");
        if (el) {
            el.textContent = `${p.side} @ ${p.entry_price.toFixed(2)}`;
            el.className = p.side === "BUY" ? "position-long" : "position-short";
        }
        setText("pos-entry", p.entry_price.toFixed(2));
        setText("pos-stop", p.stop_price.toFixed(2));
        setText("pos-target", p.target_price.toFixed(2));
        setText("pos-upnl", `$${p.unrealized_pnl.toFixed(2)}`);
    } else {
        const el = document.getElementById("position-info");
        if (el) { el.textContent = "FLAT"; el.className = "position-flat"; }
        setText("pos-entry", "—");
        setText("pos-stop", "—");
        setText("pos-target", "—");
        setText("pos-upnl", "$0.00");
    }

    if (s.last_candle) {
        updateCandle(s.last_candle);
    }

    if (s.session_running) {
        setSessionStatus("running");
        if (s.mode) setMode(s.mode.toUpperCase());
    }
}

function updateCandle(c) {
    setText("candle-time", c.timestamp || "—");
    setText("candle-open", num(c.open));
    setText("candle-high", num(c.high));
    setText("candle-low", num(c.low));
    setText("candle-close", num(c.close));
    setText("candle-vol", c.volume || "—");

    // Increment candle count
    const el = document.getElementById("candle-count");
    if (el) {
        const n = parseInt(el.textContent || "0") + 1;
        el.textContent = n;
    }
}

function updateEntry(data) {
    const el = document.getElementById("position-info");
    if (el) {
        el.textContent = `${data.side} @ ${data.entry_price.toFixed(2)}`;
        el.className = data.side === "BUY" ? "position-long" : "position-short";
    }
    setText("pos-entry", num(data.entry_price));
    setText("pos-stop", num(data.stop_price));
    setText("pos-target", num(data.target_price));
}

function updateExit(data) {
    const el = document.getElementById("position-info");
    if (el) { el.textContent = "FLAT"; el.className = "position-flat"; }
    setText("pos-entry", "—");
    setText("pos-stop", "—");
    setText("pos-target", "—");
    setText("pos-upnl", "$0.00");
    updatePnL(data.daily_pnl || 0);

    // Add to trades table
    addTradeRow(data);
}

function updateFSM(data) {
    setText("fsm-state", data.state || "FLAT");
}

function updateKillSwitch(data) {
    setSessionStatus("stopped");
    updatePnL(data.daily_pnl || 0);
}

function updatePnL(val) {
    const el = document.getElementById("daily-pnl");
    if (!el) return;
    el.textContent = `$${val.toFixed(2)}`;
    if (val > 0) el.className = "big-text pnl-positive";
    else if (val < 0) el.className = "big-text pnl-negative";
    else el.className = "big-text pnl-zero";
}

function setSessionStatus(status) {
    const badge = document.getElementById("session-status");
    const btnStart = document.getElementById("btn-start");
    const btnStartLive = document.getElementById("btn-start-live");
    const btnStop = document.getElementById("btn-stop");
    if (!badge) return;

    badge.textContent = status.toUpperCase();
    badge.className = `session-badge ${status}`;

    const isRunning = (status === "running");
    if (btnStart) btnStart.disabled = isRunning;
    if (btnStartLive) btnStartLive.disabled = isRunning;
    if (btnStop) btnStop.disabled = !isRunning;

    if (!isRunning) setMode("");
}

function setMode(mode) {
    const el = document.getElementById("session-mode");
    if (!el) return;
    if (!mode) { el.style.display = "none"; return; }
    el.textContent = mode;
    el.style.display = "inline";
    el.style.background = (mode === "LIVE") ? "#ff3300" : "#0077cc";
    el.style.color = "#fff";
    el.style.padding = "2px 8px";
    el.style.borderRadius = "4px";
    el.style.fontWeight = "bold";
}

function addAlertLine(type, data) {
    const feed = document.getElementById("alerts-feed");
    if (!feed) return;

    const line = document.createElement("div");
    line.className = "alert-line";

    const ts = new Date().toLocaleTimeString();
    let detail = "";
    if (type === "candle") detail = `C=${num(data.close)} V=${data.volume}`;
    else if (type === "entry") detail = `${data.side} @ ${num(data.entry_price)}`;
    else if (type === "exit") detail = `${data.reason} PnL=$${(data.pnl || 0).toFixed(2)}`;
    else if (type === "fsm_transition") detail = data.state || "";
    else if (type === "alert") detail = `[${data.alert_type}] ${data.message}`;
    else if (type === "kill_switch") detail = `Daily PnL: $${(data.daily_pnl || 0).toFixed(2)}`;
    else detail = JSON.stringify(data).slice(0, 80);

    line.innerHTML = `<span class="ts">${ts}</span><span class="type type-${type}">${type}</span> ${detail}`;
    feed.prepend(line);

    // Trim old lines
    while (feed.children.length > MAX_ALERTS) {
        feed.removeChild(feed.lastChild);
    }
}

function addTradeRow(data) {
    const tbody = document.getElementById("trades-body");
    if (!tbody) return;

    // Remove placeholder
    if (tbody.children.length === 1 && tbody.children[0].querySelector(".dim")) {
        tbody.innerHTML = "";
    }

    tradeCounter++;
    const row = document.createElement("tr");
    const pnl = (data.pnl || 0).toFixed(2);
    const pnlClass = data.pnl >= 0 ? "pnl-positive" : "pnl-negative";
    row.innerHTML = `
        <td>${tradeCounter}</td>
        <td>${data.side || "—"}</td>
        <td>${num(data.entry_price)}</td>
        <td>${num(data.exit_price)}</td>
        <td class="${pnlClass}">$${pnl}</td>
        <td>${data.reason || "—"}</td>
    `;
    tbody.prepend(row);
}

// Session controls
async function startSession() {
    const res = await fetch("/api/session/start", { method: "POST" });
    const j = await res.json();
    if (j.status === "started") { setSessionStatus("running"); setMode("SIMULATED"); }
    else alert(j.message || "Failed to start");
}

async function startLiveSession() {
    if (!confirm("START LIVE TRADING on Interactive Brokers?\n\nThis will place REAL orders. Make sure TWS/IB Gateway is running.")) return;
    const res = await fetch("/api/session/start-live", { method: "POST" });
    const j = await res.json();
    if (j.status === "started") { setSessionStatus("running"); setMode("LIVE"); }
    else alert(j.message || "Failed to start live session");
}

async function stopSession() {
    await fetch("/api/session/stop", { method: "POST" });
    setSessionStatus("stopped");
}

async function killSession() {
    if (!confirm("KILL SWITCH: Stop all trading immediately?")) return;
    await fetch("/api/session/kill", { method: "POST" });
    setSessionStatus("stopped");
}

// Helpers
function setText(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
}

function num(v) {
    if (v == null) return "—";
    return typeof v === "number" ? v.toFixed(2) : v;
}

// Auto-connect on page load
document.addEventListener("DOMContentLoaded", connectWS);
