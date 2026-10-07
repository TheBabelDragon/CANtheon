"""Explicit clock semantics for CANtheon.

source_timestamp: when the originating node says the measurement occurred
ingest_timestamp: when CANtheon accepted the frame
sequence: source/message ordering identifier where available

Do not silently manufacture a source timestamp when the source did not provide one.
Unavailable source time is represented explicitly as None.
"""

from __future__ import annotations

from typing import Optional, Protocol


class Clock(Protocol):
    """Injectable clock abstraction. Deterministic tests inject a fixed clock."""

    def now_ns(self) -> int:
        """Return current time in nanoseconds."""
        ...


class SystemClock:
    """Wall-clock backed clock for production use."""

    def now_ns(self) -> int:
        import time
        return time.time_ns()


class FixedClock:
    """Injectable fixed clock for deterministic tests.

    Advance manually via advance() or set().
    """

    def __init__(self, start_ns: int = 0) -> None:
        self._ns = start_ns

    def now_ns(self) -> int:
        return self._ns

    def set(self, ns: int) -> None:
        self._ns = ns

    def advance(self, delta_ns: int) -> int:
        self._ns += delta_ns
        return self._ns


# Module-level default; Runtime accepts an explicit clock.
_default_clock: Clock = SystemClock()


def get_default_clock() -> Clock:
    return _default_clock


def set_default_clock(clock: Clock) -> None:
    global _default_clock
    _default_clock = clock
