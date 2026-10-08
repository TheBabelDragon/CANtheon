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
- Sensor-neutral spatial / ToF observation families (v0.3)
- Deterministic spatial serialization and zone→point calibration

## What CANtheon does **not** own

- MetaField / TensorGate semantics
- Machine-learning inference
- Autonomous control authority
- Physical CAN-FD hardware drivers
- Vendor ToF / camera SDKs (reference adapters are host-only)

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

## Spatial / ToF Observations (v0.3)

CANtheon is **sensor-neutral**.  Spatial observations are a first-class,
typed family independent of Classical CAN / CAN-FD transport.

```
RAW SENSOR
     ↓
SENSOR OBSERVATION   (RANGE, TOF_ZONE, IMU, …)
     ↓
DERIVED SPATIAL DATA (POINT3D, …)
     ↓
GEOMETRY             (GEOMETRY_OBSERVATION)
```

### Observation families

| Kind | Purpose | Key fields |
|------|---------|------------|
| `RANGE` | Single range / distance | `range_mm`, status, confidence, optional zone |
| `TOF_ZONE` | One zone of a multizone ToF | zone_id/x/y, `range_mm`, signal, ambient |
| `POINT3D` | Cartesian point (derived) | `x/y/z_mm`, reference_frame_id, source_sequences |
| `IMU` | Inertial sample | ax/ay/az, gx/gy/gz, explicit unit enums |
| `GEOMETRY` | Derived primitive | geometry_type, parameters, source_sequences |

### Units, widths, validity

All wire encodings are **little-endian**, integer / fixed-point.  No floating-point on the wire.

| Field | Unit | Wire type | Notes |
|-------|------|-----------|-------|
| `range_mm` | millimetres | uint32 | `0xFFFFFFFF` = unavailable |
| `x/y/z_mm` | millimetres | int32 | signed |
| `confidence` | 0.01 % | uint16 | `0xFFFF` = unknown; `10000` = 100 % |
| `timestamp_ns` | nanoseconds | int64 | same convention as v0.2 |
| `sequence` | unitless | uint64 | source ordering |
| `signal_rate_kcps_x100` | kcps × 100 | int32 | −1 = unavailable |
| `status` | enum | int32 | VALID / INVALID / UNAVAILABLE / … |

Invalid or unavailable measurements are **never** silently converted to zero.
A genuine contact range of 0 mm remains `VALID` with `range_mm = 0`.

Every derived observation carries `source_sequences` so provenance answers:
*“Which source measurement produced this value?”*

Schema identity: `cantheon.spatial@0.3.0`.

### VL53L5CX reference adapter

An 8×8 multizone ToF source is represented by a **hardware-independent**
reference adapter (`cantheon.adapters.vl53l5cx`).  No vendor SDK is required;
synthetic frames are fully host-testable.

```python
from cantheon.adapters.vl53l5cx import (
    VL53L5CXAdapter, make_synthetic_8x8, default_forward_calibration,
)
from cantheon.spatial import encode_frame, zone_to_point3d

cal = default_forward_calibration(frame_id="tof0")
frame = make_synthetic_8x8(
    valid_ranges={0: 500, 36: 800, 63: 1200},
    invalid_zones=[1],
    sequence=42,
)
adapter = VL53L5CXAdapter(calibration=cal)

# 64 TOF_ZONE_OBSERVATION records
zones = adapter.produce(frame)

# selected POINT3D_OBSERVATION (valid zones only have VALID status)
points = adapter.produce_points(frame)

# optional GEOMETRY_OBSERVATION retains source sequences
```

An 8×8 ToF sensor is **not** a depth camera.  The adapter produces zone
ranges and optional calibrated points; it does not invent image semantics.

Future optical, IR, radar, or other physical sensors can emit the same
observation families without changing the core model.

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
