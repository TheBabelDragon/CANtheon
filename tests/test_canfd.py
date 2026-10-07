"""CAN-FD transport coverage."""

import pytest
from cantheon.frame import (
    CanFrame, FrameFormat, IdentifierFormat,
    fd_dlc_to_length, fd_length_to_dlc, FD_VALID_LENGTHS,
)
from cantheon.signal import SignalDef, extract_signal, Endianness
from cantheon.schema import SchemaRegistry
from cantheon.normalize import normalize_frame
from cantheon.observation import Quality
from cantheon import (
    Node, Runtime, InMemorySink, FixedClock, Recorder, Replay,
    DiagnosticType, CANgate,
)


def test_fd_dlc_all_lengths():
    for dlc, length in [
        (0, 0), (1, 1), (2, 2), (3, 3), (4, 4), (5, 5), (6, 6), (7, 7), (8, 8),
        (9, 12), (10, 16), (11, 20), (12, 24), (13, 32), (14, 48), (15, 64),
    ]:
        assert fd_dlc_to_length(dlc) == length
        assert fd_length_to_dlc(length) == dlc


def test_fd_invalid_length():
    with pytest.raises(ValueError):
        fd_length_to_dlc(9)
    with pytest.raises(ValueError):
        fd_length_to_dlc(65)
    with pytest.raises(ValueError):
        fd_dlc_to_length(16)


@pytest.mark.parametrize("length", [0, 1, 2, 3, 4, 5, 6, 7, 8])
def test_classical_valid_lengths(length):
    f = CanFrame.classical(0x100, b"\x00" * length)
    assert f.frame_format == FrameFormat.CLASSICAL_CAN
    assert f.payload_length == length
    assert f.dlc == length


@pytest.mark.parametrize("length", sorted(FD_VALID_LENGTHS))
def test_fd_valid_lengths(length):
    f = CanFrame.can_fd(0x100, b"\x00" * length)
    assert f.frame_format == FrameFormat.CAN_FD
    assert f.payload_length == length
    assert f.dlc == fd_length_to_dlc(length)


def test_classical_over_8_rejected():
    with pytest.raises(ValueError, match="Classical CAN"):
        CanFrame.classical(0x100, b"\x00" * 9)


def test_fd_over_64_rejected():
    with pytest.raises(ValueError, match="64"):
        CanFrame.can_fd(0x100, b"\x00" * 65)


def test_fd_unsupported_length_rejected():
    with pytest.raises(ValueError, match="unsupported"):
        CanFrame.can_fd(0x100, b"\x00" * 10)


def test_classical_brs_rejected():
    with pytest.raises(ValueError, match="BRS"):
        CanFrame(
            can_id=0x100, data=b"\x00",
            frame_format=FrameFormat.CLASSICAL_CAN,
            bit_rate_switch=True,
        )


def test_standard_id_range():
    CanFrame.classical(0x000, b"")
    CanFrame.classical(0x7FF, b"")
    with pytest.raises(ValueError):
        CanFrame.classical(0x800, b"")


def test_extended_id_range():
    CanFrame.classical(0x000, b"", extended=True)
    CanFrame.classical(0x1FFFFFFF, b"", extended=True)
    with pytest.raises(ValueError):
        CanFrame(
            can_id=0x20000000, data=b"",
            frame_format=FrameFormat.CLASSICAL_CAN,
            identifier_format=IdentifierFormat.EXTENDED_29,
        )


def test_same_numeric_different_format():
    std = CanFrame(
        can_id=0x100, data=b"\x01",
        identifier_format=IdentifierFormat.STANDARD_11,
    )
    ext = CanFrame(
        can_id=0x100, data=b"\x01",
        identifier_format=IdentifierFormat.EXTENDED_29,
    )
    assert std.identifier_format != ext.identifier_format
    assert std.can_id == ext.can_id
    assert not std.is_extended
    assert ext.is_extended


@pytest.mark.parametrize("brs,esi", [
    (False, False), (True, False), (False, True), (True, True),
])
def test_brs_esi_combinations(brs, esi):
    f = CanFrame.can_fd(0x100, b"\x00" * 16, brs=brs, esi=esi)
    assert f.bit_rate_switch is brs
    assert f.error_state_indicator is esi


def test_signal_at_byte_20():
    data = bytearray(32)
    data[20] = 0xAB
    sig = SignalDef(signal_id="far", name="Far", start_bit=160, bit_length=8)
    raw, eng = extract_signal(bytes(data), sig)
    assert raw == 0xAB


def test_signal_at_byte_40():
    data = bytearray(48)
    data[40] = 0x42
    sig = SignalDef(signal_id="s", name="S", start_bit=320, bit_length=8)
    raw, _ = extract_signal(bytes(data), sig)
    assert raw == 0x42


def test_signal_at_byte_63():
    data = bytearray(64)
    data[63] = 0xFF
    sig = SignalDef(signal_id="s", name="S", start_bit=504, bit_length=8)
    raw, _ = extract_signal(bytes(data), sig)
    assert raw == 0xFF


def test_multibyte_crossing_byte8_boundary():
    data = bytearray(16)
    data[7] = 0x34
    data[8] = 0x12
    sig = SignalDef(
        signal_id="cross", name="Cross",
        start_bit=56, bit_length=16, endianness=Endianness.LITTLE,
    )
    raw, _ = extract_signal(bytes(data), sig)
    assert raw == 0x1234


def test_fd_normalize_beyond_byte7():
    reg = SchemaRegistry()
    reg.load_dict({
        "schema_id": "fd.v1", "schema_version": "1.0", "node_id": "n1",
        "messages": [{
            "message_id": 0x200, "name": "FarSensor", "frame_format": "CAN_FD",
            "signals": [{
                "signal_id": "pressure", "name": "Pressure",
                "start_bit": 160, "bit_length": 16, "is_signed": False,
                "scale": 0.1, "unit": "kPa",
            }],
        }],
    })
    data = bytearray(32)
    data[20] = 1000 & 0xFF
    data[21] = (1000 >> 8) & 0xFF
    frame = CanFrame.can_fd(0x200, bytes(data))
    obs = normalize_frame(frame, reg, node_id="n1", sequence=1, ingest_timestamp_ns=1)[0]
    assert abs(obs.value - 100.0) < 1e-9
    assert obs.quality == Quality.VALID


def test_schema_transport_mismatch():
    reg = SchemaRegistry()
    reg.load_dict({
        "schema_id": "classic.v1", "schema_version": "1.0", "node_id": "n1",
        "messages": [{
            "message_id": 0x100, "name": "T", "frame_format": "CLASSICAL_CAN",
            "signals": [{"signal_id": "v", "name": "V", "start_bit": 0, "bit_length": 8}],
        }],
    })
    clock = FixedClock(0)
    rt = Runtime(reg, Node("n1", "N"), sink=InMemorySink(), clock=clock)
    frame = CanFrame.can_fd(0x100, b"\x01")
    rt.process(frame, ingest_timestamp_ns=1)
    types = [d.diagnostic_type for d in rt.diagnostics]
    assert DiagnosticType.SCHEMA_TRANSPORT_MISMATCH in types


def test_fd_record_replay_preserves_transport():
    reg = SchemaRegistry()
    reg.load_dict({
        "schema_id": "fd.v1", "schema_version": "1.0", "node_id": "n1",
        "messages": [{
            "message_id": 0x300, "name": "Big", "frame_format": "CAN_FD",
            "signals": [{"signal_id": "v", "name": "V", "start_bit": 0, "bit_length": 8}],
        }],
    })
    recorder = Recorder()
    clock = FixedClock(0)
    rt = Runtime(reg, Node("n1", "N"), sink=InMemorySink(), clock=clock, recorder=recorder)
    data = b"\xAA" + b"\x00" * 15
    frame = CanFrame.can_fd(0x300, data, brs=True, esi=True, extended=True)
    rt.process(frame, ingest_timestamp_ns=10, source_timestamp_ns=5)
    replay = Replay.from_recorder(recorder)
    frames = list(replay.frames())
    assert len(frames) == 1
    reconstructed, meta = frames[0]
    assert reconstructed.frame_format == FrameFormat.CAN_FD
    assert reconstructed.identifier_format == IdentifierFormat.EXTENDED_29
    assert reconstructed.bit_rate_switch is True
    assert reconstructed.error_state_indicator is True
    assert reconstructed.data == data
    assert reconstructed.can_id == 0x300
    live_keys = [o.canonical_key() for o in rt.sink.observations]
    clock2 = FixedClock(0)
    rt2 = Runtime(reg, Node("n1", "N"), sink=InMemorySink(), clock=clock2)
    replayed = replay.run(rt2)
    assert [o.canonical_key() for o in replayed] == live_keys


def test_fd_not_silently_classical():
    with pytest.raises(ValueError):
        CanFrame(
            can_id=0x100, data=b"\x00" * 16,
            frame_format=FrameFormat.CLASSICAL_CAN,
        )


def test_to_dict_includes_fd_fields():
    f = CanFrame.can_fd(0x123, b"\x00" * 12, brs=True)
    d = f.to_dict()
    assert d["frame_format"] == "CAN_FD"
    assert d["bit_rate_switch"] is True
    assert d["payload_length"] == 12
    assert d["dlc"] == 9
