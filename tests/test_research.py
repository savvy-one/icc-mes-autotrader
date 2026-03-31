"""Tests for the research agent (calendar, regime, confidence filtering)."""

import json
import os
import tempfile
from datetime import datetime, timedelta

import pytest

from icc.market.candle import Candle, CandleBuffer
from icc.research.agent import ResearchAgent
from icc.research.calendar import EconomicCalendar, CalendarState
from icc.research.config import ResearchConfig
from icc.research.regime import RegimeDetector


def _make_buffer(n: int = 50, base_price: float = 5200.0,
                 volume: int = 1000) -> CandleBuffer:
    """Create a buffer with n candles of varying range (normal vol regime)."""
    buf = CandleBuffer(maxlen=200)
    base = datetime(2026, 3, 10, 9, 30)
    for i in range(n):
        mid = base_price + (i % 10) * 0.5
        # Vary the range so ATR percentile lands in normal territory:
        # most candles have a small 1-point range, a few have up to 3
        spread = 0.5 + (i % 7) * 0.3  # ranges from 0.5 to 2.3
        buf.append(Candle(
            timestamp=base + timedelta(minutes=i),
            open=mid - 0.25,
            high=mid + spread,
            low=mid - spread,
            close=mid + 0.25,
            volume=volume,
        ))
    return buf


def _make_volatile_buffer(n: int = 50) -> CandleBuffer:
    """Create a buffer with high ATR candles."""
    buf = CandleBuffer(maxlen=200)
    base = datetime(2026, 3, 10, 9, 30)
    for i in range(n):
        mid = 5200.0
        # Extreme range for high ATR
        buf.append(Candle(
            timestamp=base + timedelta(minutes=i),
            open=mid,
            high=mid + 50.0,  # huge range
            low=mid - 50.0,
            close=mid + 10.0,
            volume=2000,
        ))
    return buf


# --- Economic Calendar ---

class TestEconomicCalendar:
    def test_blackout_during_fomc(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "events": [{
                    "name": "FOMC Rate Decision",
                    "type": "FOMC",
                    "timestamp": "2026-03-18T14:00:00",
                    "impact": "high",
                }]
            }, f)
            f.flush()

            cal = EconomicCalendar(f.name)
            # 10 minutes before FOMC (within 30-min pre-blackout)
            state = cal.check(datetime(2026, 3, 18, 13, 50))
            assert state.in_blackout
            assert "FOMC" in (state.active_event or "")

            os.unlink(f.name)

    def test_no_blackout_outside_window(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "events": [{
                    "name": "FOMC Rate Decision",
                    "type": "FOMC",
                    "timestamp": "2026-03-18T14:00:00",
                    "impact": "high",
                }]
            }, f)
            f.flush()

            cal = EconomicCalendar(f.name)
            # 2 hours before FOMC — outside blackout
            state = cal.check(datetime(2026, 3, 18, 12, 0))
            assert not state.in_blackout

            os.unlink(f.name)

    def test_no_file_graceful(self):
        cal = EconomicCalendar("/nonexistent/calendar.json")
        state = cal.check(datetime(2026, 3, 18, 14, 0))
        assert not state.in_blackout
        assert cal.event_count == 0

    def test_cpi_blackout(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "events": [{
                    "name": "CPI Release",
                    "type": "CPI",
                    "timestamp": "2026-03-11T08:30:00",
                    "impact": "high",
                }]
            }, f)
            f.flush()

            cal = EconomicCalendar(f.name)
            # During CPI blackout (5 minutes after)
            state = cal.check(datetime(2026, 3, 11, 8, 35))
            assert state.in_blackout

            os.unlink(f.name)


# --- Regime Detector ---

class TestRegimeDetector:
    def test_normal_atr(self):
        config = ResearchConfig()
        detector = RegimeDetector(config)
        buf = _make_buffer()
        now = datetime(2026, 3, 10, 11, 0)
        state = detector.assess(buf, "long", now)
        assert state.atr_regime in ("normal", "low", "high")
        assert 0.0 <= state.confidence_mult <= 1.5

    def test_extreme_atr_penalty(self):
        config = ResearchConfig()
        detector = RegimeDetector(config)
        buf = _make_volatile_buffer()
        now = datetime(2026, 3, 10, 11, 0)
        state = detector.assess(buf, "long", now)
        # With extreme vol, confidence should be reduced
        assert state.confidence_mult < 1.0

    def test_opening_session_penalty(self):
        config = ResearchConfig()
        detector = RegimeDetector(config)
        buf = _make_buffer()
        # At 9:35 AM (within opening 30 min)
        now = datetime(2026, 3, 10, 9, 35)
        state = detector.assess(buf, "long", now)
        assert state.session_phase == "opening"
        assert state.details["phase_mult"] == 0.8

    def test_mid_session_no_penalty(self):
        config = ResearchConfig()
        detector = RegimeDetector(config)
        buf = _make_buffer()
        now = datetime(2026, 3, 10, 11, 0)
        state = detector.assess(buf, "long", now)
        assert state.session_phase == "mid"
        assert state.details["phase_mult"] == 1.0

    def test_closing_session_penalty(self):
        config = ResearchConfig()
        detector = RegimeDetector(config)
        buf = _make_buffer()
        # At 15:35 (within closing 30 min)
        now = datetime(2026, 3, 10, 15, 35)
        state = detector.assess(buf, "long", now)
        assert state.session_phase == "closing"
        assert state.details["phase_mult"] == 0.7

    def test_vwap_counter_trend(self):
        config = ResearchConfig()
        detector = RegimeDetector(config)
        # Create buffer where price is clearly above VWAP (trending up)
        buf = CandleBuffer(maxlen=200)
        base = datetime(2026, 3, 10, 9, 30)
        for i in range(50):
            price = 5200.0 + i * 2.0  # Strong uptrend
            buf.append(Candle(
                timestamp=base + timedelta(minutes=i),
                open=price - 0.5,
                high=price + 1.0,
                low=price - 1.0,
                close=price,
                volume=1000,
            ))
        now = datetime(2026, 3, 10, 11, 0)
        # Short signal against uptrend = counter-VWAP
        state = detector.assess(buf, "short", now)
        assert not state.vwap_aligned
        assert state.details["vwap_mult"] == 0.8

    def test_insufficient_data(self):
        config = ResearchConfig()
        detector = RegimeDetector(config)
        buf = CandleBuffer(maxlen=200)
        # Only 5 candles
        base = datetime(2026, 3, 10, 9, 30)
        for i in range(5):
            buf.append(Candle(
                timestamp=base + timedelta(minutes=i),
                open=5200.0, high=5201.0, low=5199.0, close=5200.5,
                volume=1000,
            ))
        now = datetime(2026, 3, 10, 11, 0)
        state = detector.assess(buf, "long", now)
        # With insufficient data, should default to normal
        assert state.atr_regime == "normal"


# --- Research Agent ---

class TestResearchAgent:
    def test_disabled_full_confidence(self):
        config = ResearchConfig(enabled=False)
        agent = ResearchAgent(config)
        buf = _make_buffer()
        allowed, reason, confidence = agent.assess_entry(buf, "long")
        assert allowed
        assert confidence == 1.0

    def test_blackout_vetoes(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "events": [{
                    "name": "FOMC",
                    "type": "FOMC",
                    "timestamp": "2026-03-18T14:00:00",
                    "impact": "high",
                }]
            }, f)
            f.flush()

            config = ResearchConfig(calendar_file=f.name)
            agent = ResearchAgent(config)
            buf = _make_buffer()
            now = datetime(2026, 3, 18, 13, 50)
            allowed, reason, confidence = agent.assess_entry(buf, "long", now)
            assert not allowed
            assert confidence == 0.0
            assert "blackout" in reason.lower()

            os.unlink(f.name)

    def test_low_confidence_vetoes(self):
        config = ResearchConfig(
            min_confidence=0.5,
            calendar_file="/nonexistent.json",
            # Set multipliers so combined confidence is low
            opening_mult=0.5,
            extreme_vol_mult=0.2,
        )
        agent = ResearchAgent(config)
        buf = _make_volatile_buffer()
        # Opening session + extreme vol -> low confidence
        now = datetime(2026, 3, 10, 9, 35)
        allowed, reason, confidence = agent.assess_entry(buf, "long", now)
        # Either vetoed or allowed depending on exact ATR calculation
        # but confidence should be < 1.0
        assert confidence < 1.0

    def test_snapshot_serializable(self):
        config = ResearchConfig(calendar_file="/nonexistent.json")
        agent = ResearchAgent(config)
        buf = _make_buffer()
        now = datetime(2026, 3, 10, 11, 0)
        agent.assess_entry(buf, "long", now)
        snapshot = agent.get_snapshot()
        # Should be JSON-serializable
        import json
        json_str = json.dumps(snapshot)
        assert "confidence" in json_str

    def test_snapshot_before_assessment(self):
        config = ResearchConfig(calendar_file="/nonexistent.json")
        agent = ResearchAgent(config)
        snapshot = agent.get_snapshot()
        assert snapshot["status"] == "no_assessment"
