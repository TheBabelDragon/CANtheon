"""Canonical observation and quality flags.

Distinguishes:
  - raw CAN frame (CanFrame / RawFrameRecord)
  - decoded signal values
  - normalized Observation

No silent conversion between layers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from .provenance import Provenance


class Quality(str, Enum):
    VALID = "VALID"
    INVALID = "INVALID"
    STALE = "STALE"
    OUT_OF_RANGE = "OUT_OF_RANGE"
    DECODE_ERROR = "DECODE_ERROR"


@dataclass(frozen=True)
class RawFrameRecord:
    """Immutable record of a received CAN frame before decoding."""

    can_id: int
    data_hex: str
    dlc: int
    receive_timestamp_ns: Optional[int]
    source: str = "can"


@dataclass(frozen=True)
class Observation:
    """Canonical physical-state observation.

    Required fields per the CANtheon contract:
      node_id, message_id, signal_id, value, unit,
      timestamp, sequence, quality, source, provenance
    """

    node_id: str
    message_id: int
    signal_id: str
    value: float
    unit: str
    timestamp_ns: int
    sequence: int
    quality: Quality
    source: str
    provenance: Provenance
    raw_value: Optional[int] = None  # integer before scale/offset
    message_name: str = ""
    signal_name: str = ""
    schema_version: str = "1.0"
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "message_id": self.message_id,
            "message_id_hex": f"0x{self.message_id:03X}",
            "signal_id": self.signal_id,
            "value": self.value,
            "unit": self.unit,
            "timestamp_ns": self.timestamp_ns,
            "sequence": self.sequence,
            "quality": self.quality.value,
            "source": self.source,
            "provenance": self.provenance.to_dict(),
            "raw_value": self.raw_value,
            "message_name": self.message_name,
            "signal_name": self.signal_name,
            "schema_version": self.schema_version,
            "extra": dict(self.extra),
        }

    def is_valid(self) -> bool:
        return self.quality == Quality.VALID
