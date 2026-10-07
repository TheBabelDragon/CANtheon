"""Canonical observation and quality flags.

Time semantics:
  source_timestamp_ns: when the originating node says the measurement occurred
  ingest_timestamp_ns: when CANtheon accepted the frame
  sequence: source/message ordering identifier
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from .provenance import Provenance
from .schema_compat import SchemaIdentity


class Quality(str, Enum):
    VALID = "VALID"
    INVALID = "INVALID"
    STALE = "STALE"
    OUT_OF_RANGE = "OUT_OF_RANGE"
    DECODE_ERROR = "DECODE_ERROR"


@dataclass(frozen=True)
class RawFrameRecord:
    can_id: int
    data_hex: str
    dlc: int
    receive_timestamp_ns: Optional[int]
    source: str = "can"


@dataclass(frozen=True)
class Observation:
    node_id: str
    message_id: int
    signal_id: str
    value: float
    unit: str
    sequence: int
    quality: Quality
    source: str
    provenance: Provenance
    ingest_timestamp_ns: int = 0
    source_timestamp_ns: Optional[int] = None
    timestamp_ns: int = 0
    raw_value: Optional[int] = None
    message_name: str = ""
    signal_name: str = ""
    schema_version: str = "1.0"
    schema_id: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.timestamp_ns and not self.ingest_timestamp_ns:
            object.__setattr__(self, "ingest_timestamp_ns", self.timestamp_ns)
        if self.ingest_timestamp_ns and not self.timestamp_ns:
            object.__setattr__(self, "timestamp_ns", self.ingest_timestamp_ns)

    @property
    def schema_identity(self) -> SchemaIdentity:
        return SchemaIdentity(
            schema_id=self.schema_id or "unknown",
            schema_version=self.schema_version,
        )

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "message_id": self.message_id,
            "message_id_hex": f"0x{self.message_id:03X}",
            "signal_id": self.signal_id,
            "value": self.value,
            "unit": self.unit,
            "timestamp_ns": self.timestamp_ns,
            "ingest_timestamp_ns": self.ingest_timestamp_ns,
            "source_timestamp_ns": self.source_timestamp_ns,
            "sequence": self.sequence,
            "quality": self.quality.value,
            "source": self.source,
            "provenance": self.provenance.to_dict(),
            "raw_value": self.raw_value,
            "message_name": self.message_name,
            "signal_name": self.signal_name,
            "schema_version": self.schema_version,
            "schema_id": self.schema_id,
            "extra": dict(self.extra),
        }

    def is_valid(self) -> bool:
        return self.quality == Quality.VALID

    def canonical_key(self) -> str:
        return (
            f"{self.node_id}|0x{self.message_id:03X}|{self.signal_id}|"
            f"{self.sequence}|{self.value}|{self.quality.value}|"
            f"{self.schema_id}@{self.schema_version}"
        )
