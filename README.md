# CANtheon

**CANtheon converts distributed CAN 2.0 traffic into canonical, validated, provenance-preserving physical state for the MetaField ecosystem.**

## Boundary

| Layer        | Role                                              |
|--------------|---------------------------------------------------|
| **CANtheon** | physical state boundary (this repository)         |
| **CANgate**  | MetaField gateway (inside this repository)        |
| **MetaField**| field semantics (external)                        |
| **TensorGate**| numerical/tensor boundary (external)             |

CANtheon is **not** an ML framework and **not** a replacement for MetaField or TensorGate.

```
Physical modules
      │
      ▼
   CAN 2.0
      │
      ▼
┌─────────────────────┐
│      CANtheon       │
│  decode · normalize │
│  validate · stamp   │
│  sequence · quality │
│  identity · prove   │
└─────────┬───────────┘
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

## What CANtheon owns

- CAN frame ingestion
- Message decoding & signal extraction
- Engineering-unit conversion (scale / offset)
- Node / module identity
- Units, timestamps, sequence numbers
- Quality / state flags (`VALID`, `INVALID`, `STALE`, `OUT_OF_RANGE`, `DECODE_ERROR`)
- Validation (range, decode errors — never silent discard)
- Deterministic canonical observations
- Provenance
- Runtime event routing
- CAN-side diagnostics
- CANgate (MetaField-facing adapter surface)

## What CANtheon does **not** own

- MetaField field semantics
- TensorGate numerical / tensor semantics
- Machine-learning inference or model weights
- Physical waveform processing
- ESP-NOW or unrelated swarm transport
- Application-specific actuator logic / autonomous control authority

## Install

```bash
# from a clean checkout
python -m pip install -e ".[dev]"
```

Zero runtime dependencies. Tests need `pytest`.

## Canonical observation

Every observation carries:

| Field         | Meaning                                      |
|---------------|----------------------------------------------|
| `node_id`     | physical participant identity                |
| `message_id`  | CAN 11-bit ID                                |
| `signal_id`   | signal within the message                    |
| `value`       | engineering value                            |
| `unit`        | unit string (e.g. `°C`)                      |
| `timestamp_ns`| nanosecond timestamp                         |
| `sequence`    | monotonic sequence per runtime               |
| `quality`     | `VALID` / `OUT_OF_RANGE` / `DECODE_ERROR` … |
| `source`      | origin tag (`cantheon`)                      |
| `provenance`  | node, CAN ID, signal, sequence, schema, raw  |

Raw frames, decoded signals, and normalized observations remain **distinct**. No silent conversion.

## End-to-end example

```bash
python examples/live_loop.py
```

Path demonstrated:

```
simulated CAN frame
        ↓
CANtheon decoder
        ↓
normalized observation (°C)
        ↓
validation (incl. OUT_OF_RANGE preserved)
        ↓
provenance
        ↓
CANgate
        ↓
MetaField-compatible event boundary
```

Conceptual reverse (interface only — no autonomy):

```
canonical decision/output
        ↓
CANgate.encode_command(...)
        ↓
CAN message bytes
```

## Minimal host usage

```python
from cantheon import (
    CanFrame, Node, SchemaRegistry, Runtime, InMemorySink, CANgate
)

registry = SchemaRegistry()
registry.load_json("schemas/example_node.json")

node = Node(node_id="temp_sensor_01", name="Temperature Sensor")
runtime = Runtime(registry, node, sink=InMemorySink())
gate = CANgate(runtime)

# 25.0 °C as signed 16-bit tenths, little-endian
frame = CanFrame.from_id_and_bytes(0x100, bytes([0xFA, 0x00]))
observations = gate.ingest(frame)

for obs in observations:
    print(obs.value, obs.unit, obs.quality.value)
    print(obs.provenance.to_dict())

print(gate.health())
# events ready for MetaField adapter:
for event in gate.published:
    print(event.to_dict())
```

## Tests

```bash
python -m pytest -q
```

Coverage includes: frame construction, ID handling, payload decode, signed/unsigned extraction, scale/offset, endianness, units, range validation, invalid input, node identity, timestamps, sequence, provenance, observation serialization, CANgate ingest/emit, deterministic reprocessing.

## Schema versioning

Message/signal definitions live under `schemas/` and are versioned via `schema_version`. Load with `SchemaRegistry.load_json(...)`.

## Remaining integration boundaries

- **MetaField**: attach a real MetaField consumer to `CANgate.on_publish` or map `MetaFieldEvent` into the field substrate. CANtheon does not import or embed MetaField.
- **TensorGate**: once MetaField admits the observation as field state, TensorGate can consume the numerical boundary. CANtheon does not implement tensor semantics.

## License

MIT
