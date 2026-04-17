"""OptionChainResolver — resolves option contracts from IB via Lumibot."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Protocol, runtime_checkable

import pytz

logger = logging.getLogger(__name__)

_ET = pytz.timezone("US/Eastern")

# Cache yfinance Ticker to avoid repeated instantiation
_yf_ticker_cache: dict[str, object] = {}


def _yf_get_ticker(symbol: str):
    """Get or create a cached yfinance Ticker."""
    if symbol not in _yf_ticker_cache:
        import yfinance as yf
        _yf_ticker_cache[symbol] = yf.Ticker(symbol)
    return _yf_ticker_cache[symbol]


def _yf_get_price(symbol: str) -> float | None:
    """Get current price from Yahoo Finance."""
    try:
        ticker = _yf_get_ticker(symbol)
        info = ticker.fast_info
        price = getattr(info, 'last_price', None)
        if price is not None:
            return float(price)
        # Fallback to previous close
        price = getattr(info, 'previous_close', None)
        if price is not None:
            return float(price)
    except Exception as e:
        logger.debug("yfinance price failed for %s: %s", symbol, e)
    return None


def _yf_get_option_premium(symbol: str, expiration: date, strike: float,
                            option_type: str) -> float | None:
    """Get option premium from Yahoo Finance."""
    try:
        ticker = _yf_get_ticker(symbol)
        exp_str = expiration.strftime("%Y-%m-%d")
        chain = ticker.option_chain(exp_str)
        if option_type.upper() == "CALL":
            df = chain.calls
        else:
            df = chain.puts
        row = df.loc[df["strike"] == strike]
        if not row.empty:
            ask = float(row.iloc[0]["ask"])
            last = float(row.iloc[0]["lastPrice"])
            return ask if ask > 0 else last
    except Exception as e:
        logger.debug("yfinance option premium failed: %s", e)
    return None


@dataclass(frozen=True)
class OptionContract:
    """Resolved option contract ready for order submission."""

    underlying: str       # "MES" or "SPX"
    option_type: str      # "CALL" or "PUT"
    strike: float
    expiration: date
    premium: float        # Ask price (cost to buy)
    multiplier: float     # 5.0 for MES, 100.0 for SPX
    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0
    implied_vol: float = 0.0

    @property
    def total_cost(self) -> float:
        """Total debit to open one contract (excluding commission)."""
        return self.premium * self.multiplier

    @property
    def symbol(self) -> str:
        """Descriptive symbol string for logging / DB."""
        exp_str = self.expiration.strftime("%y%m%d")
        return f"{self.underlying}{exp_str}{self.option_type[0]}{self.strike:.0f}"


# ---------------------------------------------------------------------------
# Provider protocol + implementations
# ---------------------------------------------------------------------------

@runtime_checkable
class OptionChainProvider(Protocol):
    """Broker-agnostic interface for querying option chains."""

    def get_option_expirations(self, underlying: str) -> list[date]: ...

    def get_option_chain(self, underlying: str, expiration: date) -> list[dict]: ...


class LumibotOptionChainProvider:
    """Queries IB option chains via a Lumibot strategy instance."""

    def __init__(self, strategy) -> None:
        self._strategy = strategy

    # Asset type mapping for non-futures underlyings
    _ASSET_TYPES: dict[str, str] = {
        "SPX": "INDEX",
        "SPY": "STOCK",
        "QQQ": "STOCK",
        "IWM": "STOCK",
        "DIA": "STOCK",
        "NVDA": "STOCK",
        "AAPL": "STOCK",
        "AMZN": "STOCK",
        "TSLA": "STOCK",
        "META": "STOCK",
        "MSFT": "STOCK",
    }

    def _get_underlying_asset(self, underlying: str):
        """Create the correct Asset type for the underlying.

        - SPX: index asset
        - SPY/QQQ/etc: stock asset
        - MES/ES: futures asset (requires front-month expiration)
        """
        from lumibot.entities import Asset

        # Non-futures underlyings
        asset_type_str = self._ASSET_TYPES.get(underlying)
        if asset_type_str is not None:
            at = getattr(Asset.AssetType, asset_type_str)
            return Asset(symbol=underlying, asset_type=at)

        # Use the strategy's own asset if it matches (already has expiration set)
        if hasattr(self._strategy, 'asset') and self._strategy.asset is not None:
            strat_asset = self._strategy.asset
            if getattr(strat_asset, 'symbol', None) == underlying:
                return strat_asset

        # Futures: compute front-month expiration
        from icc.broker.lumibot_strategy import _third_friday
        today = date.today()
        quarterly = [3, 6, 9, 12]
        exp = None
        for m in quarterly:
            y = today.year if m >= today.month else today.year + 1
            tf = _third_friday(y, m)
            if tf >= today:
                exp = tf
                break
        if exp is None:
            exp = _third_friday(today.year + 1, 3)

        return Asset(
            symbol=underlying,
            asset_type=Asset.AssetType.FUTURE,
            expiration=exp,
            multiplier=5,
        )

    def get_underlying_price(self, underlying: str) -> float | None:
        """Fetch the current price of the option underlying (IB first, yfinance fallback)."""
        # Try IB first
        try:
            asset = self._get_underlying_asset(underlying)
            price = self._strategy.get_last_price(asset)
            if price is not None:
                return float(price)
        except Exception as e:
            logger.debug("IB price failed for %s: %s", underlying, e)

        # Fallback: yfinance
        return _yf_get_price(underlying)

    def _get_chains(self, underlying: str) -> dict | None:
        """Fetch option chains from IB via Lumibot and return as dict."""
        asset = self._get_underlying_asset(underlying)
        chains = self._strategy.get_chains(asset)
        if chains is None:
            return None
        # Lumibot returns a dict with uppercase keys:
        # {"Expirations": [...], "Strikes": [...], "Chains": {"CALL": {...}, "PUT": {...}}}
        if isinstance(chains, dict):
            return chains
        return None

    # Cache expirations per underlying — they don't change during the day
    _expiration_cache: dict[str, list[date]] = {}

    def get_option_expirations(self, underlying: str) -> list[date]:
        # Return cached expirations if available
        if underlying in self._expiration_cache:
            return self._expiration_cache[underlying]

        # Try IB first (skip for stocks — no subscription)
        asset_type = self._ASSET_TYPES.get(underlying)
        if asset_type is None:  # futures only
            try:
                chains = self._get_chains(underlying)
                if chains is not None:
                    raw_exps = chains.get("Expirations", []) or []
                    parsed = []
                    for exp in raw_exps:
                        if exp is None:
                            continue
                        if isinstance(exp, date):
                            parsed.append(exp)
                        elif isinstance(exp, str):
                            try:
                                clean = exp if "-" in exp else f"{exp[:4]}-{exp[4:6]}-{exp[6:]}"
                                parsed.append(date.fromisoformat(clean))
                            except (ValueError, IndexError):
                                logger.debug("Skipping unparseable expiration: %s", exp)
                    if parsed:
                        result = sorted(parsed)
                        self._expiration_cache[underlying] = result
                        return result
            except Exception as e:
                logger.debug("IB expirations failed for %s: %s", underlying, e)

        # Fallback: yfinance (primary source for stocks)
        try:
            ticker = _yf_get_ticker(underlying)
            yf_exps = ticker.options  # tuple of date strings
            parsed = [date.fromisoformat(e) for e in yf_exps]
            if parsed:
                result = sorted(parsed)
                self._expiration_cache[underlying] = result
                logger.debug("yfinance expirations for %s: %d found", underlying, len(parsed))
                return result
        except Exception as e:
            logger.warning("yfinance expirations failed for %s: %s", underlying, e)
        return []

    def get_option_chain(
        self, underlying: str, expiration: date, near_price: float | None = None
    ) -> list[dict]:
        # For stocks, skip IB chain (requires subscription, returns bad strikes)
        # and go straight to yfinance which has correct strike grids.
        asset_type = self._ASSET_TYPES.get(underlying)
        if asset_type is not None:
            return self._yf_option_chain(underlying, expiration, near_price)

        # Try IB first (futures only)
        try:
            from lumibot.entities import Asset

            chains = self._get_chains(underlying)
            if chains is not None:
                exp_str = expiration.strftime("%Y-%m-%d")
                chains_data = chains.get("Chains", {})

                results: list[dict] = []
                for opt_type in ("CALL", "PUT"):
                    type_chains = chains_data.get(opt_type, {})
                    strikes = type_chains.get(exp_str, [])
                    if not strikes:
                        strikes = chains.get("Strikes", [])

                    if near_price is not None and strikes:
                        margin = near_price * 0.03
                        strikes = [s for s in strikes if abs(s - near_price) <= margin]
                        strikes = sorted(strikes, key=lambda s: abs(s - near_price))[:10]

                    for strike in strikes:
                        price = None
                        try:
                            option_asset = Asset(
                                symbol=underlying,
                                asset_type=Asset.AssetType.OPTION,
                                expiration=expiration,
                                strike=strike,
                                right=opt_type.lower(),
                            )
                            price = self._strategy.get_last_price(option_asset)
                        except Exception:
                            pass

                        if price is None or price == 0:
                            yf_price = _yf_get_option_premium(
                                underlying, expiration, float(strike), opt_type
                            )
                            if yf_price is not None:
                                price = yf_price

                        results.append({
                            "strike": float(strike),
                            "option_type": opt_type,
                            "last": float(price) if price else 0.0,
                            "ask": float(price) if price else 0.0,
                            "bid": 0.0,
                        })
                if results:
                    return results
        except Exception as e:
            logger.debug("IB option chain failed for %s: %s", underlying, e)

        # Fallback: full yfinance option chain
        return self._yf_option_chain(underlying, expiration, near_price)

    def _yf_option_chain(
        self, underlying: str, expiration: date, near_price: float | None = None
    ) -> list[dict]:
        """Fetch option chain from yfinance — reliable strikes for equity options."""
        try:
            ticker = _yf_get_ticker(underlying)
            exp_str = expiration.strftime("%Y-%m-%d")
            chain = ticker.option_chain(exp_str)
            results: list[dict] = []

            for opt_type, df in [("CALL", chain.calls), ("PUT", chain.puts)]:
                if near_price is not None:
                    df = df.loc[(df["strike"] - near_price).abs().argsort()[:10]]

                for _, row in df.iterrows():
                    ask = float(row.get("ask", 0) or 0)
                    last = float(row.get("lastPrice", 0) or 0)
                    results.append({
                        "strike": float(row["strike"]),
                        "option_type": opt_type,
                        "last": last,
                        "ask": ask if ask > 0 else last,
                        "bid": float(row.get("bid", 0) or 0),
                        "delta": float(row.get("delta", 0) or 0),
                        "implied_vol": float(row.get("impliedVolatility", 0) or 0),
                    })
            logger.debug("yfinance chain for %s exp=%s: %d contracts", underlying, exp_str, len(results))
            return results
        except Exception as e:
            logger.error("Failed to get option chain for %s: %s", underlying, e)
            return []


class MockOptionChainProvider:
    """Mock provider for tests and backtesting."""

    def __init__(
        self,
        expirations: list[date] | None = None,
        chain: list[dict] | None = None,
    ) -> None:
        self._expirations = expirations or []
        self._chain = chain or []

    def get_option_expirations(self, underlying: str) -> list[date]:
        return self._expirations

    def get_option_chain(self, underlying: str, expiration: date) -> list[dict]:
        return self._chain

    def set_chain(self, chain: list[dict]) -> None:
        self._chain = chain

    def set_expirations(self, expirations: list[date]) -> None:
        self._expirations = expirations


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------

MULTIPLIERS: dict[str, float] = {
    "MES": 5.0,
    "ES": 50.0,
    "SPX": 100.0,
    "SPY": 100.0,
    "QQQ": 100.0,
    "NVDA": 100.0,
    "AAPL": 100.0,
    "AMZN": 100.0,
    "TSLA": 100.0,
    "META": 100.0,
    "MSFT": 100.0,
    "IWM": 100.0,
    "DIA": 100.0,
}


class OptionChainResolver:
    """Selects the best option contract for an ICC entry signal.

    Usage::

        resolver = OptionChainResolver(provider, underlying="MES",
                                        strike_mode="ATM",
                                        expiration_mode="ZERO_DTE")
        contract = resolver.resolve("long", current_price=5420.25)
        if contract:
            trade_cost = contract.total_cost + commission
    """

    def __init__(
        self,
        provider: OptionChainProvider,
        underlying: str = "MES",
        strike_mode: str = "ATM",
        expiration_mode: str = "ZERO_DTE",
        expiration_guard_minutes: int = 15,
        max_premium: float = 0.0,
        min_premium: float = 0.0,
        otm_fallback: bool = True,
    ) -> None:
        self._provider = provider
        self._underlying = underlying
        self._strike_mode = strike_mode
        self._expiration_mode = expiration_mode
        self._expiration_guard_min = expiration_guard_minutes
        self._multiplier = MULTIPLIERS.get(underlying, 5.0)
        self._last_resolved: OptionContract | None = None
        self._max_premium = max_premium
        self._min_premium = min_premium
        self._otm_fallback = otm_fallback

    # -- public API ---------------------------------------------------------

    def resolve(
        self,
        direction: str,
        current_price: float,
        now: datetime | None = None,
    ) -> OptionContract | None:
        """Resolve the best option contract for the given entry.

        Args:
            direction: ``"long"`` → CALL, ``"short"`` → PUT.
            current_price: Underlying price for strike selection.
            now: Current datetime (defaults to ``datetime.now()``).

        Returns:
            :class:`OptionContract` or ``None`` if nothing suitable.
        """
        now = now or datetime.now()
        option_type = "CALL" if direction == "long" else "PUT"

        # 0. Get the option underlying's actual price for strike selection
        #    (current_price may be from the signal feed, e.g. MES, while
        #     options are on a different underlying like SPY)
        strike_price = current_price
        if hasattr(self._provider, 'get_underlying_price'):
            underlying_price = self._provider.get_underlying_price(self._underlying)
            if underlying_price is not None:
                strike_price = underlying_price
                logger.info(
                    "Using %s price %.2f for strike selection (signal price=%.2f)",
                    self._underlying, strike_price, current_price,
                )
            elif self._underlying == "SPY":
                # Fallback: SPY ≈ S&P 500 / 10 ≈ MES / 10
                strike_price = round(current_price / 10.0, 2)
                logger.info(
                    "SPY price unavailable, estimating from MES: %.2f → SPY ~%.2f",
                    current_price, strike_price,
                )

        # 1. Resolve expiration
        expiration = self._resolve_expiration(now)
        if expiration is None:
            logger.warning(
                "No suitable expiration for %s mode=%s",
                self._underlying,
                self._expiration_mode,
            )
            return None

        # 2. Expiration guard (check BEFORE afternoon override — near-close blocks all)
        if self._is_too_close_to_expiry(expiration, now):
            logger.info(
                "Expiration guard: %s within %d-min window",
                expiration,
                self._expiration_guard_min,
            )
            return None

        # 2b. Afternoon 0DTE override: avoid catastrophic theta decay
        #     After noon ET, upgrade 0DTE to the next available expiration.
        if expiration == now.date():
            try:
                now_et = now.astimezone(_ET) if now.tzinfo else _ET.localize(now)
            except Exception:
                now_et = datetime.now(_ET)
            if now_et.hour >= 12:
                future_exps = sorted(
                    e for e in self._provider.get_option_expirations(self._underlying)
                    if e > now.date()
                )
                if future_exps:
                    old_exp = expiration
                    expiration = future_exps[0]
                    logger.info(
                        "0DTE afternoon override: %s → %s (avoiding late-day theta decay)",
                        old_exp, expiration,
                    )
                else:
                    logger.warning(
                        "0DTE afternoon: no future expirations for %s, using today",
                        self._underlying,
                    )

        # 3. Fetch chain (pass price hint to limit strikes queried)
        if hasattr(self._provider, 'get_option_chain'):
            import inspect
            sig = inspect.signature(self._provider.get_option_chain)
            if 'near_price' in sig.parameters:
                chain = self._provider.get_option_chain(self._underlying, expiration, near_price=strike_price)
            else:
                chain = self._provider.get_option_chain(self._underlying, expiration)
        else:
            chain = self._provider.get_option_chain(self._underlying, expiration)
        if not chain:
            logger.warning("Empty chain for %s exp=%s", self._underlying, expiration)
            return None

        # 4. Filter to option type
        candidates = [
            c for c in chain if c.get("option_type", "").upper() == option_type
        ]
        if not candidates:
            logger.warning("No %s options in chain", option_type)
            return None

        # 5. Select strike
        selected = self._select_strike(candidates, strike_price, option_type)
        if selected is None:
            logger.warning("No strike found for %s @ %.2f", option_type, strike_price)
            return None

        # 6. Build contract
        premium = selected.get("ask") or selected.get("last") or 0.0
        if premium <= 0:
            logger.warning(
                "Zero/negative premium for %s %s %.0f exp=%s — skipping",
                self._underlying, option_type, selected["strike"], expiration,
            )
            return None

        # Min premium floor — reject contracts too cheap (commission eats the edge)
        if self._min_premium > 0 and premium < self._min_premium:
            logger.warning(
                "Premium $%.2f < min $%.2f for %s — skipping (too cheap)",
                premium, self._min_premium, self._underlying,
            )
            return None

        # Max premium cap — if ATM is too expensive, try OTM_1
        if self._max_premium > 0 and premium > self._max_premium:
            if self._otm_fallback and self._strike_mode != "OTM_1":
                logger.info(
                    "Premium $%.2f > max $%.2f for %s ATM — trying OTM fallback",
                    premium, self._max_premium, self._underlying,
                )
                otm = self._select_strike(candidates, strike_price, option_type, force_mode="OTM_1")
                if otm is not None:
                    otm_premium = otm.get("ask") or otm.get("last") or 0.0
                    if otm_premium >= self._min_premium and otm_premium <= self._max_premium:
                        selected = otm
                        premium = otm_premium
                        logger.info(
                            "OTM fallback: %s %.0f at $%.2f",
                            option_type, selected["strike"], premium,
                        )
                    else:
                        logger.warning(
                            "OTM premium $%.2f outside range $%.2f-$%.2f — skipping %s",
                            otm_premium, self._min_premium, self._max_premium, self._underlying,
                        )
                        return None
                else:
                    logger.warning(
                        "No OTM strike available for %s — skipping",
                        self._underlying,
                    )
                    return None
            else:
                logger.warning(
                    "Premium $%.2f > max $%.2f for %s — skipping",
                    premium, self._max_premium, self._underlying,
                )
                return None

        contract = OptionContract(
            underlying=self._underlying,
            option_type=option_type,
            strike=selected["strike"],
            expiration=expiration,
            premium=premium,
            multiplier=self._multiplier,
            delta=selected.get("delta", 0.0),
            gamma=selected.get("gamma", 0.0),
            theta=selected.get("theta", 0.0),
            vega=selected.get("vega", 0.0),
            implied_vol=selected.get("implied_vol", 0.0),
        )
        self._last_resolved = contract
        logger.info(
            "Resolved: %s premium=%.2f cost=%.2f",
            contract.symbol,
            contract.premium,
            contract.total_cost,
        )
        return contract

    @property
    def last_resolved(self) -> OptionContract | None:
        """Most recently resolved contract (for snapshot / logging)."""
        return self._last_resolved

    # -- internals ----------------------------------------------------------

    def _resolve_expiration(self, now: datetime) -> date | None:
        today = now.date()
        expirations = self._provider.get_option_expirations(self._underlying)
        future_exps = sorted(e for e in expirations if e >= today)

        if not future_exps:
            return None

        if self._expiration_mode == "ZERO_DTE":
            # Prefer today if available, else nearest
            if today in future_exps:
                return today
            return future_exps[0]

        if self._expiration_mode == "WEEKLY":
            cutoff = today + timedelta(days=7)
            weekly = [e for e in future_exps if e <= cutoff]
            if weekly:
                return weekly[0]
            # Fallback: nearest available expiration
            return future_exps[0]

        if self._expiration_mode == "MONTHLY":
            cutoff = today + timedelta(days=45)
            monthly = [e for e in future_exps if e <= cutoff]
            if not monthly:
                return None
            # Prefer expiration closest to ~30 days out
            return min(monthly, key=lambda e: abs((e - today).days - 30))

        return future_exps[0]  # fallback: nearest

    def _is_too_close_to_expiry(self, expiration: date, now: datetime) -> bool:
        if expiration > now.date():
            return False
        # Same-day: check minutes until 4:00 PM ET close
        close_minutes = 16 * 60  # 960
        now_minutes = now.hour * 60 + now.minute
        return (close_minutes - now_minutes) <= self._expiration_guard_min

    def _select_strike(
        self,
        candidates: list[dict],
        current_price: float,
        option_type: str,
        force_mode: str | None = None,
    ) -> dict | None:
        if not candidates:
            return None

        mode = force_mode or self._strike_mode

        if mode == "ATM":
            return min(candidates, key=lambda c: abs(c["strike"] - current_price))

        if mode == "OTM_1":
            if option_type == "CALL":
                otm = sorted(
                    (c for c in candidates if c["strike"] > current_price),
                    key=lambda c: c["strike"],
                )
            else:
                otm = sorted(
                    (c for c in candidates if c["strike"] < current_price),
                    key=lambda c: c["strike"],
                    reverse=True,
                )
            return otm[0] if otm else None

        if mode == "DELTA":
            target_delta = 0.50
            with_delta = [c for c in candidates if c.get("delta") is not None]
            if not with_delta:
                return min(
                    candidates, key=lambda c: abs(c["strike"] - current_price)
                )
            return min(
                with_delta,
                key=lambda c: abs(abs(c.get("delta", 0)) - target_delta),
            )

        # Fallback: ATM
        return min(candidates, key=lambda c: abs(c["strike"] - current_price))
