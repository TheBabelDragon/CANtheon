# Shared Evidence Contract — Phase 1 (CANtheon)

**Status:** Implemented on this branch (v0.3.x foundation).

CANtheon is the transport- and evidence-foundation for the shared, versioned evidence path:

```
CANtheon → CANgate → MetaField → TensorGate → MultiFlow → Aurora Mesh
```

## What this repository owns

- Classical CAN + CAN-FD transport (11/29-bit IDs, DLC, BRS/ESI, payload ≤ 64 B)
- Canonical observation production with dual timestamps, sequence, quality, provenance
- Deterministic record/replay that preserves full transport metadata
- Schema identity + fail-closed compatibility
- Host-side, dependency-free boundary envelope (`cantheon.metafield_boundary@0.3.0`)

## Canonical evidence envelope (minimum fields)

| Field | Meaning |
|-------|---------|
| `schema_id` / `schema_version` (or boundary schema) | Contract identity |
| `node_id` / source identity | Who produced the measurement |
| `source_timestamp_ns` | When the node claims the measurement occurred (`null` if unavailable) |
| `ingest_timestamp_ns` | When CANtheon accepted the frame |
| `sequence` | Source ordering identifier |
| `quality` | VALID / INVALID / STALE / OUT_OF_RANGE / DECODE_ERROR (never silently rewritten) |
| `provenance` | Node, message, signal, sequence, raw identity, optional parent |
| payload / frame identity | Raw data, units, value, transport metadata where relevant |

Serialization is deterministic where the data and format permit. Missing values are explicit (`null` / omitted), never fabricated.

## Architectural rules (enforced)

- CANtheon **must not** import MetaField or TensorGate.
- Corrections appear as new records or explicit superseding references; historical evidence is not rewritten.
- Unsupported schema versions and invalid transport combinations fail closed.

## Downstream hand-off

See `docs/METAFIELD_INTEGRATION.md` and `cantheon.adapters.metafield_contract`.

Consumers map the boundary envelope into their own types (FieldObservation, tensor lineage, schedule decisions, mesh objects). CANtheon stops at the physical-state + evidence boundary.

## Verification

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
```

All transport, envelope, record/replay, schema, and boundary tests must pass before this foundation is considered ready for CANgate / MetaField integration work.
