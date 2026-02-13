"""Tests for ICCStateMachine."""

import pytest
from icc.constants import FSMState
from icc.core.fsm import ICCStateMachine


@pytest.fixture
def fsm():
    return ICCStateMachine()


class TestFSM:
    def test_initial_state(self, fsm):
        assert fsm.state == FSMState.FLAT

    def test_long_path(self, fsm):
        fsm.transition("indication_up")
        assert fsm.state == FSMState.INDICATION_UP
        fsm.transition("correction_up")
        assert fsm.state == FSMState.CORRECTION_UP
        fsm.transition("continuation_up")
        assert fsm.state == FSMState.CONTINUATION_UP
        fsm.transition("enter_long")
        assert fsm.state == FSMState.IN_TRADE_UP
        fsm.transition("target_hit")
        assert fsm.state == FSMState.EXIT
        fsm.transition("reset")
        assert fsm.state == FSMState.FLAT

    def test_short_path(self, fsm):
        fsm.transition("indication_down")
        assert fsm.state == FSMState.INDICATION_DOWN
        fsm.transition("correction_down")
        assert fsm.state == FSMState.CORRECTION_DOWN
        fsm.transition("continuation_down")
        assert fsm.state == FSMState.CONTINUATION_DOWN
        fsm.transition("enter_short")
        assert fsm.state == FSMState.IN_TRADE_DOWN
        fsm.transition("stop_hit")
        assert fsm.state == FSMState.EXIT
        fsm.transition("reset")
        assert fsm.state == FSMState.FLAT

    def test_risk_block_from_any_state(self, fsm):
        fsm.transition("indication_up")
        fsm.transition("risk_block")
        assert fsm.state == FSMState.RISK_BLOCKED

    def test_invalid_transition_stays(self, fsm):
        fsm.transition("enter_long")  # invalid from FLAT
        assert fsm.state == FSMState.FLAT

    def test_timeout_resets_to_flat(self, fsm):
        fsm.transition("indication_up")
        fsm.transition("timeout")
        assert fsm.state == FSMState.FLAT

    def test_force_state(self, fsm):
        fsm.force_state(FSMState.RISK_BLOCKED)
        assert fsm.state == FSMState.RISK_BLOCKED

    def test_listener_called(self, fsm):
        transitions = []
        fsm.add_listener(lambda old, action, new: transitions.append((old, action, new)))
        fsm.transition("indication_up")
        assert len(transitions) == 1
        assert transitions[0] == (FSMState.FLAT, "indication_up", FSMState.INDICATION_UP)

    def test_reset(self, fsm):
        fsm.transition("indication_up")
        fsm.reset()
        assert fsm.state == FSMState.FLAT
