"""Deterministic provenance for every observation.

Answers: which physical node/message produced this value?
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class Provenance:
    """Immutable provenance record attached to an Observation."""

    node_id: str
    can_message_id: int
    signal_id: str
    sequence: int
    timestamp_ns: int
    schema_version: str
    raw_data_hex: str = ""
    parent_observation_id: Optional[str] = None  # if transformed
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {
            "node_id": self.node_id,
            "can_message_id": self.can_message_id,
            "can_message_id_hex": f"0x{self.can_message_id:03X}",
            "signal_id": self.signal_id,
            "sequence": self.sequence,
            "timestamp_ns": self.timestamp_ns,
            "schema_version": self.schema_version,
            "raw_data_hex": self.raw_data_hex,
        }
        if self.parent_observation_id is not None:
            d["parent_observation_id"] = self.parent_observation_id
        if self.extra:
            d["extra"] = dict(self.extra)
        return d

    def identity_key(self) -> str:
        """Stable key for the producing (node, message, signal, sequence)."""
        return (
            f"{self.node_id}|0x{self.can_message_id:03X}|"
            f"{self.signal_id}|{self.sequence}"
        )
