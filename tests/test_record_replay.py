"""Recording and deterministic replay."""

from cantheon import (
    CanFrame, Node, SchemaRegistry, Runtime, InMemorySink, CANgate,
    FixedClock, Recorder, Replay, Quality,
)


def _reg():
    reg = SchemaRegistry()
    reg.load_dict({
        "schema_id": "temp.v1",
        "schema_version": "1.0",
        "node_id": "n1",
        "messages": [{
            "message_id": 0x100,
            "name": "TemperatureStatus",
            "signals": [{
                "signal_id": "temperature",
                "name": "Temperature",
                "start_bit": 0,
                "bit_length": 16,
                "is_signed": True,
                "scale": 0.1,
                "unit": "\u00b0C",
                "min_value": -40.0,
                "max_value": 125.0,
            }],
        }],
    })
    return reg


def _temp(tenths):
    if tenths < 0:
        raw = (1 << 16) + tenths
    else:
        raw = tenths
    return CanFrame(can_id=0x100, data=bytes([raw & 0xFF, (raw >> 8) & 0xFF]))


def test_record_and_replay_deterministic():
    clock = FixedClock(0)
    recorder = Recorder()
    reg = _reg()
    rt = Runtime(reg, Node("n1", "N"), sink=InMemorySink(),
                 clock=clock, recorder=recorder)

    frames = [
        (_temp(250), 100),
        (_temp(300), 200),
        (_temp(2000), 300),
    ]
    live_obs = []
    for frame, ts in frames:
        clock.set(ts)
        live_obs.extend(rt.process(frame, ingest_timestamp_ns=ts, source_timestamp_ns=ts))

    live_keys = [o.canonical_key() for o in live_obs]

    clock2 = FixedClock(0)
    rt2 = Runtime(reg, Node("n1", "N"), sink=InMemorySink(), clock=clock2)
    replay = Replay.from_recorder(recorder)
    replayed = replay.run(rt2)
    replay_keys = [o.canonical_key() for o in replayed]

    assert live_keys == replay_keys
    assert len(replayed) == 3
    assert replayed[0].value == 25.0
    assert replayed[2].quality == Quality.OUT_OF_RANGE


def test_replay_from_path(tmp_path):
    path = tmp_path / "session.jsonl"
    recorder = Recorder(path)
    reg = _reg()
    clock = FixedClock(0)
    rt = Runtime(reg, Node("n1", "N"), sink=InMemorySink(),
                 clock=clock, recorder=recorder)
    rt.process(_temp(250), ingest_timestamp_ns=50, source_timestamp_ns=50)
    recorder.close()

    replay = Replay.from_path(path)
    assert len(list(replay.frames())) == 1
    assert len(replay.observations()) == 1


def test_recorded_event_roundtrip():
    from cantheon.record import RecordedEvent
    frame = _temp(250)
    ev = RecordedEvent.from_frame(
        frame, node_id="n1", ingest_timestamp_ns=10,
        source_timestamp_ns=5, schema_id="temp.v1", schema_version="1.0",
    )
    d = ev.to_dict()
    ev2 = RecordedEvent.from_dict(d)
    assert ev2.event_type == "frame"
    assert ev2.data["can_id"] == 0x100
    assert ev2.data["schema_id"] == "temp.v1"
