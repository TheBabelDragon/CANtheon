"""Provenance identity and contents."""

from cantheon.provenance import Provenance
from cantheon.frame import CanFrame
from cantheon.schema import SchemaRegistry
from cantheon.normalize import normalize_frame


def test_provenance_fields():
    p = Provenance(
        node_id="temp_sensor_01",
        can_message_id=0x100,
        signal_id="temperature",
        sequence=7,
        timestamp_ns=12345,
        schema_version="1.0",
        raw_data_hex="fa00",
    )
    d = p.to_dict()
    assert d["node_id"] == "temp_sensor_01"
    assert d["can_message_id"] == 0x100
    assert d["signal_id"] == "temperature"
    assert d["sequence"] == 7
    assert d["schema_version"] == "1.0"
    assert d["raw_data_hex"] == "fa00"


def test_identity_key():
    p = Provenance(
        node_id="n",
        can_message_id=0x100,
        signal_id="s",
        sequence=3,
        timestamp_ns=0,
        schema_version="1.0",
    )
    assert p.identity_key() == "n|0x100|s|3"


def test_provenance_attached_on_normalize():
    reg = SchemaRegistry()
    reg.load_dict(
        {
            "messages": [
                {
                    "message_id": 0x100,
                    "name": "M",
                    "signals": [
                        {
                            "signal_id": "temperature",
                            "name": "T",
                            "start_bit": 0,
                            "bit_length": 16,
                            "is_signed": True,
                            "scale": 0.1,
                            "unit": "°C",
                        }
                    ],
                }
            ]
        }
    )
    data = bytes([250 & 0xFF, 0])
    frame = CanFrame(can_id=0x100, data=data, timestamp_ns=99)
    obs = normalize_frame(
        frame, reg, node_id="temp_sensor_01", sequence=42, timestamp_ns=99
    )[0]
    assert obs.provenance.node_id == "temp_sensor_01"
    assert obs.provenance.can_message_id == 0x100
    assert obs.provenance.signal_id == "temperature"
    assert obs.provenance.sequence == 42
    assert obs.provenance.timestamp_ns == 99
    assert obs.provenance.raw_data_hex == data.hex()
