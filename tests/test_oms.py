"""Tests for OMS components."""

import pytest
from icc.constants import OrderSide, OrderStatus, OrderType
from icc.broker.backtest import BacktestBrokerAdapter
from icc.oms.manager import OrderManager
from icc.oms.orders import Order, Position
from icc.oms.position_tracker import PositionTracker


class TestOrderManager:
    def test_submit_fills(self):
        broker = BacktestBrokerAdapter()
        mgr = OrderManager(broker)
        order = Order(order_type=OrderType.STOP, side=OrderSide.BUY, price=100.0)
        result = mgr.submit(order)
        assert result.status == OrderStatus.FILLED
        assert result.filled_price is not None

    def test_cancel(self):
        broker = BacktestBrokerAdapter()
        mgr = OrderManager(broker)
        order = Order(order_type=OrderType.STOP, side=OrderSide.BUY, price=100.0)
        mgr.submit(order)
        # Already filled, can't cancel
        assert not mgr.cancel(order.order_id)


class TestPositionTracker:
    def test_open_close_long(self):
        tracker = PositionTracker()
        tracker.open_position(OrderSide.BUY, 100.0, 98.0, 104.0)
        assert not tracker.is_flat
        pnl = tracker.close_position(102.0, commission=5.0)
        # (102 - 100) * 5.0 * 1 - 5.0 = 5.0
        assert pnl == pytest.approx(5.0)
        assert tracker.is_flat

    def test_open_close_short(self):
        tracker = PositionTracker()
        tracker.open_position(OrderSide.SELL, 100.0, 102.0, 96.0)
        pnl = tracker.close_position(98.0, commission=5.0)
        # (100 - 98) * 5.0 * 1 - 5.0 = 5.0
        assert pnl == pytest.approx(5.0)

    def test_double_open_raises(self):
        tracker = PositionTracker()
        tracker.open_position(OrderSide.BUY, 100.0, 98.0, 104.0)
        with pytest.raises(RuntimeError):
            tracker.open_position(OrderSide.BUY, 101.0, 99.0, 105.0)

    def test_close_empty_raises(self):
        tracker = PositionTracker()
        with pytest.raises(RuntimeError):
            tracker.close_position(100.0)

    def test_stop_hit_long(self):
        tracker = PositionTracker()
        tracker.open_position(OrderSide.BUY, 100.0, 98.0, 104.0)
        assert tracker.check_stop_target(101.0, 97.5) == "stop_hit"

    def test_target_hit_long(self):
        tracker = PositionTracker()
        tracker.open_position(OrderSide.BUY, 100.0, 98.0, 104.0)
        assert tracker.check_stop_target(104.5, 100.0) == "target_hit"

    def test_stop_hit_short(self):
        tracker = PositionTracker()
        tracker.open_position(OrderSide.SELL, 100.0, 102.0, 96.0)
        assert tracker.check_stop_target(102.5, 99.0) == "stop_hit"

    def test_neither_hit(self):
        tracker = PositionTracker()
        tracker.open_position(OrderSide.BUY, 100.0, 98.0, 104.0)
        assert tracker.check_stop_target(101.0, 99.0) is None

    def test_bars_increment(self):
        tracker = PositionTracker()
        tracker.open_position(OrderSide.BUY, 100.0, 98.0, 104.0)
        assert tracker.increment_bars() == 1
        assert tracker.increment_bars() == 2
