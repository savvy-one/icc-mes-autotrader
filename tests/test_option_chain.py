"""Tests for OptionChainResolver."""

from datetime import date, datetime

import pytest

from icc.broker.option_chain import (
    MockOptionChainProvider,
    OptionChainResolver,
    OptionContract,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_chain(strikes, current_price=5420.0):
    """Build a synthetic chain with CALL + PUT at each strike."""
    chain = []
    for s in strikes:
        dist = abs(s - current_price)
        # Rough synthetic premium: deeper ITM → more expensive
        call_premium = max(0.25, (current_price - s) * 0.1 + 5.0) if s <= current_price else max(0.25, 5.0 - dist * 0.05)
        put_premium = max(0.25, (s - current_price) * 0.1 + 5.0) if s >= current_price else max(0.25, 5.0 - dist * 0.05)
        chain.append({
            "strike": s,
            "option_type": "CALL",
            "ask": round(call_premium, 2),
            "last": round(call_premium - 0.10, 2),
            "bid": round(call_premium - 0.25, 2),
            "delta": round(0.5 + (current_price - s) * 0.01, 3),
        })
        chain.append({
            "strike": s,
            "option_type": "PUT",
            "ask": round(put_premium, 2),
            "last": round(put_premium - 0.10, 2),
            "bid": round(put_premium - 0.25, 2),
            "delta": round(-0.5 + (current_price - s) * 0.01, 3),
        })
    return chain


TODAY = date(2026, 3, 13)
WEEKLY_EXP = date(2026, 3, 20)
MONTHLY_EXP = date(2026, 4, 17)
EXPIRATIONS = [TODAY, WEEKLY_EXP, MONTHLY_EXP]

STRIKES = [5400, 5410, 5420, 5430, 5440]
CHAIN = _make_chain(STRIKES)
CURRENT_PRICE = 5420.0

NOW = datetime(2026, 3, 13, 10, 30)  # 10:30 AM


@pytest.fixture
def provider():
    return MockOptionChainProvider(expirations=EXPIRATIONS, chain=CHAIN)


@pytest.fixture
def resolver(provider):
    return OptionChainResolver(
        provider=provider,
        underlying="MES",
        strike_mode="ATM",
        expiration_mode="ZERO_DTE",
        expiration_guard_minutes=15,
    )


# ---------------------------------------------------------------------------
# OptionContract tests
# ---------------------------------------------------------------------------

class TestOptionContract:
    def test_total_cost(self):
        c = OptionContract(
            underlying="MES", option_type="CALL", strike=5420,
            expiration=TODAY, premium=10.0, multiplier=5.0,
        )
        assert c.total_cost == 50.0  # 10 * 5

    def test_total_cost_spx(self):
        c = OptionContract(
            underlying="SPX", option_type="PUT", strike=5420,
            expiration=TODAY, premium=10.0, multiplier=100.0,
        )
        assert c.total_cost == 1000.0

    def test_symbol_format(self):
        c = OptionContract(
            underlying="MES", option_type="CALL", strike=5420,
            expiration=date(2026, 3, 13), premium=5.0, multiplier=5.0,
        )
        assert c.symbol == "MES260313C5420"

    def test_symbol_put(self):
        c = OptionContract(
            underlying="MES", option_type="PUT", strike=5400,
            expiration=date(2026, 4, 17), premium=5.0, multiplier=5.0,
        )
        assert c.symbol == "MES260417P5400"

    def test_frozen(self):
        c = OptionContract(
            underlying="MES", option_type="CALL", strike=5420,
            expiration=TODAY, premium=5.0, multiplier=5.0,
        )
        with pytest.raises(AttributeError):
            c.premium = 10.0


# ---------------------------------------------------------------------------
# Expiration resolution
# ---------------------------------------------------------------------------

class TestExpirationResolution:
    def test_zero_dte_picks_today(self, provider):
        r = OptionChainResolver(provider, expiration_mode="ZERO_DTE")
        contract = r.resolve("long", CURRENT_PRICE, now=NOW)
        assert contract is not None
        assert contract.expiration == TODAY

    def test_zero_dte_falls_back_to_nearest(self, provider):
        """If today is not an expiration, pick nearest future."""
        provider.set_expirations([WEEKLY_EXP, MONTHLY_EXP])
        r = OptionChainResolver(provider, expiration_mode="ZERO_DTE")
        contract = r.resolve("long", CURRENT_PRICE, now=NOW)
        assert contract is not None
        assert contract.expiration == WEEKLY_EXP

    def test_weekly_within_7_days(self, provider):
        r = OptionChainResolver(provider, expiration_mode="WEEKLY")
        contract = r.resolve("long", CURRENT_PRICE, now=NOW)
        assert contract is not None
        assert contract.expiration == TODAY  # today is within 7 days

    def test_weekly_no_match_falls_back_to_nearest(self):
        far = date(2026, 6, 19)
        p = MockOptionChainProvider(expirations=[far], chain=CHAIN)
        r = OptionChainResolver(p, expiration_mode="WEEKLY")
        contract = r.resolve("long", CURRENT_PRICE, now=NOW)
        assert contract is not None
        assert contract.expiration == far  # falls back to nearest available

    def test_monthly_prefers_30_days_out(self, provider):
        r = OptionChainResolver(provider, expiration_mode="MONTHLY")
        contract = r.resolve("long", CURRENT_PRICE, now=NOW)
        assert contract is not None
        # Monthly exp (April 17) is 35 days out, closest to 30
        assert contract.expiration == MONTHLY_EXP

    def test_no_expirations_returns_none(self):
        p = MockOptionChainProvider(expirations=[], chain=CHAIN)
        r = OptionChainResolver(p, expiration_mode="ZERO_DTE")
        assert r.resolve("long", CURRENT_PRICE, now=NOW) is None


# ---------------------------------------------------------------------------
# Expiration guard
# ---------------------------------------------------------------------------

class TestExpirationGuard:
    def test_not_triggered_morning(self, resolver):
        """10:30 AM is far from close — no guard."""
        contract = resolver.resolve("long", CURRENT_PRICE, now=NOW)
        assert contract is not None

    def test_triggered_near_close(self, provider):
        """15:50 = 10 min to close, guard=15 → blocked."""
        r = OptionChainResolver(
            provider, expiration_mode="ZERO_DTE", expiration_guard_minutes=15,
        )
        late = datetime(2026, 3, 13, 15, 50)
        contract = r.resolve("long", CURRENT_PRICE, now=late)
        assert contract is None

    def test_not_triggered_different_day(self, provider):
        """Expiration is tomorrow — guard doesn't apply."""
        provider.set_expirations([WEEKLY_EXP])
        r = OptionChainResolver(
            provider, expiration_mode="WEEKLY", expiration_guard_minutes=15,
        )
        late = datetime(2026, 3, 13, 15, 50)
        contract = r.resolve("long", CURRENT_PRICE, now=late)
        assert contract is not None


# ---------------------------------------------------------------------------
# Strike selection
# ---------------------------------------------------------------------------

class TestStrikeSelection:
    def test_atm_selects_closest(self, resolver):
        contract = resolver.resolve("long", 5418.5, now=NOW)
        assert contract is not None
        assert contract.strike == 5420  # closest to 5418.5

    def test_atm_exact_match(self, resolver):
        contract = resolver.resolve("long", 5420.0, now=NOW)
        assert contract is not None
        assert contract.strike == 5420

    def test_otm_call_above_price(self, provider):
        r = OptionChainResolver(provider, strike_mode="OTM_1", expiration_mode="ZERO_DTE")
        contract = r.resolve("long", 5420.0, now=NOW)
        assert contract is not None
        assert contract.option_type == "CALL"
        assert contract.strike == 5430  # first strike above

    def test_otm_put_below_price(self, provider):
        r = OptionChainResolver(provider, strike_mode="OTM_1", expiration_mode="ZERO_DTE")
        contract = r.resolve("short", 5420.0, now=NOW)
        assert contract is not None
        assert contract.option_type == "PUT"
        assert contract.strike == 5410  # first strike below

    def test_delta_mode_with_delta(self, provider):
        r = OptionChainResolver(provider, strike_mode="DELTA", expiration_mode="ZERO_DTE")
        contract = r.resolve("long", CURRENT_PRICE, now=NOW)
        assert contract is not None
        # Should pick strike closest to 0.50 delta

    def test_delta_mode_fallback_no_delta(self, provider):
        """If no delta data, falls back to ATM."""
        chain_no_delta = [
            {"strike": s, "option_type": t, "ask": 5.0}
            for s in STRIKES for t in ("CALL", "PUT")
        ]
        provider.set_chain(chain_no_delta)
        r = OptionChainResolver(provider, strike_mode="DELTA", expiration_mode="ZERO_DTE")
        contract = r.resolve("long", 5420.0, now=NOW)
        assert contract is not None
        assert contract.strike == 5420  # ATM fallback


# ---------------------------------------------------------------------------
# Direction → option type mapping
# ---------------------------------------------------------------------------

class TestDirection:
    def test_long_resolves_call(self, resolver):
        contract = resolver.resolve("long", CURRENT_PRICE, now=NOW)
        assert contract is not None
        assert contract.option_type == "CALL"

    def test_short_resolves_put(self, resolver):
        contract = resolver.resolve("short", CURRENT_PRICE, now=NOW)
        assert contract is not None
        assert contract.option_type == "PUT"


# ---------------------------------------------------------------------------
# Contract metadata
# ---------------------------------------------------------------------------

class TestContractMetadata:
    def test_underlying_set(self, resolver):
        contract = resolver.resolve("long", CURRENT_PRICE, now=NOW)
        assert contract.underlying == "MES"

    def test_multiplier_mes(self, resolver):
        contract = resolver.resolve("long", CURRENT_PRICE, now=NOW)
        assert contract.multiplier == 5.0

    def test_multiplier_spx(self, provider):
        r = OptionChainResolver(provider, underlying="SPX", expiration_mode="ZERO_DTE")
        contract = r.resolve("long", CURRENT_PRICE, now=NOW)
        assert contract.multiplier == 100.0

    def test_premium_from_ask(self, resolver):
        contract = resolver.resolve("long", CURRENT_PRICE, now=NOW)
        assert contract is not None
        assert contract.premium > 0

    def test_last_resolved_stored(self, resolver):
        assert resolver.last_resolved is None
        contract = resolver.resolve("long", CURRENT_PRICE, now=NOW)
        assert resolver.last_resolved is contract

    def test_greeks_populated(self, resolver):
        contract = resolver.resolve("long", CURRENT_PRICE, now=NOW)
        assert contract is not None
        # Our mock chain includes delta
        assert contract.delta != 0.0


# ---------------------------------------------------------------------------
# Empty / missing chain scenarios
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_chain_returns_none(self):
        p = MockOptionChainProvider(expirations=[TODAY], chain=[])
        r = OptionChainResolver(p, expiration_mode="ZERO_DTE")
        assert r.resolve("long", CURRENT_PRICE, now=NOW) is None

    def test_no_calls_in_chain(self):
        puts_only = [c for c in CHAIN if c["option_type"] == "PUT"]
        p = MockOptionChainProvider(expirations=[TODAY], chain=puts_only)
        r = OptionChainResolver(p, expiration_mode="ZERO_DTE")
        assert r.resolve("long", CURRENT_PRICE, now=NOW) is None

    def test_no_puts_in_chain(self):
        calls_only = [c for c in CHAIN if c["option_type"] == "CALL"]
        p = MockOptionChainProvider(expirations=[TODAY], chain=calls_only)
        r = OptionChainResolver(p, expiration_mode="ZERO_DTE")
        assert r.resolve("short", CURRENT_PRICE, now=NOW) is None

    def test_otm_no_strikes_above(self, provider):
        """All strikes at or below price — OTM_1 call finds nothing."""
        low_chain = _make_chain([5400, 5410, 5420])
        provider.set_chain(low_chain)
        r = OptionChainResolver(provider, strike_mode="OTM_1", expiration_mode="ZERO_DTE")
        # Price at 5420, no strikes above
        assert r.resolve("long", 5420.0, now=NOW) is None


# ---------------------------------------------------------------------------
# MockOptionChainProvider
# ---------------------------------------------------------------------------

class TestMockProvider:
    def test_set_chain(self):
        p = MockOptionChainProvider()
        assert p.get_option_chain("MES", TODAY) == []
        p.set_chain(CHAIN)
        assert len(p.get_option_chain("MES", TODAY)) == len(CHAIN)

    def test_set_expirations(self):
        p = MockOptionChainProvider()
        assert p.get_option_expirations("MES") == []
        p.set_expirations(EXPIRATIONS)
        assert p.get_option_expirations("MES") == EXPIRATIONS
