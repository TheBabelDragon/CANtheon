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

## Shared Evidence Contract

Phase 1–2 foundation for the cross-repository evidence path:

- [`docs/SHARED_EVIDENCE_CONTRACT.md`](docs/SHARED_EVIDENCE_CONTRACT.md)
- [`docs/METAFIELD_INTEGRATION.md`](docs/METAFIELD_INTEGRATION.md)
- [`docs/CROSS_REPO_CONFORMANCE.md`](docs/CROSS_REPO_CONFORMANCE.md) — end-to-end smoke path

```bash
# Sibling checkouts of metafield, TensorGate, MultiFlow, aurora-swarm-btc:
python scripts/evidence_conformance_smoke.py
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
    CANgate, FixedClock,
)

registry = SchemaRegistry()
registry.load_json("schemas/example_node.json")
runtime = Runtime(registry, Node("temp_sensor_01", "Temp"),
                  sink=InMemorySink(), clock=FixedClock(0))
gate = CANgate(runtime)
frame = CanFrame.classical(0x100, bytes([0xFA, 0x00]))
gate.ingest(frame, ingest_timestamp_ns=1000)
```

## License

MIT
