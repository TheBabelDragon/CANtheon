# CANtheon schemas

Versioned message/signal definitions for physical nodes. Schemas may constrain transport (Classical CAN vs CAN-FD, ID format, max payload).

## Document shape

```json
{
  "schema_id": "temp_sensor.v1",
  "schema_version": "1.0",
  "node_id": "temp_sensor_01",
  "node_name": "Temperature Sensor Module",
  "capabilities": ["temperature"],
  "messages": [
    {
      "message_id": 0x100,
      "name": "TemperatureStatus",
      "dlc": 2,
      "frame_format": "CLASSICAL_CAN",
      "identifier_format": "STANDARD",
      "max_payload": 8,
      "schema_id": "temp_sensor.v1",
      "schema_version": "1.0",
      "is_heartbeat": false,
      "sequence_width": null,
      "signals": [
        {
          "signal_id": "temperature",
          "name": "Temperature",
          "start_bit": 0,
          "bit_length": 16,
          "is_signed": true,
          "scale": 0.1,
          "offset": 0.0,
          "unit": "°C",
          "endianness": "little",
          "min_value": -40.0,
          "max_value": 125.0,
          "is_sequence": false
        }
      ]
    }
  ]
}
```

Load with `SchemaRegistry.load_json(path)` or `load_schema(path)`.

## Transport constraints (optional per message)

| Field | Values | Default |
|-------|--------|---------|
| `frame_format` | `CLASSICAL_CAN`, `CAN_FD` | `CLASSICAL_CAN` |
| `identifier_format` | `STANDARD` (11-bit), `EXTENDED` (29-bit) | `STANDARD` |
| `max_payload` | 0–8 (classical) or up to 64 (FD) | 8 |

Runtime emits `SCHEMA_TRANSPORT_MISMATCH` when an ingested frame violates the message’s declared transport constraints. Signal extraction supports start bits beyond the classical 8-byte window when the frame is CAN-FD.

## Compatibility rules

Every message/signal definition carries explicit `schema_id` and `schema_version`.
These propagate into every `Observation`, `Provenance`, and `MetaFieldEvent`.

| Condition | Result |
|-----------|--------|
| same `schema_id` + same version | **compatible** |
| same `schema_id` + same major, actual ≥ expected | **compatible** |
| same `schema_id` + different major | **incompatible** |
| different `schema_id` | **incompatible** |
| missing / `"unknown"` identity | **unknown** |

A schema change must **never** silently reinterpret an existing CAN payload.
Use `check_compatibility(expected, actual)` or `registry.check_schema(actual)`.

## Optional fields

- `is_heartbeat`: mark a message as a liveness source
- `sequence_width`: bit width of sequence field (enables gap/duplicate/rollback detection)
- `is_sequence` on a signal: extract sequence from payload
- `frame_format` / `identifier_format` / `max_payload`: transport contract (see above)
