"""First-class diagnostic model.

Diagnostics are observable through Runtime/CANgate.
Malformed frames are distinguishable from valid observations whose value is invalid.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from .provenance import Provenance


class DiagnosticType(str, Enum):
    NODE_TIMEOUT = "NODE_TIMEOUT"
    UNKNOWN_MESSAGE = "UNKNOWN_MESSAGE"
    DECODE_ERROR = "DECODE_ERROR"
    SEQUENCE_GAP = "SEQUENCE_GAP"
    SEQUENCE_DUPLICATE = "SEQUENCE_DUPLICATE"
    SEQUENCE_ROLLBACK = "SEQUENCE_ROLLBACK"
    STALE_OBSERVATION = "STALE_OBSERVATION"
    INVALID_VALUE = "INVALID_VALUE"
    SCHEMA_MISMATCH = "SCHEMA_MISMATCH"
    SCHEMA_UNKNOWN = "SCHEMA_UNKNOWN"
    SCHEMA_INCOMPATIBLE = "SCHEMA_INCOMPATIBLE"
    # Transport-level
    INVALID_FRAME = "INVALID_FRAME"
    INVALID_DLC = "INVALID_DLC"
    INVALID_PAYLOAD_LENGTH = "INVALID_PAYLOAD_LENGTH"
    INVALID_IDENTIFIER = "INVALID_IDENTIFIER"
    UNSUPPORTED_FRAME_FORMAT = "UNSUPPORTED_FRAME_FORMAT"
    SCHEMA_TRANSPORT_MISMATCH = "SCHEMA_TRANSPORT_MISMATCH"


@dataclass(frozen=True)
class Diagnostic:
    """Observable diagnostic event with source identity via provenance."""

    diagnostic_type: DiagnosticType
    message: str
    timestamp_ns: int
    node_id: str = ""
    can_message_id: Optional[int] = None
    signal_id: Optional[str] = None
    sequence: Optional[int] = None
    provenance: Optional[Provenance] = None
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "diagnostic_type": self.diagnostic_type.value,
            "message": self.message,
            "timestamp_ns": self.timestamp_ns,
            "node_id": self.node_id,
        }
        if self.can_message_id is not None:
            d["can_message_id"] = self.can_message_id
            d["can_message_id_hex"] = f"0x{self.can_message_id:03X}"
        if self.signal_id is not None:
            d["signal_id"] = self.signal_id
        if self.sequence is not None:
            d["sequence"] = self.sequence
        if self.provenance is not None:
            d["provenance"] = self.provenance.to_dict()
        if self.detail:
            d["detail"] = dict(self.detail)
        return d
