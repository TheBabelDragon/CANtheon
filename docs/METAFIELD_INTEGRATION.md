# MetaField Integration Boundary

**CANtheon remains independent of MetaField and TensorGate implementation.**

This document describes the host-side, deterministic contract that lets
MetaField consume CANtheon physical state without CANtheon importing
MetaField classes or network transports.

## Three-layer ownership

| Layer | Repository | Owns |
|-------|------------|------|
| **CANtheon** | this repo | physical-state truth: CAN/CAN-FD ingestion, decode, normalize, validate, dual timestamps, sequence, quality, provenance, diagnostics, liveness, replay, transport/schema contracts |
| **CANgate** | this repo (`cangate.py`) | boundary/lifecycle/event gateway; emits `MetaFieldEvent` |
| **MetaField** | external | field semantics, `FieldObservation` construction, memory, geometry, prediction, attractors |
| **TensorGate** | external | numerical/tensor representation and downstream transforms |

## Intended runtime path

```
Physical / CAN node
        ↓
CANtheon Runtime          (decode → normalize → validate → provenance)
        ↓
Observation / Diagnostic
        ↓
CANgate                   (lifecycle, health, publish hooks)
        ↓
MetaFieldEvent
        ↓
metafield_contract        (deterministic JSON envelope)
        ↓
MetaField FieldObservation   (constructed by MetaField, not by CANtheon)
        ↓
TensorGate
```

CANtheon **never** imports MetaField or TensorGate.
MetaField is responsible for turning the boundary envelope into its own
`FieldObservation`.

## Boundary schema

```
schema_id:      cantheon.metafield_boundary
schema_version: 0.3.0
```

Location: `cantheon.adapters.metafield_contract`

### Envelope kinds

| kind | source | notes |
|------|--------|-------|
| `observation` | `Observation` / `MetaFieldEvent` | dual timestamps, quality, provenance, raw identity |
| `diagnostic` | `Diagnostic` | first-class; never discarded |
| `health` | `CANgate.health()` | gateway state, liveness, counters, schema identity |

### Dual timestamps (mandatory)

| Field | Meaning |
|-------|---------|
| `source_timestamp_ns` | when the originating node claims the measurement occurred (`null` if unavailable) |
| `ingest_timestamp_ns` | when CANtheon accepted the frame |
| `timestamp_ns` | v0.2 compatibility alias (prefers ingest) |

Downstream code **must** prefer the explicit dual fields.

### Quality (fail-closed)

Values are never silently rewritten:

- `VALID`
- `INVALID`
- `STALE`
- `OUT_OF_RANGE`
- `DECODE_ERROR`

A decode-error or out-of-range observation remains distinguishable from a
legitimate zero value.

### Schema compatibility

Consumers declare an expected `SchemaIdentity`.  
`assert_compatible()` is **fail-closed**:

- same id + compatible version → `COMPATIBLE`
- different id or major mismatch → raises `BoundaryError`
- missing / unknown → `UNKNOWN` (caller decides)

No automatic mutation or silent downgrade of schema identity.

## Adapter Protocol

`cantheon.adapters.metafield.MetaFieldAdapter` is a pure `Protocol`:

```python
def on_observation(self, observation: Observation) -> None: ...
def on_diagnostic(self, diagnostic: Diagnostic) -> None: ...
def on_event(self, event: MetaFieldEvent) -> None: ...
def health(self) -> dict[str, Any]: ...
```

Implementations live **outside** CANtheon. Wire them via
`CANgate.on_publish` / `CANgate.on_diagnostic` or by consuming the
JSON envelopes from `metafield_contract`.

## What this milestone does **not** include

- No Redis / HTTP / WebSocket / MQTT / sockets / brokers
- No control authority (MetaField → CANtheon → physical transmit)
- No hardware CAN drivers or vendor SDKs
- No MetaField / TensorGate imports inside CANtheon core

`encode_command()` remains a non-transmitting conceptual reverse path only.

## Example

```bash
python examples/metafield_boundary.py
```

Produces JSON envelopes for observation, diagnostic, and health without
any MetaField dependency.

## Replay

The same boundary conversion is exercised by deterministic replay.
No wall-clock timestamps are generated inside the converter; all times
come from the recorded / injected dual timestamps.
