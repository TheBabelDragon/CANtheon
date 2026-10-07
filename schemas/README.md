# CANtheon schemas

Versioned message/signal definitions for physical nodes.

## Document shape

```json
{
  "schema_version": "1.0",
  "node_id": "temp_sensor_01",
  "messages": [
    {
      "message_id": 0x100,
      "name": "TemperatureStatus",
      "dlc": 2,
      "schema_version": "1.0",
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
          "max_value": 125.0
        }
      ]
    }
  ]
}
```

Load with `SchemaRegistry.load_json(path)` or `load_schema(path)`.
