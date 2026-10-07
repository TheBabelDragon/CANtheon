"""Signal extraction, scaling, endianness, signed/unsigned."""

from cantheon.frame import CanFrame
from cantheon.signal import SignalDef, MessageDef, Endianness, extract_signal
from cantheon.schema import SchemaRegistry
from cantheon.normalize import normalize_frame
from cantheon.observation import Quality


def test_unsigned_extraction():
    sig = SignalDef(
        signal_id="u8",
        name="U8",
        start_bit=0,
        bit_length=8,
        is_signed=False,
        scale=1.0,
        offset=0.0,
    )
    raw, eng = extract_signal(b"\x2a", sig)
    assert raw == 42
    assert eng == 42.0


def test_signed_extraction_negative():
    # -10 as signed 16-bit little-endian: 0xFFF6
    data = bytes([0xF6, 0xFF])
    sig = SignalDef(
        signal_id="temp",
        name="Temp",
        start_bit=0,
        bit_length=16,
        is_signed=True,
        scale=0.1,
        offset=0.0,
        unit="°C",
    )
    raw, eng = extract_signal(data, sig)
    assert raw == -10
    assert abs(eng - (-1.0)) < 1e-9


def test_scale_and_offset():
    sig = SignalDef(
        signal_id="v",
        name="V",
        start_bit=0,
        bit_length=8,
        scale=0.5,
        offset=10.0,
    )
    raw, eng = extract_signal(b"\x14", sig)  # 20
    assert raw == 20
    assert eng == 20 * 0.5 + 10.0  # 20.0


def test_little_endian_multi_byte():
    # value 0x1234 little-endian at bit 0
    data = bytes([0x34, 0x12])
    sig = SignalDef(
        signal_id="x",
        name="X",
        start_bit=0,
        bit_length=16,
        endianness=Endianness.LITTLE,
    )
    raw, _ = extract_signal(data, sig)
    assert raw == 0x1234


def test_normalize_temperature():
    registry = SchemaRegistry()
    registry.load_dict(
        {
            "schema_version": "1.0",
            "messages": [
                {
                    "message_id": 0x100,
                    "name": "TemperatureStatus",
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
    # 25.0 °C = 250 tenths
    data = bytes([250 & 0xFF, (250 >> 8) & 0xFF])
    frame = CanFrame(can_id=0x100, data=data, timestamp_ns=1000)
    obs_list = normalize_frame(
        frame, registry, node_id="n1", sequence=1, timestamp_ns=1000
    )
    assert len(obs_list) == 1
    obs = obs_list[0]
    assert obs.signal_id == "temperature"
    assert abs(obs.value - 25.0) < 1e-9
    assert obs.unit == "°C"
    assert obs.quality == Quality.VALID
    assert obs.raw_value == 250
    assert obs.sequence == 1
    assert obs.timestamp_ns == 1000


def test_unit_assignment():
    registry = SchemaRegistry()
    registry.load_dict(
        {
            "messages": [
                {
                    "message_id": 1,
                    "name": "M",
                    "signals": [
                        {
                            "signal_id": "s",
                            "name": "S",
                            "start_bit": 0,
                            "bit_length": 8,
                            "unit": "rpm",
                        }
                    ],
                }
            ]
        }
    )
    frame = CanFrame(can_id=1, data=b"\x01")
    obs = normalize_frame(frame, registry, node_id="n", sequence=1)[0]
    assert obs.unit == "rpm"
