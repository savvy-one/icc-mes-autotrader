"""Generate MES data with more pronounced trends to test full ICC pipeline.

This simulates sessions with clear trending periods (as seen in real MES
during news-driven or momentum sessions), interspersed with range periods.
"""

import csv
import random
import math
from datetime import datetime, timedelta

random.seed(123)

MES_TICK = 0.25

def snap(price):
    return round(round(price / MES_TICK) * MES_TICK, 2)

def generate_trending_session(date, start_price, trend_strength=1.0):
    """Generate a session with pronounced trending moves."""
    candles = []
    price = start_price
    t = date.replace(hour=9, minute=30, second=0)
    
    # Session plan: [phase_type, bars, direction, strength]
    phases = []
    remaining = 78
    
    while remaining > 0:
        phase_type = random.choices(
            ["strong_trend", "mild_trend", "range", "impulse_retrace_continue"],
            weights=[15, 20, 30, 35],
            k=1
        )[0]
        
        if phase_type == "impulse_retrace_continue":
            # This is the ICC pattern: impulse -> retrace -> continue
            impulse_bars = random.randint(3, 6)
            retrace_bars = random.randint(3, 6)
            continue_bars = random.randint(3, 6)
            total = impulse_bars + retrace_bars + continue_bars
            if total > remaining:
                phase_type = "range"
            else:
                direction = random.choice([-1, 1])
                phases.append(("impulse", impulse_bars, direction, random.uniform(1.5, 3.5)))
                phases.append(("retrace", retrace_bars, -direction, random.uniform(0.3, 0.7)))
                phases.append(("continue", continue_bars, direction, random.uniform(1.5, 3.0)))
                remaining -= total
                continue
        
        if phase_type == "strong_trend":
            bars = min(random.randint(5, 12), remaining)
            direction = random.choice([-1, 1])
            phases.append(("strong_trend", bars, direction, random.uniform(1.5, 3.0)))
            remaining -= bars
        elif phase_type == "mild_trend":
            bars = min(random.randint(4, 8), remaining)
            direction = random.choice([-1, 1])
            phases.append(("mild_trend", bars, direction, random.uniform(0.5, 1.2)))
            remaining -= bars
        else:
            bars = min(random.randint(3, 10), remaining)
            phases.append(("range", bars, 0, random.uniform(0.3, 0.8)))
            remaining -= bars
    
    bar_idx = 0
    for phase_type, bars, direction, strength in phases:
        for b in range(bars):
            # Volume: higher for impulse/continue, lower for retrace/range
            if phase_type in ("impulse", "continue", "strong_trend"):
                vol = random.randint(1500, 4000)
            elif phase_type == "retrace":
                vol = random.randint(400, 1200)
            else:
                vol = random.randint(600, 2000)
            
            if phase_type == "impulse":
                move = direction * strength * random.uniform(0.7, 1.5)
            elif phase_type == "retrace":
                # Key: retrace should be 38-62% of impulse, with lower volume
                move = direction * strength * random.uniform(0.4, 1.0)
            elif phase_type == "continue":
                move = direction * strength * random.uniform(0.8, 1.6)
            elif phase_type == "strong_trend":
                move = direction * strength * random.uniform(0.5, 1.3)
            elif phase_type == "mild_trend":
                move = direction * strength * random.uniform(0.3, 0.8)
            else:
                move = random.gauss(0, strength)
            
            o = snap(price)
            c = snap(price + move)
            body_hi = max(o, c)
            body_lo = min(o, c)
            h = snap(body_hi + random.uniform(0, 1.5))
            l = snap(body_lo - random.uniform(0, 1.5))
            
            candles.append({
                "timestamp": (t + timedelta(minutes=bar_idx * 5)).strftime("%Y-%m-%d %H:%M:%S"),
                "open": f"{o:.2f}",
                "high": f"{h:.2f}",
                "low": f"{l:.2f}",
                "close": f"{c:.2f}",
                "volume": str(vol),
            })
            price = float(c)
            bar_idx += 1
    
    return candles, price

# Generate 60 sessions
all_candles = []
price = 5200.00
current = datetime(2025, 12, 1)
sessions = 0

while sessions < 60:
    if current.weekday() >= 5:
        current += timedelta(days=1)
        continue
    
    session_candles, price = generate_trending_session(current, price)
    all_candles.extend(session_candles)
    
    # Overnight gap
    price = snap(price + random.gauss(0, 2.5))
    sessions += 1
    current += timedelta(days=1)

path = "/Users/savvybusinessaccelerator/icc-mes-autotrader/data/mes_5min_trending.csv"
with open(path, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["timestamp", "open", "high", "low", "close", "volume"])
    writer.writeheader()
    writer.writerows(all_candles)

print(f"Generated {len(all_candles)} candles -> {path}")
