"""Generate realistic MES 5-minute candle data for backtesting.

Creates data that includes both trending and ranging periods,
with realistic MES price ranges, volume profiles, and tick increments.
MES tick size = 0.25, typical 5-min range = 1-5 points.
"""

import csv
import random
import math
from datetime import datetime, timedelta

random.seed(42)  # reproducible

MES_TICK = 0.25

def snap_to_tick(price: float) -> float:
    """Snap price to nearest MES tick."""
    return round(round(price / MES_TICK) * MES_TICK, 2)

def generate_session_candles(session_date: datetime, start_price: float) -> list[dict]:
    """Generate 5-min candles for one trading session (9:30 - 16:00 ET = 78 bars)."""
    candles = []
    price = start_price
    session_start = session_date.replace(hour=9, minute=30, second=0)
    
    # Session characteristics
    trend_bias = random.choice([-1, 0, 0, 1])  # slight directional bias
    volatility = random.uniform(0.5, 2.5)  # session volatility factor
    
    # Volume profile: higher at open/close, lower midday
    def volume_profile(bar_idx: int, total_bars: int) -> int:
        # U-shaped volume profile
        x = bar_idx / total_bars
        base_vol = 500 + int(2000 * (4 * (x - 0.5)**2 + 0.2))
        noise = random.randint(-200, 400)
        return max(100, base_vol + noise)
    
    total_bars = 78  # 9:30 to 16:00 = 6.5 hours = 78 five-min bars
    
    # Create a few "impulse" periods within the session (for ICC patterns)
    impulse_starts = sorted(random.sample(range(5, 65), k=random.randint(2, 5)))
    impulse_lengths = [random.randint(3, 8) for _ in impulse_starts]
    impulse_dirs = [random.choice([-1, 1]) for _ in impulse_starts]
    
    in_impulse = False
    impulse_idx = 0
    impulse_remaining = 0
    impulse_dir = 0
    
    # Correction after impulse
    in_correction = False
    correction_remaining = 0
    correction_dir = 0
    
    for bar in range(total_bars):
        ts = session_start + timedelta(minutes=bar * 5)
        vol = volume_profile(bar, total_bars)
        
        # Check if we're starting an impulse
        if impulse_idx < len(impulse_starts) and bar == impulse_starts[impulse_idx]:
            in_impulse = True
            impulse_remaining = impulse_lengths[impulse_idx]
            impulse_dir = impulse_dirs[impulse_idx]
            impulse_idx += 1
        
        if in_impulse and impulse_remaining > 0:
            # Strong directional move
            move = impulse_dir * random.uniform(0.75, 2.5) * volatility
            vol = int(vol * random.uniform(1.3, 2.0))  # Higher volume
            impulse_remaining -= 1
            if impulse_remaining == 0:
                in_impulse = False
                # Sometimes follow with correction
                if random.random() < 0.7:
                    in_correction = True
                    correction_remaining = random.randint(3, 8)
                    correction_dir = -impulse_dir  # opposite direction
        elif in_correction and correction_remaining > 0:
            # Weaker counter-move (retracement)
            move = correction_dir * random.uniform(0.25, 1.0) * volatility * 0.5
            vol = int(vol * random.uniform(0.5, 0.8))  # Lower volume
            correction_remaining -= 1
            if correction_remaining == 0:
                in_correction = False
        else:
            # Random walk
            move = random.gauss(trend_bias * 0.05, 0.6 * volatility)
        
        open_price = snap_to_tick(price)
        close_price = snap_to_tick(price + move)
        
        # Generate high/low from OHLC logic
        body_high = max(open_price, close_price)
        body_low = min(open_price, close_price)
        wick_up = snap_to_tick(random.uniform(0, 1.5 * volatility))
        wick_down = snap_to_tick(random.uniform(0, 1.5 * volatility))
        
        high = body_high + wick_up
        low = body_low - wick_down
        
        candles.append({
            "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
            "open": f"{open_price:.2f}",
            "high": f"{high:.2f}",
            "low": f"{low:.2f}",
            "close": f"{close_price:.2f}",
            "volume": str(max(100, vol)),
        })
        
        price = float(close_price)
    
    return candles, price

def generate_data(output_path: str, num_sessions: int = 60):
    """Generate multi-session MES data."""
    all_candles = []
    price = 5200.00  # Starting MES price ~5200
    
    # Generate weekday sessions
    current_date = datetime(2025, 12, 1)
    sessions = 0
    
    while sessions < num_sessions:
        # Skip weekends
        if current_date.weekday() >= 5:
            current_date += timedelta(days=1)
            continue
        
        session_candles, closing_price = generate_session_candles(current_date, price)
        all_candles.extend(session_candles)
        
        # Overnight gap
        gap = random.gauss(0, 3.0)
        price = snap_to_tick(closing_price + gap)
        
        sessions += 1
        current_date += timedelta(days=1)
    
    # Write CSV
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["timestamp", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        writer.writerows(all_candles)
    
    return len(all_candles)

if __name__ == "__main__":
    path = "/Users/savvybusinessaccelerator/icc-mes-autotrader/data/mes_5min_backtest.csv"
    import os
    os.makedirs(os.path.dirname(path), exist_ok=True)
    count = generate_data(path, num_sessions=60)
    print(f"Generated {count} candles across 60 sessions -> {path}")
