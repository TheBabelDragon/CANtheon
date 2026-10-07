"""Versioned schema registry for message/signal definitions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from .signal import MessageDef, message_def_from_dict


class SchemaRegistry:
    """Maps CAN message IDs (and optional node binding) to MessageDef."""

    def __init__(self) -> None:
        self._by_id: dict[int, MessageDef] = {}
        self._node_bindings: dict[str, set[int]] = {}  # node_id → message_ids
        self.schema_version: str = "1.0"

    def register(self, msg: MessageDef, node_id: Optional[str] = None) -> None:
        self._by_id[msg.message_id] = msg
        if node_id is not None:
            self._node_bindings.setdefault(node_id, set()).add(msg.message_id)

    def get(self, message_id: int) -> Optional[MessageDef]:
        return self._by_id.get(message_id)

    def messages_for_node(self, node_id: str) -> list[MessageDef]:
        ids = self._node_bindings.get(node_id, set())
        return [self._by_id[i] for i in ids if i in self._by_id]

    def load_dict(self, data: dict[str, Any], node_id: Optional[str] = None) -> None:
        """Load a schema document.

        Expected shape:
        {
          "schema_version": "1.0",
          "node_id": "temp_sensor_01",   # optional
          "messages": [ { message_id, name, signals: [...] }, ... ]
        }
        """
        self.schema_version = str(data.get("schema_version", "1.0"))
        bound_node = node_id or data.get("node_id")
        for m in data.get("messages", []):
            msg = message_def_from_dict(m)
            self.register(msg, node_id=bound_node)

    def load_json(self, path: str | Path, node_id: Optional[str] = None) -> None:
        p = Path(path)
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
        self.load_dict(data, node_id=node_id)

    def known_ids(self) -> list[int]:
        return sorted(self._by_id.keys())


def load_schema(path: str | Path, node_id: Optional[str] = None) -> SchemaRegistry:
    reg = SchemaRegistry()
    reg.load_json(path, node_id=node_id)
    return reg
