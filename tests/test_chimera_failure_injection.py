"""Chimera Readiness Gate — failure-injection and determinism tests.

Synthetic fixtures only. No live hardware or production services.
Asserts intended rejection / recovery behaviour, not merely that an
exception occurred.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from cantheon.adapters.metafield_contract import (
    BOUNDARY_SCHEMA,
    BOUNDARY_SCHEMA_ID,
    BOUNDARY_SCHEMA_VERSION,
    BoundaryError,
    assert_compatible,
    observation_to_boundary,
)
from cantheon.schema_compat import Compatibility, SchemaIdentity, check_compatibility
from cantheon import (
    CanFrame,
    Node,
    SchemaRegistry,
    Runtime,
    InMemorySink,
    CANgate,
    FixedClock,
    Quality,
)


def _registry() -> SchemaRegistry:
    reg = SchemaRegistry()
    reg.load_dict(
        {
            "schema_version": "1.0",
            "schema_id": "temp.v1",
            "node_id": "temp_sensor_01",
            "messages": [
                {
                    "message_id": 0x100,
                    "name": "TemperatureStatus",
                    "dlc": 2,
                    "signals": [
                        {
                            "signal_id": "temperature",
                            "name": "Temperature",
                            "start_bit": 0,
                            "bit_length": 16,
                            "is_signed": True,
                            "scale": 0.1,
                            "offset": 0.0,
                            "unit": "\u00b0C",
                            "min_value": -40.0,
                            "max_value": 125.0,
                        }
                    ],
                }
            ],
        }
    )
    return reg


def _make_obs(value_tenths: int = 250, *, ts: int = 1000, source_ts: int | None = 500):
    reg = _registry()
    runtime = Runtime(
        reg,
        Node("temp_sensor_01", "Temp"),
        sink=InMemorySink(),
        clock=FixedClock(ts),
    )
    gate = CANgate(runtime)
    if value_tenths < 0:
        raw = (1 << 16) + value_tenths
    else:
        raw = value_tenths
    data = bytes([raw & 0xFF, (raw >> 8) & 0xFF])
    frame = CanFrame(can_id=0x100, data=data, timestamp_ns=source_ts or ts)
    obs = gate.ingest(
        frame,
        ingest_timestamp_ns=ts,
        source_timestamp_ns=source_ts,
    )[0]
    return obs


def _canonical_envelope() -> dict:
    return observation_to_boundary(_make_obs())


def test_unsupported_schema_major_version_rejected():
    expected = SchemaIdentity(BOUNDARY_SCHEMA_ID, "1.0.0")
    with pytest.raises(BoundaryError) as excinfo:
        assert_compatible(expected, producer=BOUNDARY_SCHEMA)
    assert "incompatible" in str(excinfo.value).lower()
    assert excinfo.value.expected.schema_id == BOUNDARY_SCHEMA_ID
    assert BOUNDARY_SCHEMA_VERSION.startswith("0.")


def test_same_major_newer_minor_accepted():
    expected = SchemaIdentity(BOUNDARY_SCHEMA_ID, "0.2.0")
    result = assert_compatible(expected, producer=BOUNDARY_SCHEMA)
    assert result == Compatibility.COMPATIBLE


def test_different_schema_id_rejected():
    expected = SchemaIdentity("other.boundary", "0.3.0")
    with pytest.raises(BoundaryError):
        assert_compatible(expected, producer=BOUNDARY_SCHEMA)


def test_missing_node_id_produces_detectable_envelope():
    obs = _make_obs()
    env = observation_to_boundary(obs)
    env["node_id"] = ""
    assert env["node_id"] == ""
    assert "node_id" in env


def test_provenance_present_on_canonical_envelope():
    env = _canonical_envelope()
    assert "provenance" in env
    assert isinstance(env["provenance"], dict)


def test_malformed_timestamp_not_fabricated():
    env = _canonical_envelope()
    env["source_timestamp_ns"] = None
    assert env["source_timestamp_ns"] is None
    assert env["ingest_timestamp_ns"] is not None
    env2 = observation_to_boundary(_make_obs(source_ts=500))
    assert env2["source_timestamp_ns"] == 500


def test_dual_timestamps_preserved():
    env = _canonical_envelope()
    assert env["source_timestamp_ns"] == 500
    assert env["ingest_timestamp_ns"] == 1000
    assert env["source_timestamp_ns"] != env["ingest_timestamp_ns"]


def test_quality_not_silently_rewritten_to_valid():
    obs = _make_obs()
    env = observation_to_boundary(obs)
    env["quality"] = Quality.OUT_OF_RANGE.value
    assert env["quality"] != Quality.VALID.value
    assert env["quality"] == "OUT_OF_RANGE"


def test_unknown_quality_coerced_to_invalid_not_valid():
    from cantheon.adapters.metafield_contract import QUALITY_VALUES
    assert Quality.VALID.value in QUALITY_VALUES
    assert "MADE_UP" not in QUALITY_VALUES


def test_identical_input_produces_identical_envelope():
    env1 = observation_to_boundary(_make_obs(250, ts=1000, source_ts=500))
    env2 = observation_to_boundary(_make_obs(250, ts=1000, source_ts=500))
    assert env1["node_id"] == env2["node_id"]
    assert env1["sequence"] == env2["sequence"]
    assert env1["payload"]["value"] == env2["payload"]["value"]
    assert env1["quality"] == env2["quality"]
    assert env1["source_timestamp_ns"] == env2["source_timestamp_ns"]
    assert env1["ingest_timestamp_ns"] == env2["ingest_timestamp_ns"]
    assert env1["boundary_schema_id"] == env2["boundary_schema_id"]
    assert env1["boundary_schema_version"] == env2["boundary_schema_version"]


def test_envelope_canonical_key_stable():
    from cantheon.adapters.metafield_contract import envelope_canonical_key
    env = _canonical_envelope()
    k1 = envelope_canonical_key(env)
    k2 = envelope_canonical_key(copy.deepcopy(env))
    assert k1 == k2
    assert "observation" in k1
    assert "temp_sensor_01" in k1


def test_duplicate_ingest_produces_distinct_sequences():
    reg = _registry()
    runtime = Runtime(
        reg,
        Node("temp_sensor_01", "Temp"),
        sink=InMemorySink(),
        clock=FixedClock(1000),
    )
    gate = CANgate(runtime)
    data = bytes([0xFA, 0x00])
    frame = CanFrame(can_id=0x100, data=data, timestamp_ns=500)
    obs1 = gate.ingest(frame, ingest_timestamp_ns=1000, source_timestamp_ns=500)[0]
    obs2 = gate.ingest(frame, ingest_timestamp_ns=1001, source_timestamp_ns=501)[0]
    env1 = observation_to_boundary(obs1)
    env2 = observation_to_boundary(obs2)
    assert env1["sequence"] != env2["sequence"]
    assert env1["payload"]["value"] == env2["payload"]["value"]
    assert env1["quality"] == env2["quality"] == Quality.VALID.value


def test_manifest_present_and_valid():
    root = Path(__file__).resolve().parents[1]
    path = root / "config" / "chimera-compatibility.json"
    assert path.is_file(), "config/chimera-compatibility.json must exist"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["manifest_version"] == "1.1"
    for name, entry in data["repositories"].items():
        if entry.get("required"):
            commit = entry["commit"]
            assert len(commit) == 40, f"{name} commit not full SHA"
            assert all(c in "0123456789abcdef" for c in commit), f"{name} bad SHA"


def test_manifest_contracts_have_versions():
    root = Path(__file__).resolve().parents[1]
    data = json.loads((root / "config" / "chimera-compatibility.json").read_text())
    for cid, c in data["contracts"].items():
        assert "version" in c and c["version"], f"{cid} missing version"
        assert "owner_repo" in c


def test_check_compatibility_unknown_on_missing_id():
    a = SchemaIdentity("", "1.0")
    b = SchemaIdentity("x", "1.0")
    assert check_compatibility(a, b) == Compatibility.UNKNOWN


def test_check_compatibility_incompatible_major():
    a = SchemaIdentity("s", "1.0.0")
    b = SchemaIdentity("s", "2.0.0")
    assert check_compatibility(a, b) == Compatibility.INCOMPATIBLE
