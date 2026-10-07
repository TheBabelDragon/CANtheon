"""Diagnostic model coverage."""

from cantheon import (
    CanFrame, Node, SchemaRegistry, Runtime, InMemorySink, CANgate,
    DiagnosticType, FixedClock, Quality,
)


def _setup(clock=None, timeout_ns=1_000_000_000):
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
    node = Node(node_id="n1", name="N1")
    clock = clock or FixedClock(0)
    rt = Runtime(reg, node, sink=InMemorySink(), clock=clock,
                 timeout_threshold_ns=timeout_ns, stale_threshold_ns=timeout_ns // 2)
    return CANgate(rt), rt, clock


def _temp(tenths, ts=None):
    if tenths < 0:
        raw = (1 << 16) + tenths
    else:
        raw = tenths
    data = bytes([raw & 0xFF, (raw >> 8) & 0xFF])
    return CanFrame(can_id=0x100, data=data, timestamp_ns=ts)


def test_unknown_message_diagnostic():
    gate, rt, _ = _setup()
    gate.ingest(CanFrame(can_id=0x7FF, data=b"\x00"), ingest_timestamp_ns=1)
    types = [d.diagnostic_type for d in rt.diagnostics]
    assert DiagnosticType.UNKNOWN_MESSAGE in types
    assert DiagnosticType.DECODE_ERROR in types


def test_invalid_value_diagnostic():
    gate, rt, _ = _setup()
    gate.ingest(_temp(2000), ingest_timestamp_ns=1)
    types = [d.diagnostic_type for d in rt.diagnostics]
    assert DiagnosticType.INVALID_VALUE in types
    obs = rt.sink.observations[0]
    assert obs.quality == Quality.OUT_OF_RANGE
    assert abs(obs.value - 200.0) < 1e-9


def test_decode_error_vs_invalid_value():
    gate, rt, _ = _setup()
    gate.ingest(CanFrame(can_id=0x7FF, data=b"\x00"), ingest_timestamp_ns=1)
    gate.ingest(_temp(2000), ingest_timestamp_ns=2)
    types = {d.diagnostic_type for d in rt.diagnostics}
    assert DiagnosticType.UNKNOWN_MESSAGE in types
    assert DiagnosticType.INVALID_VALUE in types


def test_node_timeout_diagnostic():
    clock = FixedClock(0)
    gate, rt, clock = _setup(clock=clock, timeout_ns=1000)
    gate.ingest(_temp(250), ingest_timestamp_ns=0)
    clock.set(2000)
    state = rt.check_liveness(2000)
    from cantheon import LivenessState
    assert state == LivenessState.TIMEOUT
    assert any(d.diagnostic_type == DiagnosticType.NODE_TIMEOUT for d in rt.diagnostics)


def test_stale_diagnostic():
    clock = FixedClock(0)
    gate, rt, clock = _setup(clock=clock, timeout_ns=1000)
    gate.ingest(_temp(250), ingest_timestamp_ns=0)
    clock.set(600)
    state = rt.check_liveness(600)
    from cantheon import LivenessState
    assert state == LivenessState.STALE
    assert any(d.diagnostic_type == DiagnosticType.STALE_OBSERVATION for d in rt.diagnostics)


def test_diagnostic_to_dict():
    gate, rt, _ = _setup()
    gate.ingest(CanFrame(can_id=0x7FF, data=b"\x00"), ingest_timestamp_ns=42)
    d = rt.diagnostics[0].to_dict()
    assert "diagnostic_type" in d
    assert "timestamp_ns" in d
    assert "node_id" in d
