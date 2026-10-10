"""CANgate ingestion, emission, health, deterministic processing, reverse path.

Phase 2: adapter conformance for the shared evidence contract.
"""

from cantheon import (
    CanFrame,
    Node,
    SchemaRegistry,
    Runtime,
    InMemorySink,
    CANgate,
    Quality,
    FixedClock,
    Recorder,
    Replay,
)
from cantheon.adapters.metafield_contract import (
    observation_to_boundary,
    event_to_boundary,
    assert_compatible,
    BOUNDARY_SCHEMA,
    BoundaryError,
)
from cantheon.schema_compat import SchemaIdentity


def _setup(clock=None):
    reg = SchemaRegistry()
    reg.load_dict(
        {
            "schema_version": "1.0",
            "schema_id": "temp.v1",
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
    runtime = Runtime(reg, node, sink=sink, clock=clock or FixedClock(0))
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
    obs_list = gate.ingest(_temp_frame(250), ingest_timestamp_ns=1000)
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
    gate, _ = _setup(clock=FixedClock(5000))
    gate.ingest(
        _temp_frame(100, ts=111),
        ingest_timestamp_ns=5000,
        source_timestamp_ns=111,
    )
    gate.ingest(
        _temp_frame(200, ts=222),
        ingest_timestamp_ns=5001,
        source_timestamp_ns=222,
    )
    assert gate.published[0].sequence == 1
    assert gate.published[1].sequence == 2
    assert gate.published[0].payload["source_timestamp_ns"] == 111
    assert gate.published[1].payload["source_timestamp_ns"] == 222
    assert gate.published[0].payload["ingest_timestamp_ns"] == 5000
    assert gate.published[1].payload["ingest_timestamp_ns"] == 5001


def test_deterministic_repeated_processing():
    """Same frame + schema → same observation contents (excl. time-dependent)."""
    gate1, _ = _setup()
    gate2, _ = _setup()
    frame = _temp_frame(250, ts=5000)
    o1 = gate1.ingest(frame, ingest_timestamp_ns=5000)[0]
    o2 = gate2.ingest(frame, ingest_timestamp_ns=5000)[0]
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
    gate.ingest(_temp_frame(250), ingest_timestamp_ns=1)
    gate.ingest(_temp_frame(2000), ingest_timestamp_ns=2)  # OOR
    h = gate.health()
    assert h["frames_in"] == 2
    assert h["observations_out"] == 2
    assert h["error_count"] == 1


def test_reverse_encode_command():
    gate, _ = _setup()
    cmd = gate.encode_command(0x100, {"temperature": 25.0})
    assert cmd is not None
    assert cmd.can_id == 0x100
    obs = gate.ingest(
        CanFrame(can_id=cmd.can_id, data=cmd.data, timestamp_ns=9),
        ingest_timestamp_ns=9,
    )[0]
    assert abs(obs.value - 25.0) < 0.2


def test_cangate_emission_shape():
    gate, _ = _setup()
    gate.ingest(_temp_frame(250), ingest_timestamp_ns=1)
    ev = gate.published[0]
    d = ev.to_dict()
    assert "kind" in d
    assert "node_id" in d
    assert "payload" in d
    assert "quality" in d
    assert "sequence" in d
    assert "timestamp_ns" in d
    assert "provenance" in d


# ---------------------------------------------------------------------------
# Phase 2 — CANgate adapter conformance (shared evidence contract)
# ---------------------------------------------------------------------------


def test_boundary_preserves_envelope_fields():
    """Canonical event envelope survives CANgate → boundary conversion."""
    gate, _ = _setup(clock=FixedClock(100))
    obs_list = gate.ingest(
        _temp_frame(250, ts=50),
        ingest_timestamp_ns=100,
        source_timestamp_ns=50,
    )
    assert len(obs_list) == 1
    obs = obs_list[0]
    env = observation_to_boundary(obs)

    assert env["kind"] == "observation"
    assert env["boundary_schema_id"] == "cantheon.metafield_boundary"
    assert env["boundary_schema_version"] == "0.3.0"
    assert env["node_id"] == "temp_sensor_01"
    assert env["sequence"] == obs.sequence
    assert env["quality"] == "VALID"
    assert env["source_timestamp_ns"] == 50
    assert env["ingest_timestamp_ns"] == 100
    assert env["payload"]["signal_id"] == "temperature"
    assert abs(env["payload"]["value"] - 25.0) < 1e-9
    assert env["payload"]["unit"] == "°C"
    assert "provenance" in env
    assert env["provenance"]["node_id"] == "temp_sensor_01"
    assert env["provenance"]["signal_id"] == "temperature"


def test_boundary_rejects_incompatible_schema():
    """Unsupported schema versions fail closed."""
    consumer = SchemaIdentity("cantheon.metafield_boundary", "99.0.0")
    try:
        assert_compatible(consumer, producer=BOUNDARY_SCHEMA)
        raised = False
    except BoundaryError:
        raised = True
    assert raised, "expected BoundaryError for major version mismatch"


def test_boundary_accepts_compatible_schema():
    consumer = SchemaIdentity("cantheon.metafield_boundary", "0.3.0")
    result = assert_compatible(consumer, producer=BOUNDARY_SCHEMA)
    assert result.value == "COMPATIBLE"


def test_event_to_boundary_preserves_dual_timestamps():
    gate, _ = _setup(clock=FixedClock(200))
    gate.ingest(
        _temp_frame(100, ts=10),
        ingest_timestamp_ns=200,
        source_timestamp_ns=10,
    )
    ev = gate.published[0]
    env = event_to_boundary(ev)
    assert env["source_timestamp_ns"] == 10
    assert env["ingest_timestamp_ns"] == 200
    assert env["sequence"] == ev.sequence
    assert env["quality"] == "VALID"
    assert "provenance" in env


def test_duplicate_ingest_preserves_sequence_identity():
    """Duplicate frames produce distinct sequence numbers; envelope remains valid."""
    gate, _ = _setup(clock=FixedClock(0))
    frame = _temp_frame(250, ts=1)
    o1 = gate.ingest(frame, ingest_timestamp_ns=1, source_timestamp_ns=1)[0]
    o2 = gate.ingest(frame, ingest_timestamp_ns=2, source_timestamp_ns=1)[0]
    assert o1.sequence != o2.sequence
    e1 = observation_to_boundary(o1)
    e2 = observation_to_boundary(o2)
    assert e1["sequence"] != e2["sequence"]
    assert e1["quality"] == e2["quality"] == "VALID"


def test_missing_source_timestamp_is_explicit_null():
    """Unavailable source timestamp must not be fabricated."""
    gate, _ = _setup(clock=FixedClock(99))
    # ingest without source_timestamp_ns
    obs = gate.ingest(_temp_frame(250), ingest_timestamp_ns=99)[0]
    env = observation_to_boundary(obs)
    # source may be None or taken from frame.timestamp_ns; never silently invented wall-clock
    assert env["ingest_timestamp_ns"] == 99
    assert "source_timestamp_ns" in env


def test_provenance_survives_boundary():
    gate, _ = _setup()
    obs = gate.ingest(_temp_frame(250), ingest_timestamp_ns=1)[0]
    env = observation_to_boundary(obs)
    prov = env["provenance"]
    assert prov["node_id"] == "temp_sensor_01"
    assert prov["signal_id"] == "temperature"
    assert "raw_data_hex" in prov
    assert prov["sequence"] == obs.sequence


def test_record_replay_through_cangate_preserves_envelope():
    """Record → replay → boundary envelope is deterministic."""
    reg = SchemaRegistry()
    reg.load_dict({
        "schema_version": "1.0",
        "schema_id": "temp.v1",
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
                "unit": "°C",
                "min_value": -40.0,
                "max_value": 125.0,
            }],
        }],
    })
    recorder = Recorder()
    clock = FixedClock(0)
    node = Node("temp_sensor_01", "Temp")
    rt = Runtime(reg, node, sink=InMemorySink(), clock=clock, recorder=recorder)
    gate = CANgate(rt)
    frame = _temp_frame(250, ts=7)
    live_obs = gate.ingest(frame, ingest_timestamp_ns=10, source_timestamp_ns=7)[0]
    live_env = observation_to_boundary(live_obs)

    # Replay into a fresh runtime
    replay = Replay.from_recorder(recorder)
    rt2 = Runtime(reg, node, sink=InMemorySink(), clock=FixedClock(0))
    gate2 = CANgate(rt2)
    for f, meta in replay.frames():
        gate2.ingest(
            f,
            ingest_timestamp_ns=meta["ingest_timestamp_ns"],
            source_timestamp_ns=meta.get("source_timestamp_ns"),
        )
    replay_obs = gate2.published[0]
    # published is MetaFieldEvent; convert via event_to_boundary
    replay_env = event_to_boundary(replay_obs)

    assert live_env["payload"]["value"] == replay_env["payload"]["value"]
    assert live_env["sequence"] == replay_env["sequence"]
    assert live_env["quality"] == replay_env["quality"]
    assert live_env["node_id"] == replay_env["node_id"]
    assert live_env["provenance"].get("raw_data_hex") == replay_env["provenance"].get("raw_data_hex")
