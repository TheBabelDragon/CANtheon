# CANtheon

**CANtheon converts distributed Classical CAN and CAN-FD traffic into canonical, validated, provenance-preserving physical state for the MetaField ecosystem.**

CANtheon owns trustworthy physical-state translation. It does **not** own field semantics, tensor semantics, inference, or autonomous control.

CANtheon supports **Classical CAN and CAN-FD** at the transport boundary, with CAN-FD up to 64-byte payloads. The canonical observation model is transport-independent.

## Architecture

```
Physical Nodes
      │
      ▼
 Classical CAN / CAN-FD
      │
      ▼
   CANtheon
      │
      ├── Frame decoding
      ├── FD transport handling
      ├── Normalization
      ├── Validation
      ├── Provenance
      ├── Clock
      ├── Sequence
      ├── Diagnostics
      ├── Discovery
      └── Replay
      │
      ▼
    CANgate
      │
      ▼
   MetaField
      │
      ▼
  TensorGate
```

## Boundary

| Layer | Role |
|-------|------|
| **CANtheon** | physical state boundary (this repository) |
| **CANgate** | MetaField gateway (inside this repository) |
| **MetaField Adapter** | protocol interface (`adapters.metafield`) |
| **MetaField** | field semantics (external) |
| **TensorGate** | numerical/tensor boundary (external) |

## Transport

| Format | ID | Payload |
|--------|-----|---------|
| Classical CAN | 11-bit or 29-bit | 0–8 bytes |
| CAN-FD | 11-bit or 29-bit | 0,1,2,3,4,5,6,7,8,12,16,20,24,32,48,64 bytes |

FD flags (BRS, ESI) live at the frame layer only. Observations remain transport-independent.

```python
from cantheon import CanFrame, FrameFormat

# Classical (default, backward compatible)
f = CanFrame.classical(0x100, b"\xFA\x00")

# CAN-FD 64-byte with BRS
f = CanFrame.can_fd(0x200, bytes(64), brs=True, extended=True)
```

## What CANtheon owns

- Classical CAN and CAN-FD frame ingestion
- Signal extraction (scale / offset / endian / signed) across full FD payload
- Node identity, capability discovery, transport capability reporting
- Dual timestamps (source vs ingest)
- Sequence tracking, quality flags, diagnostics
- Node liveness, deterministic record/replay
- Schema identity and transport-aware schema contracts
- CANgate lifecycle and health

## What CANtheon does **not** own

- MetaField / TensorGate semantics
- Machine-learning inference
- Autonomous control authority
- Physical CAN-FD hardware drivers

## Time Semantics

| Field | Meaning |
|-------|---------|
| `source_timestamp_ns` | when the originating node says the measurement occurred (`None` if unavailable) |
| `ingest_timestamp_ns` | when CANtheon accepted the frame |
| `sequence` | source/message ordering identifier |

## Deterministic Replay

Recorded streams (including full CAN-FD transport metadata) replay without hardware:

```
live frames → Recorder → JSONL → Replay.run(runtime)
→ identical canonical observations + diagnostics
```

## Install

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
```

## Quick start

```python
from cantheon import (
    CanFrame, Node, SchemaRegistry, Runtime, InMemorySink,
    CANgate, FixedClock, Recorder,
)

registry = SchemaRegistry()
registry.load_json("schemas/example_node.json")

clock = FixedClock(0)
runtime = Runtime(registry, Node("temp_sensor_01", "Temp"),
                  sink=InMemorySink(), clock=clock)
gate = CANgate(runtime)

# Classical
frame = CanFrame.classical(0x100, bytes([0xFA, 0x00]))
gate.ingest(frame, ingest_timestamp_ns=1000)

# CAN-FD
fd = CanFrame.can_fd(0x200, bytes(32), brs=True)
```

## Remaining integration boundary

Implement `MetaFieldAdapter` outside this repo; wire to `CANgate.on_publish`. No MetaField/TensorGate code in CANtheon.

## License

MIT
