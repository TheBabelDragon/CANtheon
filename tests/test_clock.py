"""Injectable clock and dual timestamp semantics."""

from cantheon import (
    CanFrame, Node, SchemaRegistry, Runtime, InMemorySink, FixedClock,
)


def test_fixed_clock():
    c = FixedClock(1000)
    assert c.now_ns() == 1000
    c.advance(500)
    assert c.now_ns() == 1500
    c.set(0)
    assert c.now_ns() == 0


def test_source_vs_ingest_timestamp():
    clock = FixedClock(9999)
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
                "unit": "\u00b0C",
            }],
        }],
    })
    rt = Runtime(reg, Node("n1", "N"), sink=InMemorySink(), clock=clock)
    data = bytes([250 & 0xFF, 0])
    frame = CanFrame(can_id=0x100, data=data, timestamp_ns=42)
    obs = rt.process(frame, ingest_timestamp_ns=100)[0]
    assert obs.source_timestamp_ns == 42
    assert obs.ingest_timestamp_ns == 100
    assert obs.source_timestamp_ns != obs.ingest_timestamp_ns


def test_no_source_timestamp_is_none():
    """Do not manufacture a source timestamp when source did not provide one."""
    clock = FixedClock(5000)
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
                "unit": "\u00b0C",
            }],
        }],
    })
    rt = Runtime(reg, Node("n1", "N"), sink=InMemorySink(), clock=clock)
    frame = CanFrame(can_id=0x100, data=bytes([250 & 0xFF, 0]))
    obs = rt.process(frame, ingest_timestamp_ns=5000)[0]
    assert obs.source_timestamp_ns is None
    assert obs.ingest_timestamp_ns == 5000
