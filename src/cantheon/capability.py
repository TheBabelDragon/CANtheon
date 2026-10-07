"""Capability discovery — introspection/data-model, not a network protocol."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class SignalCapability:
    signal_id: str
    name: str
    unit: str = ""
    min_value: Optional[float] = None
    max_value: Optional[float] = None

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "signal_id": self.signal_id,
            "name": self.name,
            "unit": self.unit,
        }
        if self.min_value is not None:
            d["min_value"] = self.min_value
        if self.max_value is not None:
            d["max_value"] = self.max_value
        return d


@dataclass(frozen=True)
class MessageCapability:
    message_id: int
    name: str
    signals: tuple[SignalCapability, ...] = ()
    is_heartbeat: bool = False
    has_sequence: bool = False

    def to_dict(self) -> dict:
        return {
            "message_id": self.message_id,
            "message_id_hex": f"0x{self.message_id:03X}",
            "name": self.name,
            "signals": [s.to_dict() for s in self.signals],
            "is_heartbeat": self.is_heartbeat,
            "has_sequence": self.has_sequence,
        }


@dataclass
class NodeCapability:
    """What a node exposes — discovery introspection."""

    node_id: str
    node_name: str
    schema_id: str
    schema_version: str
    messages: tuple[MessageCapability, ...] = ()
    capabilities: tuple[str, ...] = ()
    last_seen_ns: Optional[int] = None
    health: str = "UNKNOWN"  # UNKNOWN | OK | DEGRADED | OFFLINE | ALIVE | STALE | TIMEOUT
    # Transport capabilities (declared, not auto-invented)
    supported_frame_formats: tuple[str, ...] = ("CLASSICAL_CAN", "CAN_FD")
    supported_identifier_formats: tuple[str, ...] = ("STANDARD_11", "EXTENDED_29")
    max_payload_size: int = 64

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "node_name": self.node_name,
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "messages": [m.to_dict() for m in self.messages],
            "capabilities": list(self.capabilities),
            "last_seen_ns": self.last_seen_ns,
            "health": self.health,
            "supported_frame_formats": list(self.supported_frame_formats),
            "supported_identifier_formats": list(self.supported_identifier_formats),
            "max_payload_size": self.max_payload_size,
        }
