"""Chimera Readiness Gate v1.2 — behavior-driven failure-injection tests.

Exercises real adapter boundaries (MetaField, MultiFlow, Aurora) where
sibling packages are available. Synthetic fixtures only; no live hardware.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from cantheon.adapters.metafield_contract import (
    BOUNDARY_SCHEMA,
    BOUNDARY_SCHEMA_ID,
    BoundaryError,
    assert_compatible,
    observation_to_boundary,
)
from cantheon.schema_compat import Compatibility, SchemaIdentity, check_compatibility
from cantheon import (
    CanFrame, Node, SchemaRegistry, Runtime, InMemorySink, CANgate, FixedClock, Quality,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = REPO_ROOT.parent


def _add_sibling_paths() -> None:
    for name, sub in (("metafield", ""), ("TensorGate", ""), ("MultiFlow", "src"), ("aurora-swarm-btc", "")):
        base = WORKSPACE / name
        path = base / sub if sub else base
        if path.exists() and str(path) not in sys.path:
            sys.path.insert(0, str(path))


_add_sibling_paths()


def _has_metafield() -> bool:
    try:
        from adapters.cantheon_boundary import boundary_to_field_observation  # noqa: F401
        return True
    except ImportError:
        return False


def _has_multiflow() -> bool:
    try:
        from multiflow import build_decision_evidence  # noqa: F401
        return True
    except ImportError:
        return False


def _has_aurora() -> bool:
    try:
        from mods.evidence_integrity import build_evidence_object  # noqa: F401
        return True
    except ImportError:
        return False


def _registry() -> SchemaRegistry:
    reg = SchemaRegistry()
    reg.load_dict({
        "schema_version": "1.0", "schema_id": "temp.v1", "node_id": "temp_sensor_01",
        "messages": [{
            "message_id": 0x100, "name": "TemperatureStatus", "dlc": 2,
            "signals": [{
                "signal_id": "temperature", "name": "Temperature",
                "start_bit": 0, "bit_length": 16, "is_signed": True,
                "scale": 0.1, "offset": 0.0, "unit": "\u00b0C",
                "min_value": -40.0, "max_value": 125.0,
            }],
        }],
    })
    return reg


def _make_obs(value_tenths: int = 250, *, ts: int = 1000, source_ts: int | None = 500):
    reg = _registry()
    runtime = Runtime(reg, Node("temp_sensor_01", "Temp"), sink=InMemorySink(), clock=FixedClock(ts))
    gate = CANgate(runtime)
    if value_tenths < 0:
        raw = (1 << 16) + value_tenths
    else:
        raw = value_tenths
    data = bytes([raw & 0xFF, (raw >> 8) & 0xFF])
    frame = CanFrame(can_id=0x100, data=data, timestamp_ns=source_ts or ts)
    return gate.ingest(frame, ingest_timestamp_ns=ts, source_timestamp_ns=source_ts)[0]


def _canonical_envelope() -> dict:
    return observation_to_boundary(_make_obs())


def test_unsupported_schema_major_version_rejected():
    with pytest.raises(BoundaryError):
        assert_compatible(SchemaIdentity(BOUNDARY_SCHEMA_ID, "1.0.0"), producer=BOUNDARY_SCHEMA)


def test_different_schema_id_rejected():
    with pytest.raises(BoundaryError):
        assert_compatible(SchemaIdentity("other.boundary", "0.3.0"), producer=BOUNDARY_SCHEMA)


@pytest.mark.skipif(not _has_metafield(), reason="metafield sibling not available")
def test_metafield_rejects_missing_node_id():
    from adapters.cantheon_boundary import boundary_to_field_observation, BoundaryAdapterError
    env = _canonical_envelope()
    env["node_id"] = ""
    with pytest.raises(BoundaryAdapterError) as ei:
        boundary_to_field_observation(env)
    assert "node_id" in str(ei.value).lower()


@pytest.mark.skipif(not _has_metafield(), reason="metafield sibling not available")
def test_metafield_rejects_incompatible_boundary_major():
    from adapters.cantheon_boundary import boundary_to_field_observation, BoundaryAdapterError
    env = _canonical_envelope()
    env["boundary_schema_version"] = "1.0.0"
    with pytest.raises(BoundaryAdapterError):
        boundary_to_field_observation(env)


@pytest.mark.skipif(not _has_metafield(), reason="metafield sibling not available")
def test_metafield_accepts_valid_envelope_preserves_quality():
    from adapters.cantheon_boundary import boundary_to_field_observation
    from schemas.evidence import EvidenceQuality
    env = _canonical_envelope()
    obs = boundary_to_field_observation(env)
    assert obs.evidence is not None
    assert obs.evidence.quality == EvidenceQuality.VALID
    assert obs.evidence.source_id == "temp_sensor_01"
    assert obs.evidence.source_timestamp_ns == 500
    assert obs.evidence.ingest_timestamp_ns == 1000


def test_dual_timestamps_preserved_through_boundary():
    env = observation_to_boundary(_make_obs(source_ts=500))
    assert env["source_timestamp_ns"] == 500
    assert env["ingest_timestamp_ns"] == 1000


@pytest.mark.skipif(not _has_metafield(), reason="metafield sibling not available")
def test_dual_timestamps_survive_metafield_adapter():
    from adapters.cantheon_boundary import boundary_to_field_observation
    env = observation_to_boundary(_make_obs(source_ts=777, ts=2000))
    obs = boundary_to_field_observation(env)
    assert obs.evidence.source_timestamp_ns == env["source_timestamp_ns"]
    assert obs.evidence.ingest_timestamp_ns == env["ingest_timestamp_ns"]


@pytest.mark.skipif(not _has_metafield(), reason="metafield sibling not available")
def test_out_of_range_quality_not_upgraded_to_valid():
    from adapters.cantheon_boundary import boundary_to_field_observation
    from schemas.evidence import EvidenceQuality
    env = _canonical_envelope()
    env["quality"] = "OUT_OF_RANGE"
    field_obs = boundary_to_field_observation(env)
    assert field_obs.evidence.quality != EvidenceQuality.VALID
    assert field_obs.evidence.quality == EvidenceQuality.OUT_OF_RANGE
    assert field_obs.health != "ok"


@pytest.mark.skipif(not _has_metafield(), reason="metafield sibling not available")
def test_invalid_quality_maps_to_error_health():
    from adapters.cantheon_boundary import boundary_to_field_observation
    from schemas.evidence import EvidenceQuality
    env = _canonical_envelope()
    env["quality"] = "INVALID"
    field_obs = boundary_to_field_observation(env)
    assert field_obs.evidence.quality == EvidenceQuality.INVALID
    assert field_obs.health == "error"


def test_identical_input_produces_identical_envelope():
    env1 = observation_to_boundary(_make_obs(250, ts=1000, source_ts=500))
    env2 = observation_to_boundary(_make_obs(250, ts=1000, source_ts=500))
    assert env1["payload"]["value"] == env2["payload"]["value"]
    assert env1["sequence"] == env2["sequence"]
    assert env1["quality"] == env2["quality"]


def test_changed_value_changes_payload():
    env_a = observation_to_boundary(_make_obs(250, ts=1000, source_ts=500))
    env_b = observation_to_boundary(_make_obs(260, ts=1000, source_ts=500))
    assert env_a["payload"]["value"] != env_b["payload"]["value"]


def test_duplicate_ingest_distinct_sequences():
    reg = _registry()
    runtime = Runtime(reg, Node("temp_sensor_01", "Temp"), sink=InMemorySink(), clock=FixedClock(1000))
    gate = CANgate(runtime)
    data = bytes([0xFA, 0x00])
    frame = CanFrame(can_id=0x100, data=data, timestamp_ns=500)
    obs1 = gate.ingest(frame, ingest_timestamp_ns=1000, source_timestamp_ns=500)[0]
    obs2 = gate.ingest(frame, ingest_timestamp_ns=1001, source_timestamp_ns=501)[0]
    assert observation_to_boundary(obs1)["sequence"] != observation_to_boundary(obs2)["sequence"]


@pytest.mark.skipif(not _has_multiflow(), reason="MultiFlow sibling not available")
def test_admitted_requires_candidate_id():
    from multiflow import build_decision_evidence, OutcomeStatus
    with pytest.raises(ValueError) as ei:
        build_decision_evidence(snapshot_id="snap-1", outcome_status=OutcomeStatus.ADMITTED, admitted_candidate_id=None)
    assert "admitted_candidate_id" in str(ei.value)


@pytest.mark.skipif(not _has_multiflow(), reason="MultiFlow sibling not available")
def test_proposed_is_not_admitted():
    from multiflow import build_decision_evidence, OutcomeStatus, check_evidence_schema
    ev = build_decision_evidence(snapshot_id="snap-1", proposed_candidate_ids=["plan-a", "plan-b"], outcome_status=OutcomeStatus.PROPOSED)
    check_evidence_schema(ev)
    assert ev.outcome_status == OutcomeStatus.PROPOSED
    assert ev.admitted_candidate_id is None


@pytest.mark.skipif(not _has_multiflow(), reason="MultiFlow sibling not available")
def test_admitted_decision_has_identifier():
    from multiflow import build_decision_evidence, OutcomeStatus, check_evidence_schema
    ev = build_decision_evidence(
        snapshot_id="snap-1", proposed_candidate_ids=["plan-a", "plan-b"],
        admitted_candidate_id="plan-a", rejected_candidate_ids=["plan-b"],
        outcome_status=OutcomeStatus.ADMITTED,
    )
    check_evidence_schema(ev)
    assert ev.outcome_status == OutcomeStatus.ADMITTED
    assert ev.admitted_candidate_id == "plan-a"


@pytest.mark.skipif(not _has_multiflow(), reason="MultiFlow sibling not available")
def test_human_override_is_append_only_new_record():
    from multiflow import build_decision_evidence, OutcomeStatus
    original = build_decision_evidence(
        snapshot_id="snap-1", proposed_candidate_ids=["plan-a"],
        admitted_candidate_id="plan-a", outcome_status=OutcomeStatus.ADMITTED,
    )
    override = build_decision_evidence(
        snapshot_id="snap-1", proposed_candidate_ids=["plan-a", "plan-b"],
        admitted_candidate_id="plan-b", outcome_status=OutcomeStatus.OVERRIDE,
        human_override=True, override_reason="operator selected plan-b",
        override_of_decision_id=original.decision_id,
    )
    assert override.decision_id != original.decision_id
    assert override.human_override is True
    assert override.override_of_decision_id == original.decision_id
    assert original.outcome_status == OutcomeStatus.ADMITTED


@pytest.mark.skipif(not _has_aurora(), reason="aurora-swarm-btc sibling not available")
def test_aurora_content_hash_matches_payload():
    from mods.evidence_integrity import build_evidence_object, verify_integrity, IntegrityStatus, content_hash
    payload = {"kind": "test", "value": 42}
    obj = build_evidence_object(payload, node_id="n1", sequence=1)
    assert obj.content_hash == content_hash(payload)
    assert verify_integrity(obj) == IntegrityStatus.VALID


@pytest.mark.skipif(not _has_aurora(), reason="aurora-swarm-btc sibling not available")
def test_aurora_tamper_detected():
    from mods.evidence_integrity import build_evidence_object, verify_integrity, IntegrityStatus, EvidenceObject
    obj = build_evidence_object({"kind": "test", "value": 1}, node_id="n1")
    tampered = EvidenceObject(content_hash=obj.content_hash, payload={"kind": "test", "value": 999},
                              schema_id=obj.schema_id, schema_version=obj.schema_version)
    assert verify_integrity(tampered) == IntegrityStatus.HASH_MISMATCH


@pytest.mark.skipif(not _has_aurora(), reason="aurora-swarm-btc sibling not available")
def test_aurora_replicate_idempotent():
    from mods.evidence_integrity import build_evidence_object, EvidenceStore
    obj = build_evidence_object({"kind": "test", "seq": 1}, node_id="n1", sequence=1)
    store = EvidenceStore()
    store.append(obj)
    result = store.replicate([obj])
    assert obj.content_hash in result.duplicates
    assert len(store) == 1


@pytest.mark.skipif(not _has_aurora(), reason="aurora-swarm-btc sibling not available")
def test_aurora_schema_mismatch_fails_closed():
    from mods.evidence_integrity import build_evidence_object, check_schema, EvidenceObject
    obj = build_evidence_object({"kind": "x"}, node_id="n1")
    bad = EvidenceObject(content_hash=obj.content_hash, payload=obj.payload,
                         schema_id="wrong.schema", schema_version="0.1.0")
    with pytest.raises(ValueError):
        check_schema(bad)


@pytest.mark.skipif(not _has_aurora(), reason="aurora-swarm-btc sibling not available")
def test_aurora_append_rejects_hash_mismatch():
    from mods.evidence_integrity import EvidenceStore, EvidenceObject
    store = EvidenceStore()
    bad = EvidenceObject(content_hash="0" * 64, payload={"kind": "ok"})
    with pytest.raises(ValueError):
        store.append(bad)


def test_manifest_present_and_valid():
    path = REPO_ROOT / "config" / "chimera-compatibility.json"
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["manifest_version"] in ("1.1", "1.2")
    for name, entry in data["repositories"].items():
        if entry.get("required"):
            assert len(entry["commit"]) == 40


def test_manifest_relationships_reference_declared_repos():
    data = json.loads((REPO_ROOT / "config" / "chimera-compatibility.json").read_text())
    repo_names = set(data["repositories"].keys())
    for rel in data.get("compatibility_relationships") or []:
        assert rel["from"] in repo_names
        assert rel["to"] in repo_names


def test_check_compatibility_helpers():
    assert check_compatibility(SchemaIdentity("", "1.0"), SchemaIdentity("x", "1.0")) == Compatibility.UNKNOWN
    assert check_compatibility(SchemaIdentity("s", "1.0.0"), SchemaIdentity("s", "2.0.0")) == Compatibility.INCOMPATIBLE
