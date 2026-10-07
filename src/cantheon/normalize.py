"""Deterministic frame → observation normalization.

v0.2: dual timestamps, schema identity, sequence signal extraction.
"""

from __future__ import annotations

from typing import Optional

from .frame import CanFrame
from .observation import Observation, Quality
from .provenance import Provenance
from .schema import SchemaRegistry
from .signal import MessageDef, extract_signal


def normalize_frame(
    frame: CanFrame,
    registry: SchemaRegistry,
    *,
    node_id: str,
    sequence: int,
    ingest_timestamp_ns: Optional[int] = None,
    source_timestamp_ns: Optional[int] = None,
    timestamp_ns: Optional[int] = None,
    source: str = "cantheon",
) -> list[Observation]:
    if ingest_timestamp_ns is None:
        ingest_timestamp_ns = timestamp_ns if timestamp_ns is not None else 0
    src_ts = source_timestamp_ns
    if src_ts is None and frame.timestamp_ns is not None:
        src_ts = frame.timestamp_ns
    if src_ts is None and timestamp_ns is not None and ingest_timestamp_ns != timestamp_ns:
        src_ts = timestamp_ns

    msg_def: Optional[MessageDef] = registry.get(frame.can_id)
    schema_id = registry.schema_id
    schema_version = registry.schema_version

    if msg_def is None:
        prov = Provenance(
            node_id=node_id,
            can_message_id=frame.can_id,
            signal_id="__unknown__",
            sequence=sequence,
            timestamp_ns=ingest_timestamp_ns,
            schema_version=schema_version,
            schema_id=schema_id,
            raw_data_hex=frame.data.hex(),
        )
        return [
            Observation(
                node_id=node_id,
                message_id=frame.can_id,
                signal_id="__unknown__",
                value=float("nan"),
                unit="",
                timestamp_ns=ingest_timestamp_ns,
                ingest_timestamp_ns=ingest_timestamp_ns,
                source_timestamp_ns=src_ts,
                sequence=sequence,
                quality=Quality.DECODE_ERROR,
                source=source,
                provenance=prov,
                message_name="",
                signal_name="unknown",
                schema_version=schema_version,
                schema_id=schema_id,
                extra={"reason": "no message definition for CAN ID"},
            )
        ]

    schema_id = msg_def.schema_id or schema_id
    schema_version = msg_def.schema_version or schema_version

    effective_sequence = sequence
    seq_sig = msg_def.sequence_signal()
    if seq_sig is not None:
        try:
            raw_seq, _ = extract_signal(frame.data, seq_sig)
            effective_sequence = int(raw_seq)
        except ValueError:
            pass

    observations: list[Observation] = []
    for sig in msg_def.signals:
        try:
            raw, eng = extract_signal(frame.data, sig)
            quality = Quality.VALID
            if sig.min_value is not None and eng < sig.min_value:
                quality = Quality.OUT_OF_RANGE
            if sig.max_value is not None and eng > sig.max_value:
                quality = Quality.OUT_OF_RANGE

            prov = Provenance(
                node_id=node_id,
                can_message_id=frame.can_id,
                signal_id=sig.signal_id,
                sequence=effective_sequence,
                timestamp_ns=ingest_timestamp_ns,
                schema_version=schema_version,
                schema_id=schema_id,
                raw_data_hex=frame.data.hex(),
            )
            observations.append(
                Observation(
                    node_id=node_id,
                    message_id=frame.can_id,
                    signal_id=sig.signal_id,
                    value=eng,
                    unit=sig.unit,
                    timestamp_ns=ingest_timestamp_ns,
                    ingest_timestamp_ns=ingest_timestamp_ns,
                    source_timestamp_ns=src_ts,
                    sequence=effective_sequence,
                    quality=quality,
                    source=source,
                    provenance=prov,
                    raw_value=raw,
                    message_name=msg_def.name,
                    signal_name=sig.name,
                    schema_version=schema_version,
                    schema_id=schema_id,
                )
            )
        except ValueError as exc:
            prov = Provenance(
                node_id=node_id,
                can_message_id=frame.can_id,
                signal_id=sig.signal_id,
                sequence=effective_sequence,
                timestamp_ns=ingest_timestamp_ns,
                schema_version=schema_version,
                schema_id=schema_id,
                raw_data_hex=frame.data.hex(),
            )
            observations.append(
                Observation(
                    node_id=node_id,
                    message_id=frame.can_id,
                    signal_id=sig.signal_id,
                    value=float("nan"),
                    unit=sig.unit,
                    timestamp_ns=ingest_timestamp_ns,
                    ingest_timestamp_ns=ingest_timestamp_ns,
                    source_timestamp_ns=src_ts,
                    sequence=effective_sequence,
                    quality=Quality.DECODE_ERROR,
                    source=source,
                    provenance=prov,
                    message_name=msg_def.name,
                    signal_name=sig.name,
                    schema_version=schema_version,
                    schema_id=schema_id,
                    extra={"reason": str(exc)},
                )
            )
    return observations
