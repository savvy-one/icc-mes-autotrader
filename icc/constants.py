"""Enumerations and constants for ICC MES AutoTrader."""

from enum import Enum, auto


class FSMState(str, Enum):
    FLAT = "FLAT"
    INDICATION_UP = "INDICATION_UP"
    INDICATION_DOWN = "INDICATION_DOWN"
    CORRECTION_UP = "CORRECTION_UP"
    CORRECTION_DOWN = "CORRECTION_DOWN"
    CONTINUATION_UP = "CONTINUATION_UP"
    CONTINUATION_DOWN = "CONTINUATION_DOWN"
    IN_TRADE_UP = "IN_TRADE_UP"
    IN_TRADE_DOWN = "IN_TRADE_DOWN"
    EXIT = "EXIT"
    RISK_BLOCKED = "RISK_BLOCKED"
    ORB_BUILDING = "ORB_BUILDING"
    ORB_ARMED = "ORB_ARMED"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class Environment(str, Enum):
    BACKTEST = "backtest"
    PAPER = "paper"
    LIVE = "live"


class InstrumentType(str, Enum):
    FUTURES = "FUTURES"
    OPTIONS = "OPTIONS"


class OptionRight(str, Enum):
    CALL = "CALL"
    PUT = "PUT"


class StrikeMode(str, Enum):
    ATM = "ATM"
    OTM_1 = "OTM_1"
    DELTA = "DELTA"


class ExpirationMode(str, Enum):
    ZERO_DTE = "ZERO_DTE"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"


# Option contract specs per underlying
OPTION_SPECS = {
    "MES": {"multiplier": 5.0, "strike_increment": 5.0, "exchange": "CME"},
    "SPX": {"multiplier": 100.0, "strike_increment": 5.0, "exchange": "CBOE"},
}

DEFAULT_PREMIUM_STOP_PCT = 0.50
EXPIRATION_GUARD_MINUTES = 15


# MES contract specifications
MES_TICK_SIZE = 0.25
MES_TICK_VALUE = 1.25
MES_POINT_VALUE = 5.0

# Risk defaults
DEFAULT_ACCOUNT_SIZE = 389.0
DAILY_LOSS_KILL_PCT = 0.20
DAILY_LOSS_PREKILL_PCT = 0.18
MAX_TRADES_PER_SESSION = 8
MAX_OPEN_POSITIONS = 1
COOLDOWN_SECONDS = 600
MAX_CONSECUTIVE_LOSSES = 2
COMMISSION_PER_SIDE = 2.50
SLIPPAGE_TICKS = 1

# Strategy defaults
EMA_PERIOD = 20
ATR_PERIOD = 14
VOLUME_AVG_PERIOD = 20
CONTINUATION_VOLUME_PERIOD = 15
FIB_RETRACEMENT_MIN = 0.382
FIB_RETRACEMENT_MAX = 0.618
CORRECTION_MAX_BARS = 20
STOP_ATR_MULTIPLIER = 1.5
TARGET_ATR_MULTIPLIER = 2.0
TRADE_TIMEOUT_BARS = 25

# Session window (ET)
SESSION_START_HOUR = 9
SESSION_START_MINUTE = 30
SESSION_END_HOUR = 15
SESSION_END_MINUTE = 45
