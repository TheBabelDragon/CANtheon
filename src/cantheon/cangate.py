"""CANgate — explicit boundary between CANtheon and MetaField.

CANgate owns the adapter/protocol surface. It does not embed MetaField
or TensorGate implementation. Real MetaField integration attaches later
without changing CAN normalization internals.

v0.2: lifecycle states, expanded health, diagnostics passthrough.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from .diagnostics import Diagnostic
from .frame import CanFrame
from .liveness import LivenessState
from .observation import Observation, Quality
from .runtime import Runtime
from .schema_compat import SchemaIdentity


class GateState(str, Enum):
    INITIALIZING = "INITIALIZING"
    READY = "READY"
    DEGRADED = "DEGRADED"
    ERROR = "ERROR"


@dataclass(frozen=True)
class MetaFieldEvent:
    """Clean MetaField-facing event/state boundary object.

    This is intentionally a plain data contract, not a live MetaField API.
    Downstream adapters map this into whatever MetaField expects.
    """

    kind: str  # "observation" | "health" | "diagnostic"
    node_id: str
    payload: dict[str, Any]
    quality: str
    sequence: int
    timestamp_ns: int
    provenance: dict[str, Any] = field(default_factory=dict)
    schema_id: str = ""
    schema_version: str = ""

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "node_id": self.node_id,
            "payload": dict(self.payload),
            "quality": self.quality,
            "sequence": self.sequence,
            "timestamp_ns": self.timestamp_ns,
            "provenance": dict(self.provenance),
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
        }


def observation_to_event(obs: Observation) -> MetaFieldEvent:
    return MetaFieldEvent(
        kind="observation",
        node_id=obs.node_id,
        payload={
            "message_id": obs.message_id,
            "signal_id": obs.signal_id,
            "value": obs.value,
            "unit": obs.unit,
            "raw_value": obs.raw_value,
            "message_name": obs.message_name,
            "signal_name": obs.signal_name,
            "schema_version": obs.schema_version,
            "schema_id": obs.schema_id,
            "ingest_timestamp_ns": obs.ingest_timestamp_ns,
            "source_timestamp_ns": obs.source_timestamp_ns,
        },
        quality=obs.quality.value,
        sequence=obs.sequence,
        timestamp_ns=obs.ingest_timestamp_ns or obs.timestamp_ns,
        provenance=obs.provenance.to_dict(),
        schema_id=obs.schema_id,
        schema_version=obs.schema_version,
    )


class CANgate:
    """Gateway: ingest(frame) → observation(s) → publish → MetaFieldEvent.

    Also exposes health() for gateway status.
    Reverse path (canonical decision → CAN message) is stubbed as a
    clean interface only; no autonomous control authority.
    """

    def __init__(self, runtime: Runtime) -> None:
        self.runtime = runtime
        self._published: list[MetaFieldEvent] = []
        self._publish_hooks: list[Callable[[MetaFieldEvent], None]] = []
        self._diag_hooks: list[Callable[[Diagnostic], None]] = []
        self._frames_in = 0
        self._obs_out = 0
        self._errors = 0
        self._unknown_messages = 0
        self._decode_failures = 0
        self._state = GateState.INITIALIZING
        self._state = GateState.READY

    def on_publish(self, callback: Callable[[MetaFieldEvent], None]) -> None:
        self._publish_hooks.append(callback)

    def on_diagnostic(self, callback: Callable[[Diagnostic], None]) -> None:
        self._diag_hooks.append(callback)

    def ingest(
        self,
        frame: CanFrame,
        *,
        timestamp_ns: Optional[int] = None,
        ingest_timestamp_ns: Optional[int] = None,
        source_timestamp_ns: Optional[int] = None,
    ) -> list[Observation]:
        """Ingest one CAN frame; returns normalized + validated observations."""
        self._frames_in += 1
        observations = self.runtime.process(
            frame,
            timestamp_ns=timestamp_ns,
            ingest_timestamp_ns=ingest_timestamp_ns,
            source_timestamp_ns=source_timestamp_ns,
        )
        for obs in observations:
            if obs.quality != Quality.VALID:
                self._errors += 1
                if obs.quality == Quality.DECODE_ERROR:
                    self._decode_failures += 1
            if obs.signal_id == "__unknown__":
                self._unknown_messages += 1
            self.publish(obs)
        # surface runtime diagnostics
        for d in self.runtime.diagnostics:
            for h in self._diag_hooks:
                h(d)
        if self._errors and self._state == GateState.READY:
            self._state = GateState.DEGRADED
        return observations

    def publish(self, observation: Observation) -> MetaFieldEvent:
        """Emit a MetaField-facing event for one observation."""
        event = observation_to_event(observation)
        self._published.append(event)
        self._obs_out += 1
        for h in self._publish_hooks:
            h(event)
        return event

    @property
    def state(self) -> GateState:
        liv = self.runtime.liveness_state
        if liv == LivenessState.TIMEOUT:
            return GateState.DEGRADED
        return self._state

    def health(self) -> dict[str, Any]:
        liv = self.runtime.liveness_state
        return {
            "gateway": "CANgate",
            "state": self.state.value,
            "frames_received": self._frames_in,
            "observations_emitted": self._obs_out,
            "diagnostics_emitted": len(self.runtime.diagnostics),
            "unknown_messages": self._unknown_messages,
            "decode_failures": self._decode_failures,
            "error_count": self._errors,
            # backward-compat aliases
            "frames_in": self._frames_in,
            "observations_out": self._obs_out,
            "node": self.runtime.node.to_dict(),
            "liveness": liv.value,
            "active_nodes": (
                [self.runtime.node.node_id]
                if liv == LivenessState.ALIVE
                else []
            ),
            "stale_nodes": (
                [self.runtime.node.node_id]
                if liv in (LivenessState.STALE, LivenessState.TIMEOUT)
                else []
            ),
            "sequence": self.runtime.sequence,
            "known_message_ids": self.runtime.registry.known_ids(),
            "schema_id": self.runtime.registry.schema_id,
            "schema_version": self.runtime.registry.schema_version,
        }

    @property
    def published(self) -> list[MetaFieldEvent]:
        return list(self._published)

    def encode_command(
        self,
        message_id: int,
        signal_values: dict[str, float],
    ) -> Optional[CanFrame]:
        """Conceptual reverse: canonical decision → CAN message bytes.

        Returns a CanFrame if the message is known and all signals fit;
        otherwise None. Does NOT transmit. No control authority.
        """
        msg_def = self.runtime.registry.get(message_id)
        if msg_def is None:
            return None
        buf = bytearray(8)
        for sig in msg_def.signals:
            if sig.signal_id not in signal_values:
                continue
            eng = signal_values[sig.signal_id]
            if sig.scale == 0:
                continue
            raw = int(round((eng - sig.offset) / sig.scale))
            if sig.is_signed and raw < 0:
                raw = raw + (1 << sig.bit_length)
            for i in range(sig.bit_length):
                bit_pos = sig.start_bit + i
                byte_idx = bit_pos // 8
                bit_in_byte = bit_pos % 8
                if byte_idx >= 8:
                    return None
                if (raw >> i) & 1:
                    buf[byte_idx] |= 1 << bit_in_byte
                else:
                    buf[byte_idx] &= ~(1 << bit_in_byte)
        dlc = msg_def.dlc if msg_def.dlc is not None else 8
        return CanFrame(can_id=message_id, data=bytes(buf[:dlc]))
