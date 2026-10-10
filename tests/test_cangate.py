"""CANgate ingestion, emission, health, deterministic processing, reverse path."""

from cantheon import (
    CanFrame,
    Node,
    SchemaRegistry,
    Runtime,
    InMemorySink,
    CANgate,
    Quality,
)


def _setup():
    reg = SchemaRegistry()
    reg.load_dict(
        {
            "schema_version": "1.0",
            "node_id": "temp_sensor_01",
            "messages": [
                {
                    "message_id": 0x100,
                    "name": "TemperatureStatus",
                    "dlc": 2,
                    "signals": [
                        {
                            "signal_id": "temperature",
                            "name": "Temperature",
                            "start_bit": 0,
                            "bit_length": 16,
                            "is_signed": True,
                            "scale": 0.1,
                            "offset": 0.0,
                            "unit": "°C",
                            "min_value": -40.0,
                            "max_value": 125.0,
                        }
                    ],
                }
            ],
        }
    )
    node = Node(node_id="temp_sensor_01", name="Temp Sensor")
    sink = InMemorySink()
    runtime = Runtime(reg, node, sink=sink)
    gate = CANgate(runtime)
    return gate, sink


def _temp_frame(tenths: int, ts: int = 1000) -> CanFrame:
    if tenths < 0:
        raw = (1 << 16) + tenths
    else:
        raw = tenths
    data = bytes([raw & 0xFF, (raw >> 8) & 0xFF])
    return CanFrame(can_id=0x100, data=data, timestamp_ns=ts)


def test_ingest_and_publish():
    gate, sink = _setup()
    obs_list = gate.ingest(_temp_frame(250))
    assert len(obs_list) == 1
    assert abs(obs_list[0].value - 25.0) < 1e-9
    assert len(gate.published) == 1
    ev = gate.published[0]
    assert ev.kind == "observation"
    assert ev.payload["value"] == obs_list[0].value
    assert ev.quality == "VALID"
    assert len(sink.observations) == 1


def test_node_identity():
    gate, _ = _setup()
    h = gate.health()
    assert h["node"]["node_id"] == "temp_sensor_01"
    assert h["gateway"] == "CANgate"


def test_timestamps_and_sequence():
    from cantheon import FixedClock
    reg = SchemaRegistry()
    reg.load_dict({
        "schema_version": "1.0",
        "node_id": "temp_sensor_01",
        "messages": [{
            "message_id": 0x100,
            "name": "TemperatureStatus",
            "dlc": 2,
            "signals": [{
                "signal_id": "temperature",
                "name": "Temperature",
                "start_bit": 0,
                "bit_length": 16,
                "is_signed": True,
                "scale": 0.1,
                "offset": 0.0,
                "unit": "°C",
                "min_value": -40.0,
                "max_value": 125.0,
            }],
        }],
    })
    node = Node(node_id="temp_sensor_01", name="Temp Sensor")
    clock = FixedClock(5000)
    runtime = Runtime(reg, node, sink=InMemorySink(), clock=clock)
    gate = CANgate(runtime)
    # Frame timestamp becomes source_timestamp; ingest is controlled by clock / explicit
    gate.ingest(_temp_frame(100, ts=111), ingest_timestamp_ns=5000, source_timestamp_ns=111)
    gate.ingest(_temp_frame(200, ts=222), ingest_timestamp_ns=5001, source_timestamp_ns=222)
    assert gate.published[0].sequence == 1
    assert gate.published[1].sequence == 2
    # Dual timestamps preserved: source in payload, timestamp_ns is ingest (or source fallback)
    assert gate.published[0].payload["source_timestamp_ns"] == 111
    assert gate.published[1].payload["source_timestamp_ns"] == 222
    assert gate.published[0].payload["ingest_timestamp_ns"] == 5000
    assert gate.published[1].payload["ingest_timestamp_ns"] == 5001


def test_deterministic_repeated_processing():
    """Same frame + schema → same observation contents (excl. time-dependent)."""
    gate1, _ = _setup()
    gate2, _ = _setup()
    frame = _temp_frame(250, ts=5000)
    o1 = gate1.ingest(frame)[0]
    o2 = gate2.ingest(frame)[0]
    assert o1.value == o2.value
    assert o1.unit == o2.unit
    assert o1.raw_value == o2.raw_value
    assert o1.quality == o2.quality
    assert o1.signal_id == o2.signal_id
