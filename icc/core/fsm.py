"""ICCStateMachine — 11 states, transition table."""

from __future__ import annotations

import logging
from typing import Callable

from icc.constants import FSMState

logger = logging.getLogger(__name__)

# Valid transitions: {from_state: {action: to_state}}
TRANSITION_TABLE: dict[FSMState, dict[str, FSMState]] = {
    FSMState.FLAT: {
        "indication_up": FSMState.INDICATION_UP,
        "indication_down": FSMState.INDICATION_DOWN,
    },
    FSMState.INDICATION_UP: {
        "correction_up": FSMState.CORRECTION_UP,
        "timeout": FSMState.FLAT,
        "invalidate": FSMState.FLAT,
    },
    FSMState.INDICATION_DOWN: {
        "correction_down": FSMState.CORRECTION_DOWN,
        "timeout": FSMState.FLAT,
        "invalidate": FSMState.FLAT,
    },
    FSMState.CORRECTION_UP: {
        "continuation_up": FSMState.CONTINUATION_UP,
        "timeout": FSMState.FLAT,
        "invalidate": FSMState.FLAT,
    },
    FSMState.CORRECTION_DOWN: {
        "continuation_down": FSMState.CONTINUATION_DOWN,
        "timeout": FSMState.FLAT,
        "invalidate": FSMState.FLAT,
    },
    FSMState.CONTINUATION_UP: {
        "enter_long": FSMState.IN_TRADE_UP,
        "timeout": FSMState.FLAT,
        "invalidate": FSMState.FLAT,
    },
    FSMState.CONTINUATION_DOWN: {
        "enter_short": FSMState.IN_TRADE_DOWN,
        "timeout": FSMState.FLAT,
        "invalidate": FSMState.FLAT,
    },
    FSMState.IN_TRADE_UP: {
        "exit": FSMState.EXIT,
        "stop_hit": FSMState.EXIT,
        "target_hit": FSMState.EXIT,
        "timeout_exit": FSMState.EXIT,
    },
    FSMState.IN_TRADE_DOWN: {
        "exit": FSMState.EXIT,
        "stop_hit": FSMState.EXIT,
        "target_hit": FSMState.EXIT,
        "timeout_exit": FSMState.EXIT,
    },
    FSMState.EXIT: {
        "reset": FSMState.FLAT,
    },
    FSMState.RISK_BLOCKED: {
        "reset": FSMState.FLAT,
    },
}


class ICCStateMachine:
    """FSM for ICC methodology with 11 states."""

    def __init__(self) -> None:
        self._state: FSMState = FSMState.FLAT
        self._listeners: list[Callable[[FSMState, str, FSMState], None]] = []

    @property
    def state(self) -> FSMState:
        return self._state

    def add_listener(self, fn: Callable[[FSMState, str, FSMState], None]) -> None:
        self._listeners.append(fn)

    def transition(self, action: str) -> FSMState:
        """Attempt a transition. Returns new state."""
        # Risk block can happen from any state
        if action == "risk_block":
            old = self._state
            self._state = FSMState.RISK_BLOCKED
            self._notify(old, action, self._state)
            return self._state

        transitions = TRANSITION_TABLE.get(self._state, {})
        new_state = transitions.get(action)

        if new_state is None:
            logger.warning(
                "Invalid transition: %s -[%s]-> ???", self._state.value, action
            )
            return self._state

        old = self._state
        self._state = new_state
        self._notify(old, action, self._state)
        return self._state

    def force_state(self, state: FSMState) -> None:
        """Force state (for risk engine kill switch)."""
        old = self._state
        self._state = state
        self._notify(old, "force", state)

    def reset(self) -> None:
        old = self._state
        self._state = FSMState.FLAT
        self._notify(old, "reset", FSMState.FLAT)

    def _notify(self, old: FSMState, action: str, new: FSMState) -> None:
        logger.info("FSM: %s -[%s]-> %s", old.value, action, new.value)
        for fn in self._listeners:
            fn(old, action, new)
