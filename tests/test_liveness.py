"""Node liveness with injectable clock."""

from cantheon import (
    CanFrame, Node, SchemaRegistry, Runtime, InMemorySink,
    FixedClock, LivenessState, DiagnosticType,
)


def test_alive_stale_timeout():
    clock = FixedClock(0)
    reg = SchemaRegistry()
    reg.load_dict({
        "schema_id": "s",
        "schema_version": "1.0",
        "node_id": "n1",
        "messages": [{
            "message_id": 0x100,
            "name": "T",
            "signals": [{
                "signal_id": "temperature",
                "name": "T",
                "start_bit": 0,
                "bit_length": 16,
                "is_signed": True,
                "scale": 0.1,
                "unit": "°C",
                "min_value": -40,
                "max_value": 125,
            }],
        }],
    })
    rt = Runtime(
        reg, Node("n1", "N"),
        sink=InMemorySink(),
        clock=clock,
        timeout_threshold_ns=1000,
        stale_threshold_ns=500,
    )
    data = bytes([250 & 0xFF, 0])
    frame = CanFrame(can_id=0x100, data=data)

    # node appears → ALIVE
    rt.process(frame, ingest_timestamp_ns=0)
    assert rt.check_liveness(0) == LivenessState.ALIVE

    # no heartbeat → STALE
    clock.set(600)
    assert rt.check_liveness(600) == LivenessState.STALE

    # timeout → TIMEOUT + diagnostic
    clock.set(1500)
    assert rt.check_liveness(1500) == LivenessState.TIMEOUT
    assert any(d.diagnostic_type == DiagnosticType.NODE_TIMEOUT for d in rt.diagnostics)


def test_liveness_tracker_unit():
    from cantheon.liveness import LivenessTracker, LivenessState
    t = LivenessTracker(timeout_threshold_ns=100, stale_threshold_ns=50)
    assert t.state(0) == LivenessState.UNKNOWN
    t.touch(10)
    assert t.state(20) == LivenessState.ALIVE
    assert t.state(70) == LivenessState.STALE
    assert t.state(120) == LivenessState.TIMEOUT
