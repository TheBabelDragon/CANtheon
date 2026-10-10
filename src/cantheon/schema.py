"""Versioned schema registry for message/signal definitions.

v0.2: schema_id + schema_version on every registration,
capability discovery, compatibility checks.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from .capability import (
    MessageCapability,
    NodeCapability,
    SignalCapability,
)
from .schema_compat import (
    Compatibility,
    SchemaIdentity,
    check_compatibility,
)
from .signal import MessageDef, message_def_from_dict


class SchemaRegistry:
    """Maps CAN message IDs (and optional node binding) to MessageDef."""

    def __init__(self) -> None:
        self._by_id: dict[int, MessageDef] = {}
        self._node_bindings: dict[str, set[int]] = {}
        self._node_meta: dict[str, dict[str, Any]] = {}
        self.schema_version: str = "1.0"
        self.schema_id: str = ""

    @property
    def schema_identity(self) -> SchemaIdentity:
        return SchemaIdentity(
            schema_id=self.schema_id or "unknown",
            schema_version=self.schema_version,
        )

    def register(
        self,
        msg: MessageDef,
        node_id: Optional[str] = None,
        *,
        node_name: str = "",
        capabilities: tuple[str, ...] = (),
    ) -> None:
        if not msg.schema_id and self.schema_id:
            object.__setattr__(msg, "schema_id", self.schema_id)
        self._by_id[msg.message_id] = msg
        if node_id is not None:
            self._node_bindings.setdefault(node_id, set()).add(msg.message_id)
            meta = self._node_meta.setdefault(node_id, {
                "node_name": node_name or node_id,
                "capabilities": list(capabilities),
            })
            if node_name:
                meta["node_name"] = node_name
            if capabilities:
                meta["capabilities"] = list(capabilities)

    def get(self, message_id: int) -> Optional[MessageDef]:
        return self._by_id.get(message_id)

    def messages_for_node(self, node_id: str) -> list[MessageDef]:
        ids = self._node_bindings.get(node_id, set())
        return [self._by_id[i] for i in ids if i in self._by_id]

    def load_dict(
        self,
        data: dict[str, Any],
        node_id: Optional[str] = None,
    ) -> None:
        self.schema_version = str(data.get("schema_version", "1.0"))
        self.schema_id = str(data.get("schema_id", self.schema_id or ""))
        bound_node = node_id or data.get("node_id")
        node_name = str(data.get("node_name", bound_node or ""))
        caps = tuple(data.get("capabilities", ()) or ())
        for m in data.get("messages", []):
            if "schema_id" not in m and self.schema_id:
                m = dict(m)
                m["schema_id"] = self.schema_id
            if "schema_version" not in m:
                m = dict(m)
                m["schema_version"] = self.schema_version
            msg = message_def_from_dict(m)
            self.register(
                msg,
                node_id=bound_node,
                node_name=node_name,
                capabilities=caps,
            )

    def load_json(
        self,
        path: str | Path,
        node_id: Optional[str] = None,
    ) -> None:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.load_dict(data, node_id=node_id)

    def known_ids(self) -> list[int]:
        return sorted(self._by_id.keys())

    def check_schema(self, actual: SchemaIdentity) -> Compatibility:
        return check_compatibility(self.schema_identity, actual)

    def discover(self) -> list[NodeCapability]:
        """Alias for discover_capabilities (public discovery API)."""
        return self.discover_capabilities()

    def discover_capabilities(self) -> list[NodeCapability]:
        """Return capabilities for all known nodes."""
        node_ids = set(self._node_bindings.keys())
        if not node_ids:
            if self._by_id:
                return [self._build_capability(
                    "_unbound",
                    node_name="unbound",
                    message_ids=set(self._by_id.keys()),
                )]
            return []
        return [
            self._build_capability(nid, message_ids=self._node_bindings[nid])
            for nid in sorted(node_ids)
        ]

    def node_capabilities(self, node_id: str) -> Optional[NodeCapability]:
        if node_id not in self._node_bindings and node_id not in self._node_meta:
            return None
        ids = self._node_bindings.get(node_id, set())
        return self._build_capability(node_id, message_ids=ids)

    def _build_capability(
        self,
        node_id: str,
        *,
        node_name: str = "",
        message_ids: Optional[set[int]] = None,
    ) -> NodeCapability:
        meta = self._node_meta.get(node_id, {})
        name = node_name or meta.get("node_name", node_id)
        caps = tuple(meta.get("capabilities", ()))
        msgs: list[MessageCapability] = []
        for mid in sorted(message_ids or set()):
            mdef = self._by_id.get(mid)
            if mdef is None:
                continue
            sigs = tuple(
                SignalCapability(
                    signal_id=s.signal_id,
                    name=s.name,
                    unit=s.unit,
                    min_value=s.min_value,
                    max_value=s.max_value,
                )
                for s in mdef.signals
            )
            msgs.append(
                MessageCapability(
                    message_id=mdef.message_id,
                    name=mdef.name,
                    signals=sigs,
                    is_heartbeat=mdef.is_heartbeat,
                    has_sequence=mdef.sequence_signal() is not None
                    or mdef.sequence_width is not None,
                )
            )
        return NodeCapability(
            node_id=node_id,
            node_name=name,
            schema_id=self.schema_id or "unknown",
            schema_version=self.schema_version,
            messages=tuple(msgs),
            capabilities=caps,
        )


def load_schema(
    path: str | Path,
    node_id: Optional[str] = None,
) -> SchemaRegistry:
    reg = SchemaRegistry()
    reg.load_json(path, node_id=node_id)
    return reg
