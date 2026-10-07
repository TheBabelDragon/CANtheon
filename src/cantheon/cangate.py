"""CANgate — explicit boundary between CANtheon and MetaField.

CANgate owns the adapter/protocol surface. It does not embed MetaField
or TensorGate implementation. Real MetaField integration attaches later
without changing CAN normalization internals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .frame import CanFrame
from .observation import Observation, Quality
from .runtime import Runtime


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

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "node_id": self.node_id,
            "payload": dict(self.payload),
            "quality": self.quality,
            "sequence": self.sequence,
            "timestamp_ns": self.timestamp_ns,
            "provenance": dict(self.provenance),
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
        },
        quality=obs.quality.value,
        sequence=obs.sequence,
        timestamp_ns=obs.timestamp_ns,
        provenance=obs.provenance.to_dict(),
    )


class CANgate:
    """Gateway: ingest(frame) → observation(s) → publish → MetaFieldEvent.

    Also exposes health() for gateway status.
    Reverse path (canonical decision → CAN message) is stubbed as a
    clean interface only; no autonomous control authority in v0.1.
    """

    def __init__(self, runtime: Runtime) -> None:
        self.runtime = runtime
        self._published: list[MetaFieldEvent] = []
        self._publish_hooks: list[Callable[[MetaFieldEvent], None]] = []
        self._frames_in = 0
        self._obs_out = 0
        self._errors = 0

    def on_publish(self, callback: Callable[[MetaFieldEvent], None]) -> None:
        self._publish_hooks.append(callback)

    def ingest(
        self,
        frame: CanFrame,
        *,
        timestamp_ns: Optional[int] = None,
    ) -> list[Observation]:
        """Ingest one CAN frame; returns normalized + validated observations."""
        self._frames_in += 1
        observations = self.runtime.process(frame, timestamp_ns=timestamp_ns)
        for obs in observations:
            if obs.quality != Quality.VALID:
                self._errors += 1
            self.publish(obs)
        return observations

    def publish(self, observation: Observation) -> MetaFieldEvent:
        """Emit a MetaField-facing event for one observation."""
        event = observation_to_event(observation)
        self._published.append(event)
        self._obs_out += 1
        for h in self._publish_hooks:
            h(event)
        return event

    def health(self) -> dict[str, Any]:
        return {
            "gateway": "CANgate",
            "frames_in": self._frames_in,
            "observations_out": self._obs_out,
            "error_count": self._errors,
            "node": self.runtime.node.to_dict(),
            "sequence": self.runtime.sequence,
            "known_message_ids": self.runtime.registry.known_ids(),
        }

    @property
    def published(self) -> list[MetaFieldEvent]:
        return list(self._published)

    # --- reverse conceptual path (interface only, no autonomy) ---

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
        # Build a zeroed 8-byte buffer and pack signals that are present.
        # Minimal implementation: only supports little-endian unsigned for now.
        buf = bytearray(8)
        for sig in msg_def.signals:
            if sig.signal_id not in signal_values:
                continue
            eng = signal_values[sig.signal_id]
            # inverse of eng = raw * scale + offset
            if sig.scale == 0:
                continue
            raw = int(round((eng - sig.offset) / sig.scale))
            if sig.is_signed and raw < 0:
                raw = raw + (1 << sig.bit_length)
            # pack little-endian bits
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
