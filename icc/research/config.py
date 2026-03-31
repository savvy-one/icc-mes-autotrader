"""Configuration for the research agent."""

from __future__ import annotations

from pydantic import BaseModel


class ResearchConfig(BaseModel):
    enabled: bool = True
    min_confidence: float = 0.4
    # Calendar
    calendar_file: str = "data/econ_calendar.json"
    # ATR regime
    atr_lookback: int = 100
    atr_extreme_pct: float = 0.90  # above 90th percentile = extreme
    atr_low_pct: float = 0.20      # below 20th percentile = low vol
    # Session phase
    opening_minutes: int = 30
    closing_minutes: int = 30
    # Multipliers
    opening_mult: float = 0.8
    closing_mult: float = 0.7
    low_vol_mult: float = 0.7
    high_vol_mult: float = 0.6
    extreme_vol_mult: float = 0.3
    counter_vwap_mult: float = 0.8
