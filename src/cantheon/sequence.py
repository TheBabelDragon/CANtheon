"""Sequence tracking for messages that declare sequence information.

Detects: expected next, actual, gap, duplicate, rollback/reset.
Does NOT discard frames — observation survives; diagnostic records anomaly.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class SequenceAnomaly(str, Enum):
    NONE = "NONE"
    GAP = "GAP"
    DUPLICATE = "DUPLICATE"
    ROLLBACK = "ROLLBACK"


@dataclass
class SequenceTracker:
    """Per-(node, message) sequence tracker.

    sequence_width: bit width of the sequence field (e.g. 8 → wrap at 256).
    None means unbounded monotonic integer.
    """

    sequence_width: Optional[int] = None
    last_sequence: Optional[int] = None

    @property
    def modulus(self) -> Optional[int]:
        if self.sequence_width is None:
            return None
        return 1 << self.sequence_width

    def expected_next(self) -> Optional[int]:
        if self.last_sequence is None:
            return None
        nxt = self.last_sequence + 1
        if self.modulus is not None:
            nxt = nxt % self.modulus
        return nxt

    def observe(self, sequence: int) -> SequenceAnomaly:
        """Observe a sequence value. Returns anomaly type; always updates state."""
        if self.last_sequence is None:
            self.last_sequence = sequence
            return SequenceAnomaly.NONE

        expected = self.expected_next()
        assert expected is not None

        if sequence == self.last_sequence:
            return SequenceAnomaly.DUPLICATE

        if sequence == expected:
            self.last_sequence = sequence
            return SequenceAnomaly.NONE

        if self.modulus is not None:
            forward = (sequence - self.last_sequence) % self.modulus
            if forward == 0:
                return SequenceAnomaly.DUPLICATE
            if forward > self.modulus // 2:
                self.last_sequence = sequence
                return SequenceAnomaly.ROLLBACK
            self.last_sequence = sequence
            return SequenceAnomaly.GAP

        if sequence < self.last_sequence:
            self.last_sequence = sequence
            return SequenceAnomaly.ROLLBACK
        self.last_sequence = sequence
        return SequenceAnomaly.GAP
