# CANtheon schemas

Versioned message/signal definitions for physical nodes.

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
      "message_id": 256,
      "name": "TemperatureStatus",
      "dlc": 2,
      "schema_id": "temp_sensor.v1",
      "schema_version": "1.0",
      "frame_format": "EITHER",
      "identifier_format": "EITHER",
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
          "unit": "\u00b0C",
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

`frame_format`: `CLASSICAL_CAN` | `CAN_FD` | `EITHER`  
`identifier_format`: `STANDARD_11` | `EXTENDED_29` | `EITHER`

Load with `SchemaRegistry.load_json(path)` or `load_schema(path)`.

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
A Classical-CAN-only schema must not silently accept an FD frame (emits `SCHEMA_TRANSPORT_MISMATCH`).

## Optional fields

- `is_heartbeat`: mark a message as a liveness source
- `sequence_width`: bit width of sequence field
- `is_sequence` on a signal: extract sequence from payload
- `frame_format` / `identifier_format` / `max_payload`: transport constraints
