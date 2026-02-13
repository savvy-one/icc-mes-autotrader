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
    correction_max_bars: int = CORRECTION_MAX_BARS
    stop_atr_mult: float = STOP_ATR_MULTIPLIER
    target_atr_mult: float = TARGET_ATR_MULTIPLIER
    trade_timeout_bars: int = TRADE_TIMEOUT_BARS


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


class BrokerConfig(BaseModel):
    api_key: str = ""
    account_id: str = ""
    base_url: str = ""


class IBConfig(BaseModel):
    socket_port: int = 7497  # 7497=paper, 7496=live
    client_id: str = "100"
    ip: str = "127.0.0.1"


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

    strategy: StrategyConfig = Field(default_factory=StrategyConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    broker: BrokerConfig = Field(default_factory=BrokerConfig)
    alerts: AlertConfig = Field(default_factory=AlertConfig)
    ib: IBConfig = Field(default_factory=IBConfig)


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
    """Load config by merging: defaults < strategy_default.yaml < risk_default.yaml < environment yaml."""
    strategy_yaml = _load_yaml(CONFIGS_DIR / "strategy_default.yaml")
    risk_yaml = _load_yaml(CONFIGS_DIR / "risk_default.yaml")

    merged: dict = {}
    if strategy_yaml:
        merged = _deep_merge(merged, {"strategy": strategy_yaml})
    if risk_yaml:
        merged = _deep_merge(merged, {"risk": risk_yaml})

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
