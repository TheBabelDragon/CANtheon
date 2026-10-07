"""Range validation and invalid input handling."""

from cantheon.frame import CanFrame
from cantheon.schema import SchemaRegistry
from cantheon.normalize import normalize_frame
from cantheon.validate import validate_observation
from cantheon.observation import Quality
from cantheon.signal import SignalDef


def _temp_registry():
    reg = SchemaRegistry()
    reg.load_dict(
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
    return reg


def test_out_of_range():
    reg = _temp_registry()
    # 200.0 °C = 2000 tenths
    data = bytes([2000 & 0xFF, (2000 >> 8) & 0xFF])
    frame = CanFrame(can_id=0x100, data=data, timestamp_ns=1)
    obs = normalize_frame(frame, reg, node_id="n", sequence=1)[0]
    assert obs.quality == Quality.OUT_OF_RANGE
    assert abs(obs.value - 200.0) < 1e-9  # value still present


def test_unknown_message_decode_error():
    reg = _temp_registry()
    frame = CanFrame(can_id=0x7FF, data=b"\x00")
    obs = normalize_frame(frame, reg, node_id="n", sequence=1)[0]
    assert obs.quality == Quality.DECODE_ERROR
    assert obs.signal_id == "__unknown__"


def test_validate_observation_preserves_decode_error():
    reg = _temp_registry()
    frame = CanFrame(can_id=0x7FF, data=b"\x00")
    obs = normalize_frame(frame, reg, node_id="n", sequence=1)[0]
    out = validate_observation(obs)
    assert out.quality == Quality.DECODE_ERROR


def test_invalid_not_discarded():
    """Malformed / out-of-range must remain observable."""
    reg = _temp_registry()
    data = bytes([2000 & 0xFF, (2000 >> 8) & 0xFF])
    frame = CanFrame(can_id=0x100, data=data)
    obs_list = normalize_frame(frame, reg, node_id="n", sequence=5)
    assert len(obs_list) == 1
    assert obs_list[0].quality != Quality.VALID
    assert obs_list[0].sequence == 5
