"""Deterministic frame → observation normalization.

raw CAN frame
  → message definition
  → signal extraction
  → engineering-unit conversion
  → canonical Observation
"""

from __future__ import annotations

import time
from typing import Optional

from .frame import CanFrame
from .observation import Observation, Quality
from .provenance import Provenance
from .schema import SchemaRegistry
from .signal import MessageDef, extract_signal


def _now_ns() -> int:
    return time.time_ns()


def normalize_frame(
    frame: CanFrame,
    registry: SchemaRegistry,
    *,
    node_id: str,
    sequence: int,
    timestamp_ns: Optional[int] = None,
    source: str = "cantheon",
) -> list[Observation]:
    """Decode and normalize all signals present in the frame.

    Returns a list of Observation (one per signal definition).
    If the message is unknown, returns a single DECODE_ERROR observation
    so the failure is observable rather than silent.
    """
    ts = timestamp_ns if timestamp_ns is not None else (
        frame.timestamp_ns if frame.timestamp_ns is not None else _now_ns()
    )
    msg_def: Optional[MessageDef] = registry.get(frame.can_id)

    if msg_def is None:
        prov = Provenance(
            node_id=node_id,
            can_message_id=frame.can_id,
            signal_id="__unknown__",
            sequence=sequence,
            timestamp_ns=ts,
            schema_version=registry.schema_version,
            raw_data_hex=frame.data.hex(),
        )
        return [
            Observation(
                node_id=node_id,
                message_id=frame.can_id,
                signal_id="__unknown__",
                value=float("nan"),
                unit="",
                timestamp_ns=ts,
                sequence=sequence,
                quality=Quality.DECODE_ERROR,
                source=source,
                provenance=prov,
                message_name="",
                signal_name="unknown",
                schema_version=registry.schema_version,
                extra={"reason": "no message definition for CAN ID"},
            )
        ]

    if msg_def.dlc is not None and frame.dlc != msg_def.dlc:
        # still attempt decode but mark quality later if needed
        pass

    observations: list[Observation] = []
    for sig in msg_def.signals:
        try:
            raw, eng = extract_signal(frame.data, sig)
            quality = Quality.VALID
            # range check is also performed in validate; we pre-set here
            if sig.min_value is not None and eng < sig.min_value:
                quality = Quality.OUT_OF_RANGE
            if sig.max_value is not None and eng > sig.max_value:
                quality = Quality.OUT_OF_RANGE

            prov = Provenance(
                node_id=node_id,
                can_message_id=frame.can_id,
                signal_id=sig.signal_id,
                sequence=sequence,
                timestamp_ns=ts,
                schema_version=msg_def.schema_version,
                raw_data_hex=frame.data.hex(),
            )
            observations.append(
                Observation(
                    node_id=node_id,
                    message_id=frame.can_id,
                    signal_id=sig.signal_id,
                    value=eng,
                    unit=sig.unit,
                    timestamp_ns=ts,
                    sequence=sequence,
                    quality=quality,
                    source=source,
                    provenance=prov,
                    raw_value=raw,
                    message_name=msg_def.name,
                    signal_name=sig.name,
                    schema_version=msg_def.schema_version,
                )
            )
        except ValueError as exc:
            prov = Provenance(
                node_id=node_id,
                can_message_id=frame.can_id,
                signal_id=sig.signal_id,
                sequence=sequence,
                timestamp_ns=ts,
                schema_version=msg_def.schema_version,
                raw_data_hex=frame.data.hex(),
            )
            observations.append(
                Observation(
                    node_id=node_id,
                    message_id=frame.can_id,
                    signal_id=sig.signal_id,
                    value=float("nan"),
                    unit=sig.unit,
                    timestamp_ns=ts,
                    sequence=sequence,
                    quality=Quality.DECODE_ERROR,
                    source=source,
                    provenance=prov,
                    message_name=msg_def.name,
                    signal_name=sig.name,
                    schema_version=msg_def.schema_version,
                    extra={"reason": str(exc)},
                )
            )
    return observations
