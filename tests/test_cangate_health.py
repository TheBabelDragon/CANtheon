"""CANgate lifecycle and expanded health."""

from cantheon import (
    CanFrame, Node, SchemaRegistry, Runtime, InMemorySink, CANgate,
    FixedClock, GateState,
)


def test_gate_state_ready():
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
    clock = FixedClock(0)
    rt = Runtime(reg, Node("n1", "N"), sink=InMemorySink(), clock=clock)
    gate = CANgate(rt)
    assert gate.state == GateState.READY

    data = bytes([250 & 0xFF, 0])
    gate.ingest(CanFrame(can_id=0x100, data=data), ingest_timestamp_ns=1)
    h = gate.health()
    assert h["state"] == "READY"
    assert h["frames_received"] == 1
    assert h["observations_emitted"] == 1
    assert "diagnostics_emitted" in h
    assert "active_nodes" in h
    assert "stale_nodes" in h
    assert h["schema_id"] == "s"
    # backward-compat keys
    assert h["frames_in"] == 1
    assert h["observations_out"] == 1
