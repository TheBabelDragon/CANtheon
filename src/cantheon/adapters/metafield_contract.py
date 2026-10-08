"""Deterministic MetaField boundary contract — host-side, dependency-free.

Converts CANtheon canonical objects into a stable, JSON-serializable,
replayable envelope that a MetaField consumer can turn into FieldObservation
without CANtheon importing MetaField or TensorGate.

Schema identity: cantheon.metafield_boundary@0.3.0

The envelope deliberately retains transport/provenance detail that
MetaField's higher-level FieldObservation abstracts away.
"""

from __future__ import annotations

from typing import Any, Optional

from ..cangate import MetaFieldEvent
from ..diagnostics import Diagnostic
from ..observation import Observation, Quality
from ..schema_compat import Compatibility, SchemaIdentity, check_compatibility

# ---------------------------------------------------------------------------
# Contract identity
# ---------------------------------------------------------------------------

BOUNDARY_SCHEMA_ID = "cantheon.metafield_boundary"
BOUNDARY_SCHEMA_VERSION = "0.3.0"
BOUNDARY_SCHEMA = SchemaIdentity(BOUNDARY_SCHEMA_ID, BOUNDARY_SCHEMA_VERSION)

# Quality values that must never be silently rewritten to a "good" zero.
QUALITY_VALUES = frozenset(q.value for q in Quality)


class BoundaryError(Exception):
    """Raised when a consumer declares an incompatible schema contract."""

    def __init__(self, message: str, *, expected: SchemaIdentity, actual: SchemaIdentity):
        super().__init__(message)
        self.expected = expected
        self.actual = actual


def assert_compatible(
    consumer_expected: SchemaIdentity,
    *,
    producer: SchemaIdentity = BOUNDARY_SCHEMA,
) -> Compatibility:
    """Fail-closed compatibility check for the boundary contract.

    Returns Compatibility.COMPATIBLE on success.
    Raises BoundaryError on INCOMPATIBLE.
    Returns UNKNOWN only when identities are missing (caller may still reject).
    """
    result = check_compatibility(consumer_expected, producer)
    if result == Compatibility.INCOMPATIBLE:
        raise BoundaryError(
            f"schema incompatible: expected {consumer_expected}, "
            f"producer offers {producer}",
            expected=consumer_expected,
            actual=producer,
        )
    return result


# ---------------------------------------------------------------------------
# Envelope builders (pure, deterministic, no wall-clock)
# ---------------------------------------------------------------------------

def _sorted_dict(d: dict[str, Any]) -> dict[str, Any]:
    """Stable key order for deterministic JSON."""
    return {k: d[k] for k in sorted(d.keys())}


def observation_to_boundary(obs: Observation) -> dict[str, Any]:
    """Observation → MetaField-compatible physical observation envelope.

    Preserves dual timestamps, quality, provenance, raw frame identity.
    Never collapses INVALID/OUT_OF_RANGE/DECODE_ERROR into a silent zero.
    """
    quality = obs.quality.value if isinstance(obs.quality, Quality) else str(obs.quality)
    if quality not in QUALITY_VALUES:
        quality = Quality.INVALID.value

    payload = {
        "message_id": obs.message_id,
        "message_id_hex": f"0x{obs.message_id:03X}",
        "signal_id": obs.signal_id,
        "value": obs.value,
        "unit": obs.unit,
        "raw_value": obs.raw_value,
        "message_name": obs.message_name,
        "signal_name": obs.signal_name,
        "source": obs.source,
    }
    # extra is optional and must remain ordered for determinism
    if obs.extra:
        payload["extra"] = _sorted_dict(dict(obs.extra))

    envelope: dict[str, Any] = {
        "kind": "observation",
        "boundary_schema_id": BOUNDARY_SCHEMA_ID,
        "boundary_schema_version": BOUNDARY_SCHEMA_VERSION,
        "node_id": obs.node_id,
        "payload": payload,
        "quality": quality,
        "sequence": obs.sequence,
        "ingest_timestamp_ns": int(obs.ingest_timestamp_ns),
        "source_timestamp_ns": (
            int(obs.source_timestamp_ns)
            if obs.source_timestamp_ns is not None
            else None
        ),
        # compatibility alias (v0.2)
        "timestamp_ns": int(obs.ingest_timestamp_ns or obs.timestamp_ns),
        "schema_id": obs.schema_id,
        "schema_version": obs.schema_version,
        "provenance": obs.provenance.to_dict() if obs.provenance else {},
    }
    return envelope


def diagnostic_to_boundary(diag: Diagnostic) -> dict[str, Any]:
    """Diagnostic → first-class downstream representation."""
    d = diag.to_dict()
    envelope: dict[str, Any] = {
        "kind": "diagnostic",
        "boundary_schema_id": BOUNDARY_SCHEMA_ID,
        "boundary_schema_version": BOUNDARY_SCHEMA_VERSION,
        "node_id": diag.node_id,
        "payload": {
            "diagnostic_type": d.get("diagnostic_type"),
            "message": d.get("message"),
            "can_message_id": d.get("can_message_id"),
            "can_message_id_hex": d.get("can_message_id_hex"),
            "signal_id": d.get("signal_id"),
            "sequence": d.get("sequence"),
            "detail": _sorted_dict(d.get("detail") or {}),
        },
        "quality": "DIAGNOSTIC",
        "sequence": diag.sequence if diag.sequence is not None else 0,
        "ingest_timestamp_ns": int(diag.timestamp_ns),
        "source_timestamp_ns": None,
        "timestamp_ns": int(diag.timestamp_ns),
        "schema_id": "",
        "schema_version": "",
        "provenance": (
            diag.provenance.to_dict() if diag.provenance is not None else {}
        ),
    }
    # strip Nones from payload for cleaner JSON
    envelope["payload"] = {
        k: v for k, v in envelope["payload"].items() if v is not None
    }
    return envelope


def health_to_boundary(health: dict[str, Any]) -> dict[str, Any]:
    """CANgate / Runtime health → stable health envelope.

    Does not invent a second liveness implementation; consumes the dict
    already produced by CANgate.health() / Runtime.
    """
    # Preserve known keys in deterministic order
    known = [
        "gateway", "state", "frames_received", "observations_emitted",
        "diagnostics_emitted", "unknown_messages", "decode_failures",
        "error_count", "frames_in", "observations_out", "node", "liveness",
        "active_nodes", "stale_nodes", "sequence", "known_message_ids",
        "schema_id", "schema_version",
    ]
    payload: dict[str, Any] = {}
    for k in known:
        if k in health:
            payload[k] = health[k]
    # any additional keys, sorted
    for k in sorted(health.keys()):
        if k not in payload:
            payload[k] = health[k]

    return {
        "kind": "health",
        "boundary_schema_id": BOUNDARY_SCHEMA_ID,
        "boundary_schema_version": BOUNDARY_SCHEMA_VERSION,
        "node_id": (health.get("node") or {}).get("node_id", ""),
        "payload": payload,
        "quality": health.get("state", "READY"),
        "sequence": int(health.get("sequence") or 0),
        "ingest_timestamp_ns": 0,  # health is instantaneous; no wall clock injected
        "source_timestamp_ns": None,
        "timestamp_ns": 0,
        "schema_id": health.get("schema_id", ""),
        "schema_version": health.get("schema_version", ""),
        "provenance": {},
    }


def event_to_boundary(event: MetaFieldEvent) -> dict[str, Any]:
    """MetaFieldEvent → full boundary envelope.

    Ensures dual timestamps and all identity fields survive the hop.
    """
    payload = dict(event.payload)
    # Prefer explicit dual timestamps if present in payload; fall back to event
    ingest = payload.get("ingest_timestamp_ns")
    if ingest is None:
        ingest = event.timestamp_ns
    source = payload.get("source_timestamp_ns")

    envelope: dict[str, Any] = {
        "kind": event.kind,
        "boundary_schema_id": BOUNDARY_SCHEMA_ID,
        "boundary_schema_version": BOUNDARY_SCHEMA_VERSION,
        "node_id": event.node_id,
        "payload": payload,
        "quality": event.quality,
        "sequence": event.sequence,
        "ingest_timestamp_ns": int(ingest) if ingest is not None else 0,
        "source_timestamp_ns": int(source) if source is not None else None,
        "timestamp_ns": int(event.timestamp_ns),
        "schema_id": event.schema_id,
        "schema_version": event.schema_version,
        "provenance": dict(event.provenance) if event.provenance else {},
    }
    return envelope


def observation_event_to_boundary(event: MetaFieldEvent) -> dict[str, Any]:
    """Convenience: observation-kind MetaFieldEvent → boundary envelope."""
    if event.kind != "observation":
        raise ValueError(f"expected kind=observation, got {event.kind!r}")
    return event_to_boundary(event)


# ---------------------------------------------------------------------------
# JSON helpers (deterministic)
# ---------------------------------------------------------------------------

def to_jsonable(envelope: dict[str, Any]) -> dict[str, Any]:
    """Return a pure-JSON-serializable copy with stable key ordering."""
    import json
    # round-trip through sorted keys to guarantee determinism
    return json.loads(json.dumps(envelope, sort_keys=True, default=str))


def envelope_canonical_key(envelope: dict[str, Any]) -> str:
    """Stable identity key for equality / replay checks."""
    kind = envelope.get("kind", "")
    node = envelope.get("node_id", "")
    seq = envelope.get("sequence", 0)
    quality = envelope.get("quality", "")
    payload = envelope.get("payload") or {}
    sig = payload.get("signal_id", "")
    mid = payload.get("message_id", "")
    val = payload.get("value", "")
    return f"{kind}|{node}|{mid}|{sig}|{seq}|{val}|{quality}"
