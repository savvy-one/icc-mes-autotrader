"""Tests for synthetic option premium calculator (Black-Scholes)."""

import math
from datetime import date

import pytest

from icc.backtest.premium import (
    SyntheticPremiumCalculator,
    bs_delta,
    bs_premium,
)


class TestBSPremium:
    def test_atm_call_positive(self):
        """ATM call with 30 DTE should have positive premium."""
        p = bs_premium(spot=5420, strike=5420, dte=30, vol=0.20)
        assert p > 0

    def test_atm_put_positive(self):
        p = bs_premium(spot=5420, strike=5420, dte=30, vol=0.20, option_type="PUT")
        assert p > 0

    def test_deep_itm_call(self):
        """Deep ITM call premium ~ intrinsic value."""
        p = bs_premium(spot=5500, strike=5400, dte=30, vol=0.20)
        assert p >= 100  # At least intrinsic (5500 - 5400)

    def test_deep_otm_call_cheap(self):
        """Deep OTM call should be cheap."""
        p = bs_premium(spot=5420, strike=5600, dte=1, vol=0.20)
        assert p < 1.0

    def test_expired_call_intrinsic(self):
        """Expired ITM call = intrinsic value."""
        p = bs_premium(spot=5450, strike=5420, dte=0, vol=0.20)
        assert p == pytest.approx(30.0)

    def test_expired_otm_call_zero(self):
        """Expired OTM call = 0."""
        p = bs_premium(spot=5400, strike=5420, dte=0, vol=0.20)
        assert p == 0.0

    def test_expired_itm_put(self):
        p = bs_premium(spot=5400, strike=5420, dte=0, vol=0.20, option_type="PUT")
        assert p == pytest.approx(20.0)

    def test_expired_otm_put_zero(self):
        p = bs_premium(spot=5450, strike=5420, dte=0, vol=0.20, option_type="PUT")
        assert p == 0.0

    def test_higher_vol_higher_premium(self):
        low = bs_premium(spot=5420, strike=5420, dte=30, vol=0.10)
        high = bs_premium(spot=5420, strike=5420, dte=30, vol=0.30)
        assert high > low

    def test_more_dte_higher_premium(self):
        short = bs_premium(spot=5420, strike=5420, dte=1, vol=0.20)
        long = bs_premium(spot=5420, strike=5420, dte=60, vol=0.20)
        assert long > short

    def test_put_call_parity_approx(self):
        """C - P ≈ S - K*e^(-rT) for same strike/expiry."""
        S, K, dte, vol, r = 5420, 5420, 30, 0.20, 0.05
        T = dte / 365.0
        C = bs_premium(S, K, dte, vol, "CALL", r)
        P = bs_premium(S, K, dte, vol, "PUT", r)
        expected = S - K * math.exp(-r * T)
        assert C - P == pytest.approx(expected, abs=0.01)


class TestBSDelta:
    def test_atm_call_delta_near_half(self):
        d = bs_delta(spot=5420, strike=5420, dte=30, vol=0.20)
        assert 0.4 < d < 0.6

    def test_atm_put_delta_near_neg_half(self):
        d = bs_delta(spot=5420, strike=5420, dte=30, vol=0.20, option_type="PUT")
        assert -0.6 < d < -0.4

    def test_deep_itm_call_delta_near_one(self):
        d = bs_delta(spot=5500, strike=5300, dte=30, vol=0.20)
        assert d > 0.7

    def test_deep_otm_call_delta_near_zero(self):
        d = bs_delta(spot=5420, strike=5700, dte=1, vol=0.20)
        assert d < 0.1

    def test_expired_itm_call_delta_one(self):
        d = bs_delta(spot=5450, strike=5420, dte=0, vol=0.20)
        assert d == 1.0

    def test_expired_otm_call_delta_zero(self):
        d = bs_delta(spot=5400, strike=5420, dte=0, vol=0.20)
        assert d == 0.0


class TestSyntheticPremiumCalculator:
    def test_premium_method(self):
        calc = SyntheticPremiumCalculator(vol=0.20)
        p = calc.premium(spot=5420, strike=5420, dte=30)
        assert p > 0

    def test_delta_method(self):
        calc = SyntheticPremiumCalculator(vol=0.20)
        d = calc.delta(spot=5420, strike=5420, dte=30)
        assert 0.4 < d < 0.6

    def test_premium_from_contract(self):
        calc = SyntheticPremiumCalculator(vol=0.20)
        p = calc.premium_from_contract(
            spot=5420,
            strike=5420,
            expiration=date(2026, 4, 17),
            option_type="CALL",
            as_of=date(2026, 3, 13),
        )
        assert p > 0

    def test_premium_from_expired_contract(self):
        calc = SyntheticPremiumCalculator(vol=0.20)
        p = calc.premium_from_contract(
            spot=5450,
            strike=5420,
            expiration=date(2026, 3, 10),
            option_type="CALL",
            as_of=date(2026, 3, 13),
        )
        assert p == pytest.approx(30.0)  # Intrinsic only
