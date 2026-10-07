"""Node heartbeat / liveness tracking.

CANtheon reports state; it does not decide how the physical system recovers.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class LivenessState(str, Enum):
    ALIVE = "ALIVE"
    STALE = "STALE"
    TIMEOUT = "TIMEOUT"
    UNKNOWN = "UNKNOWN"


@dataclass
class LivenessTracker:
    """Per-node liveness with injectable clock semantics.

    timeout_threshold_ns: after this duration without traffic → TIMEOUT
    stale_threshold_ns: after this duration without traffic → STALE
      (must be <= timeout_threshold_ns)
    """

    timeout_threshold_ns: int
    stale_threshold_ns: Optional[int] = None
    last_seen_ns: Optional[int] = None

    def __post_init__(self) -> None:
        if self.stale_threshold_ns is None:
            self.stale_threshold_ns = self.timeout_threshold_ns // 2
        if self.stale_threshold_ns > self.timeout_threshold_ns:
            raise ValueError("stale_threshold_ns must be <= timeout_threshold_ns")

    def touch(self, now_ns: int) -> None:
        self.last_seen_ns = now_ns

    def state(self, now_ns: int) -> LivenessState:
        if self.last_seen_ns is None:
            return LivenessState.UNKNOWN
        age = now_ns - self.last_seen_ns
        if age >= self.timeout_threshold_ns:
            return LivenessState.TIMEOUT
        if age >= self.stale_threshold_ns:  # type: ignore[operator]
            return LivenessState.STALE
        return LivenessState.ALIVE
