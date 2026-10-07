"""Canonical observation fields and serialization."""

from cantheon.observation import Observation, Quality
from cantheon.provenance import Provenance


def _make_obs(**kwargs):
    defaults = dict(
        node_id="n1",
        message_id=0x100,
        signal_id="temperature",
        value=25.0,
        unit="°C",
        timestamp_ns=1000,
        sequence=1,
        quality=Quality.VALID,
        source="cantheon",
        provenance=Provenance(
            node_id="n1",
            can_message_id=0x100,
            signal_id="temperature",
            sequence=1,
            timestamp_ns=1000,
            schema_version="1.0",
            raw_data_hex="fa00",
        ),
        raw_value=250,
    )
    defaults.update(kwargs)
    return Observation(**defaults)


def test_required_fields():
    obs = _make_obs()
    d = obs.to_dict()
    for key in (
        "node_id",
        "message_id",
        "signal_id",
        "value",
        "unit",
        "timestamp_ns",
        "sequence",
        "quality",
        "source",
        "provenance",
    ):
        assert key in d


def test_is_valid():
    assert _make_obs().is_valid()
    assert not _make_obs(quality=Quality.OUT_OF_RANGE).is_valid()


def test_serialization_roundtrip_shape():
    obs = _make_obs()
    d = obs.to_dict()
    assert d["value"] == 25.0
    assert d["quality"] == "VALID"
    assert d["provenance"]["node_id"] == "n1"
    assert d["message_id_hex"] == "0x100"
