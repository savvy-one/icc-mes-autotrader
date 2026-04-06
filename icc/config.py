"""Configuration management: Pydantic Settings + YAML merge."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from icc.constants import (
    ATR_PERIOD,
    COMMISSION_PER_SIDE,
    COOLDOWN_SECONDS,
    CORRECTION_MAX_BARS,
    DAILY_LOSS_KILL_PCT,
    DAILY_LOSS_PREKILL_PCT,
    DEFAULT_ACCOUNT_SIZE,
    EMA_PERIOD,
    Environment,
    FIB_RETRACEMENT_MAX,
    FIB_RETRACEMENT_MIN,
    MAX_CONSECUTIVE_LOSSES,
    MAX_OPEN_POSITIONS,
    MAX_TRADES_PER_SESSION,
    SLIPPAGE_TICKS,
    STOP_ATR_MULTIPLIER,
    TARGET_ATR_MULTIPLIER,
    TRADE_TIMEOUT_BARS,
    VOLUME_AVG_PERIOD,
    CONTINUATION_VOLUME_PERIOD,
)

CONFIGS_DIR = Path(__file__).resolve().parent.parent / "configs"


class StrategyConfig(BaseModel):
    ema_period: int = EMA_PERIOD
    atr_period: int = ATR_PERIOD
    volume_avg_period: int = VOLUME_AVG_PERIOD
    continuation_volume_period: int = CONTINUATION_VOLUME_PERIOD
    fib_min: float = FIB_RETRACEMENT_MIN
    fib_max: float = FIB_RETRACEMENT_MAX
    indication_max_bars: int = 20
    correction_max_bars: int = CORRECTION_MAX_BARS
    stop_atr_mult: float = STOP_ATR_MULTIPLIER
    target_atr_mult: float = TARGET_ATR_MULTIPLIER
    trade_timeout_bars: int = TRADE_TIMEOUT_BARS
    min_atr_pct: float = 0.05
    trailing_stop_enabled: bool = True
    breakeven_atr_mult: float = 1.0
    trail_atr_mult: float = 1.0


class RiskConfig(BaseModel):
    account_size: float = DEFAULT_ACCOUNT_SIZE
    daily_loss_kill_pct: float = DAILY_LOSS_KILL_PCT
    daily_loss_prekill_pct: float = DAILY_LOSS_PREKILL_PCT
    max_trades_per_session: int = MAX_TRADES_PER_SESSION
    max_open_positions: int = MAX_OPEN_POSITIONS
    cooldown_seconds: int = COOLDOWN_SECONDS
    max_consecutive_losses: int = MAX_CONSECUTIVE_LOSSES
    commission_per_side: float = COMMISSION_PER_SIDE
    slippage_ticks: int = SLIPPAGE_TICKS
    large_loss_threshold: float = 100.0  # Dollar amount that counts as a "large loss"
    large_loss_cooldown_seconds: int = 600  # 10-minute cooldown after large loss


class BrokerConfig(BaseModel):
    api_key: str = ""
    account_id: str = ""
    base_url: str = ""


class IBConfig(BaseModel):
    socket_port: int = 7497  # 7497=paper, 7496=live
    client_id: str = "100"
    ip: str = "127.0.0.1"


class SettlementConfig(BaseModel):
    enabled: bool = True
    safety_buffer: float = 10.0
    tranches: list[dict] = Field(default_factory=lambda: [
        {"name": "morning", "start_hour": 9, "start_minute": 30, "budget": 1250.0},
        {"name": "afternoon", "start_hour": 13, "start_minute": 0, "budget": 1250.0},
    ])
    max_trades_per_tranche: int = 4


class ResearchConfig(BaseModel):
    enabled: bool = True
    min_confidence: float = 0.4
    calendar_file: str = "data/econ_calendar.json"
    atr_lookback: int = 100
    atr_extreme_pct: float = 0.90
    atr_low_pct: float = 0.20
    opening_minutes: int = 30
    closing_minutes: int = 30
    opening_mult: float = 0.8
    closing_mult: float = 0.7
    low_vol_mult: float = 0.7
    high_vol_mult: float = 0.6
    extreme_vol_mult: float = 0.3
    counter_vwap_mult: float = 0.8


class OptionsConfig(BaseModel):
    instrument_type: str = "FUTURES"  # FUTURES or OPTIONS
    underlying: str = "MES"  # MES or SPX
    tickers: list[str] = Field(default_factory=lambda: ["SPY", "QQQ", "NVDA", "AMZN", "TSLA", "META", "MSFT"])
    strike_mode: str = "ATM"  # ATM, OTM_1, DELTA
    expiration_mode: str = "MONTHLY"  # ZERO_DTE, WEEKLY, MONTHLY
    premium_stop_pct: float = 0.30  # 30% — tighter stop to cut losers faster
    premium_trail_trigger_pct: float = 0.15  # Activate trail stop after 15% gain
    premium_trail_drop_pct: float = 0.15  # Exit when premium drops 15% from peak
    put_confidence_boost: float = 0.30  # Extra confidence required for PUT entries vs CALLs
    min_premium: float = 0.75  # Reject contracts < $0.75 (need margin for commission + movement)
    expiration_guard_minutes: int = 15
    quantity: int = 1
    option_commission_per_side: float = 1.50
    cash_settled_underlyings: list[str] = ["SPX"]  # No T+1 delay for these
    max_premium: float = 1.50  # Reject contracts with premium > $1.50 (caps per-trade risk)
    otm_fallback: bool = True  # If ATM premium > max_premium, try OTM_1 strike


class ORBConfig(BaseModel):
    range_minutes: int = 15
    target_multiplier: float = 1.5
    stop_mode: str = "opposite"  # "opposite" or "midpoint"
    min_range_pct: float = 0.3  # min range height as % of price (0.3% = $1.97 on SPY ~$655)
    confirmation_bars: int = 2  # require N consecutive closes beyond range before entering
    volume_confirmation: bool = False
    volume_threshold_pct: float = 120.0
    max_wait_minutes: int = 120  # Extended from 60 — some breakouts take longer
    reentry_allowed: bool = True
    re_range_on_expiry: bool = True  # Build new range if first one expires without breakout
    max_ranges_per_session: int = 3  # Cap re-ranges to avoid endless cycling
    trade_timeout_bars: int = 90  # longer than ICC's 25 — ORB targets are wider
    min_atr_pct: float = 0.05  # percentage of price (0.05% = works across all price levels)
    trailing_stop_enabled: bool = True
    breakeven_range_pct: float = 0.5
    trail_range_pct: float = 0.5


class AlertConfig(BaseModel):
    console_enabled: bool = True
    email_enabled: bool = False
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    email_to: str = ""


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ICC_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Environment = Environment.BACKTEST
    db_url: str = "sqlite:///icc_trades.db"
    log_level: str = "INFO"
    log_dir: str = "logs"

    strategy_name: str = "ICC"  # "ICC" or "ORB"

    strategy: StrategyConfig = Field(default_factory=StrategyConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    broker: BrokerConfig = Field(default_factory=BrokerConfig)
    alerts: AlertConfig = Field(default_factory=AlertConfig)
    ib: IBConfig = Field(default_factory=IBConfig)
    settlement: SettlementConfig = Field(default_factory=SettlementConfig)
    research: ResearchConfig = Field(default_factory=ResearchConfig)
    options: OptionsConfig = Field(default_factory=OptionsConfig)
    orb: ORBConfig = Field(default_factory=ORBConfig)


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base."""
    merged = base.copy()
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def load_config(env: Optional[str] = None) -> AppSettings:
    """Load config by merging: defaults < strategy_default.yaml < risk_default.yaml < options_default.yaml < environment yaml."""
    strategy_yaml = _load_yaml(CONFIGS_DIR / "strategy_default.yaml")
    risk_yaml = _load_yaml(CONFIGS_DIR / "risk_default.yaml")
    options_yaml = _load_yaml(CONFIGS_DIR / "options_default.yaml")
    orb_yaml = _load_yaml(CONFIGS_DIR / "orb_default.yaml")

    merged: dict = {}
    if strategy_yaml:
        merged = _deep_merge(merged, {"strategy": strategy_yaml})
    if risk_yaml:
        merged = _deep_merge(merged, {"risk": risk_yaml})
    if options_yaml:
        merged = _deep_merge(merged, {"options": options_yaml})
    if orb_yaml:
        merged = _deep_merge(merged, {"orb": orb_yaml})

    settings = AppSettings()
    target_env = env or settings.env.value

    env_yaml = _load_yaml(CONFIGS_DIR / "environments" / f"{target_env}.yaml")
    if env_yaml:
        merged = _deep_merge(merged, env_yaml)

    if merged:
        settings = AppSettings(**merged)

    if env:
        settings.env = Environment(env)

    return settings
