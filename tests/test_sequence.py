"""Sequence tracking: gap, duplicate, rollback."""

from cantheon.sequence import SequenceTracker, SequenceAnomaly


def test_monotonic_0_1_2():
    t = SequenceTracker()
    assert t.observe(0) == SequenceAnomaly.NONE
    assert t.observe(1) == SequenceAnomaly.NONE
    assert t.observe(2) == SequenceAnomaly.NONE


def test_gap_0_to_2():
    t = SequenceTracker()
    t.observe(0)
    assert t.observe(2) == SequenceAnomaly.GAP


def test_duplicate_2_to_2():
    t = SequenceTracker()
    t.observe(2)
    assert t.observe(2) == SequenceAnomaly.DUPLICATE
    # last_sequence stays 2
    assert t.last_sequence == 2


def test_rollback_5_to_0():
    t = SequenceTracker()
    t.observe(5)
    assert t.observe(0) == SequenceAnomaly.ROLLBACK
    assert t.last_sequence == 0


def test_wraparound_8bit():
    t = SequenceTracker(sequence_width=8)
    t.observe(255)
    assert t.observe(0) == SequenceAnomaly.NONE  # wrap is expected next


def test_sequence_in_runtime():
    from cantheon import (
        CanFrame, Node, SchemaRegistry, Runtime, InMemorySink,
        DiagnosticType, FixedClock,
    )
    reg = SchemaRegistry()
    reg.load_dict({
        "schema_id": "s1",
        "schema_version": "1.0",
        "node_id": "n1",
        "messages": [{
            "message_id": 0x10,
            "name": "SeqMsg",
            "sequence_width": 8,
            "signals": [
                {
                    "signal_id": "seq",
                    "name": "Seq",
                    "start_bit": 0,
                    "bit_length": 8,
                    "is_sequence": True,
                },
                {
                    "signal_id": "val",
                    "name": "Val",
                    "start_bit": 8,
                    "bit_length": 8,
                },
            ],
        }],
    })
    clock = FixedClock(0)
    rt = Runtime(reg, Node("n1", "N"), sink=InMemorySink(), clock=clock)

    def frame(seq, val=1):
        return CanFrame(can_id=0x10, data=bytes([seq & 0xFF, val & 0xFF]))

    rt.process(frame(0), ingest_timestamp_ns=1)
    rt.process(frame(1), ingest_timestamp_ns=2)
    # gap
    rt.process(frame(3), ingest_timestamp_ns=3)
    types = [d.diagnostic_type for d in rt.diagnostics]
    assert DiagnosticType.SEQUENCE_GAP in types
    # observation still present
    assert len(rt.sink.observations) >= 3
