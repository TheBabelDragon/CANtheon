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
    gate, _ = _setup()
    gate.ingest(_temp_frame(100, ts=111))
    gate.ingest(_temp_frame(200, ts=222))
    assert gate.published[0].sequence == 1
    assert gate.published[1].sequence == 2
    assert gate.published[0].timestamp_ns == 111
    assert gate.published[1].timestamp_ns == 222


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
    assert o1.node_id == o2.node_id
    assert o1.message_id == o2.message_id
    assert o1.provenance.raw_data_hex == o2.provenance.raw_data_hex


def test_health_counters():
    gate, _ = _setup()
    gate.ingest(_temp_frame(250))
    gate.ingest(_temp_frame(2000))  # OOR
    h = gate.health()
    assert h["frames_in"] == 2
    assert h["observations_out"] == 2
    assert h["error_count"] == 1


def test_reverse_encode_command():
    gate, _ = _setup()
    cmd = gate.encode_command(0x100, {"temperature": 25.0})
    assert cmd is not None
    assert cmd.can_id == 0x100
    # re-ingest and check value
    obs = gate.ingest(CanFrame(can_id=cmd.can_id, data=cmd.data, timestamp_ns=9))[0]
    assert abs(obs.value - 25.0) < 0.2  # allow minor rounding


def test_cangate_emission_shape():
    gate, _ = _setup()
    gate.ingest(_temp_frame(250))
    ev = gate.published[0]
    d = ev.to_dict()
    assert "kind" in d
    assert "node_id" in d
    assert "payload" in d
    assert "quality" in d
    assert "sequence" in d
    assert "timestamp_ns" in d
    assert "provenance" in d
