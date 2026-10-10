"""Sequence tracking for messages that declare sequence information.

Detects: expected next, actual, gap, duplicate, rollback/reset.
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
class SequenceResult:
    previous: Optional[int]
    current: int
    expected: Optional[int]
    anomaly: SequenceAnomaly


class SequenceTracker:
    """Tracks sequence numbers for a single (node, message) stream."""

    def __init__(self, sequence_width: Optional[int] = None) -> None:
        self.sequence_width = sequence_width
        self._last: Optional[int] = None
        self._count = 0

    @property
    def last(self) -> Optional[int]:
        return self._last

    @property
    def last_sequence(self) -> Optional[int]:
        """Alias for .last — used by tests and external callers."""
        return self._last

    @property
    def count(self) -> int:
        return self._count

    def _wrap_mask(self) -> Optional[int]:
        if self.sequence_width is None:
            return None
        return (1 << self.sequence_width) - 1

    def observe(self, sequence: int) -> SequenceAnomaly:
        """Observe a new sequence value; return anomaly kind."""
        self._count += 1
        if self._last is None:
            self._last = sequence
            return SequenceAnomaly.NONE

        prev = self._last
        mask = self._wrap_mask()
        expected = prev + 1
        if mask is not None:
            expected = expected & mask

        if sequence == prev:
            anomaly = SequenceAnomaly.DUPLICATE
        elif sequence == expected:
            anomaly = SequenceAnomaly.NONE
        elif mask is not None and sequence < prev and (prev - sequence) > (mask // 2):
            # likely wrap-around that we already handled via expected
            # if not equal expected, treat as rollback
            anomaly = SequenceAnomaly.ROLLBACK
        elif sequence < prev:
            anomaly = SequenceAnomaly.ROLLBACK
        else:
            anomaly = SequenceAnomaly.GAP

        self._last = sequence
        return anomaly

    def result(self, sequence: int) -> SequenceResult:
        prev = self._last
        anomaly = self.observe(sequence)
        expected = None
        if prev is not None:
            expected = prev + 1
            mask = self._wrap_mask()
            if mask is not None:
                expected = expected & mask
        return SequenceResult(
            previous=prev,
            current=sequence,
            expected=expected,
            anomaly=anomaly,
        )
