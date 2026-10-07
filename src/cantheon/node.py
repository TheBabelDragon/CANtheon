"""Physical node / module identity.

CAN IDs identify traffic/messages.
Node identity identifies the physical participant.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Node:
    """Explicit physical participant in the CAN network."""

    node_id: str
    name: str
    capabilities: tuple[str, ...] = ()
    schema_version: str = "1.0"
    health: str = "UNKNOWN"  # UNKNOWN | OK | DEGRADED | OFFLINE
    last_seen_ns: Optional[int] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def touch(self, timestamp_ns: int) -> None:
        self.last_seen_ns = timestamp_ns
        if self.health == "UNKNOWN":
            self.health = "OK"

    def mark_offline(self) -> None:
        self.health = "OFFLINE"

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "name": self.name,
            "capabilities": list(self.capabilities),
            "schema_version": self.schema_version,
            "health": self.health,
            "last_seen_ns": self.last_seen_ns,
            "metadata": dict(self.metadata),
        }
