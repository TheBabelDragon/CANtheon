"""Schema versioning and compatibility."""

from cantheon.schema_compat import (
    SchemaIdentity,
    Compatibility,
    check_compatibility,
)
from cantheon.schema import SchemaRegistry
from cantheon.frame import CanFrame
from cantheon.normalize import normalize_frame


def test_same_schema_version():
    a = SchemaIdentity("temp.v1", "1.0")
    b = SchemaIdentity("temp.v1", "1.0")
    assert check_compatibility(a, b) == Compatibility.COMPATIBLE


def test_newer_compatible_schema():
    expected = SchemaIdentity("temp.v1", "1.0")
    actual = SchemaIdentity("temp.v1", "1.1")
    assert check_compatibility(expected, actual) == Compatibility.COMPATIBLE


def test_incompatible_major():
    expected = SchemaIdentity("temp.v1", "1.0")
    actual = SchemaIdentity("temp.v1", "2.0")
    assert check_compatibility(expected, actual) == Compatibility.INCOMPATIBLE


def test_different_schema_id():
    a = SchemaIdentity("temp.v1", "1.0")
    b = SchemaIdentity("pressure.v1", "1.0")
    assert check_compatibility(a, b) == Compatibility.INCOMPATIBLE


def test_unknown_schema():
    a = SchemaIdentity("unknown", "0.0")
    b = SchemaIdentity("temp.v1", "1.0")
    assert check_compatibility(a, b) == Compatibility.UNKNOWN
    assert check_compatibility(b, a) == Compatibility.UNKNOWN


def test_schema_identity_serialization():
    s = SchemaIdentity("temp.v1", "1.2.3")
    d = s.to_dict()
    assert d == {"schema_id": "temp.v1", "schema_version": "1.2.3"}
    s2 = SchemaIdentity.from_dict(d)
    assert s2 == s


def test_schema_propagates_to_observation():
    reg = SchemaRegistry()
    reg.load_dict({
        "schema_id": "temp.v1",
        "schema_version": "1.0",
        "node_id": "n1",
        "messages": [{
            "message_id": 0x100,
            "name": "T",
            "signals": [{
                "signal_id": "temperature",
                "name": "Temperature",
                "start_bit": 0,
                "bit_length": 16,
                "is_signed": True,
                "scale": 0.1,
                "unit": "\u00b0C",
            }],
        }],
    })
    data = bytes([250 & 0xFF, 0])
    frame = CanFrame(can_id=0x100, data=data)
    obs = normalize_frame(
        frame, reg, node_id="n1", sequence=1, ingest_timestamp_ns=1000
    )[0]
    assert obs.schema_id == "temp.v1"
    assert obs.schema_version == "1.0"
    assert obs.provenance.schema_id == "temp.v1"


def test_registry_check_schema():
    reg = SchemaRegistry()
    reg.schema_id = "temp.v1"
    reg.schema_version = "1.0"
    assert reg.check_schema(SchemaIdentity("temp.v1", "1.0")) == Compatibility.COMPATIBLE
    assert reg.check_schema(SchemaIdentity("temp.v1", "2.0")) == Compatibility.INCOMPATIBLE
