"""Chimera v1.3 — adaptive scheduling behavior-driven tests."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = REPO_ROOT.parent
EXAMPLES = REPO_ROOT / "examples"


def _add_paths() -> None:
    src = REPO_ROOT / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    for name, sub in (("metafield", ""), ("TensorGate", ""), ("MultiFlow", "src"),
                      ("aurora-swarm-btc", "")):
        base = WORKSPACE / name
        path = base / sub if sub else base
        if path.exists() and str(path) not in sys.path:
            sys.path.insert(0, str(path))


_add_paths()
sys.path.insert(0, str(EXAMPLES))
from chimera_adaptive_scheduling_demo import (  # noqa: E402
    build_baseline_problem, apply_disruption, solve_and_validate,
    emit_disruption_evidence, run as run_demo, SCENARIO_SEED,
)


def _has_multiflow() -> bool:
    try:
        from multiflow import SchedulingProblem  # noqa: F401
        return True
    except ImportError:
        return False


def _has_full_stack() -> bool:
    try:
        from adapters.cantheon_boundary import boundary_to_field_observation  # noqa: F401
        from multiflow import build_decision_evidence  # noqa: F401
        from mods.evidence_integrity import build_evidence_object  # noqa: F401
        from tensorgate import analyze  # noqa: F401
        return True
    except ImportError:
        return False


@pytest.mark.skipif(not _has_multiflow(), reason="MultiFlow not available")
def test_baseline_problem_is_solvable():
    cand, val, metrics = solve_and_validate(build_baseline_problem())
    assert cand is not None
    assert metrics["admissible"] is True
    assert metrics["hard_violations"] == 0
    assert metrics["tasks_assigned"] == metrics["tasks_total"]


@pytest.mark.skipif(not _has_multiflow(), reason="MultiFlow not available")
def test_disruption_removes_room_a_availability():
    disrupted, event = apply_disruption(build_baseline_problem())
    assert event["resource_id"] == "room-a"
    room_a = next(r for r in disrupted["resources"] if r["id"] == "room-a")
    assert room_a["availability"] == []


@pytest.mark.skipif(not _has_multiflow(), reason="MultiFlow not available")
def test_adapted_plan_avoids_offline_resource():
    disrupted, _ = apply_disruption(build_baseline_problem())
    cand, val, metrics = solve_and_validate(disrupted)
    assert cand is not None
    assert metrics["admissible"] is True
    for a in cand.assignments:
        assert "room-a" not in a.resource_ids


@pytest.mark.skipif(not _has_multiflow(), reason="MultiFlow not available")
def test_infeasible_not_reported_as_valid():
    broken = copy.deepcopy(build_baseline_problem())
    for r in broken["resources"]:
        if r["type"] == "room":
            r["availability"] = []
    cand, val, metrics = solve_and_validate(broken)
    if cand is not None and val is not None and metrics["hard_violations"] > 0:
        assert metrics["admissible"] is False


@pytest.mark.skipif(not _has_full_stack(), reason="full stack not available")
def test_disruption_produces_traceable_evidence():
    _, event = apply_disruption(build_baseline_problem())
    trail = emit_disruption_evidence(event)
    assert trail["envelope"]["node_id"]
    assert trail["decision"]["outcome_status"] == "ADMITTED"
    assert trail["mesh"]["integrity"] == "VALID"
    names = [b["boundary"] for b in trail["boundaries"]]
    assert names == ["CANtheon", "MetaField", "TensorGate", "MultiFlow", "Aurora Mesh"]


@pytest.mark.skipif(not _has_full_stack(), reason="full stack not available")
def test_incompatible_schema_rejected_at_metafield():
    from cantheon import CanFrame, Node, SchemaRegistry, Runtime, InMemorySink, CANgate, FixedClock
    from cantheon.adapters.metafield_contract import observation_to_boundary
    from adapters.cantheon_boundary import boundary_to_field_observation, BoundaryAdapterError
    reg = SchemaRegistry()
    reg.load_dict({"schema_version": "1.0", "schema_id": "resource_status.v1",
                   "node_id": "facility_monitor_01",
                   "messages": [{"message_id": 0x200, "name": "ResourceStatus", "dlc": 2,
                                 "signals": [{"signal_id": "online", "name": "Online",
                                              "start_bit": 0, "bit_length": 16, "is_signed": False,
                                              "scale": 1.0, "unit": "flag",
                                              "min_value": 0.0, "max_value": 1.0}]}]})
    runtime = Runtime(reg, Node("facility_monitor_01", "F"), sink=InMemorySink(), clock=FixedClock(1000))
    gate = CANgate(runtime)
    obs = gate.ingest(CanFrame(can_id=0x200, data=bytes([0, 0]), timestamp_ns=500),
                      ingest_timestamp_ns=1000, source_timestamp_ns=500)[0]
    env = observation_to_boundary(obs)
    env["boundary_schema_version"] = "1.0.0"
    with pytest.raises(BoundaryAdapterError):
        boundary_to_field_observation(env)


@pytest.mark.skipif(not _has_full_stack(), reason="full stack not available")
def test_quality_not_upgraded_through_metafield():
    from cantheon.adapters.metafield_contract import observation_to_boundary
    from adapters.cantheon_boundary import boundary_to_field_observation
    from schemas.evidence import EvidenceQuality
    from cantheon import CanFrame, Node, SchemaRegistry, Runtime, InMemorySink, CANgate, FixedClock
    reg = SchemaRegistry()
    reg.load_dict({"schema_version": "1.0", "schema_id": "resource_status.v1",
                   "node_id": "facility_monitor_01",
                   "messages": [{"message_id": 0x200, "name": "ResourceStatus", "dlc": 2,
                                 "signals": [{"signal_id": "online", "name": "Online",
                                              "start_bit": 0, "bit_length": 16, "is_signed": False,
                                              "scale": 1.0, "unit": "flag",
                                              "min_value": 0.0, "max_value": 1.0}]}]})
    runtime = Runtime(reg, Node("facility_monitor_01", "F"), sink=InMemorySink(), clock=FixedClock(1000))
    gate = CANgate(runtime)
    obs = gate.ingest(CanFrame(can_id=0x200, data=bytes([0, 0]), timestamp_ns=500),
                      ingest_timestamp_ns=1000, source_timestamp_ns=500)[0]
    env = observation_to_boundary(obs)
    env["quality"] = "OUT_OF_RANGE"
    fo = boundary_to_field_observation(env)
    assert fo.evidence.quality != EvidenceQuality.VALID
    assert fo.evidence.quality == EvidenceQuality.OUT_OF_RANGE


@pytest.mark.skipif(not _has_multiflow(), reason="MultiFlow not available")
def test_proposed_not_mislabeled_admitted():
    from multiflow import build_decision_evidence, OutcomeStatus, check_evidence_schema
    ev = build_decision_evidence(snapshot_id="snap-test",
                                 proposed_candidate_ids=["a", "b"],
                                 outcome_status=OutcomeStatus.PROPOSED)
    check_evidence_schema(ev)
    assert ev.outcome_status == OutcomeStatus.PROPOSED
    assert ev.admitted_candidate_id is None


@pytest.mark.skipif(not _has_multiflow(), reason="MultiFlow not available")
def test_override_creates_new_record():
    from multiflow import build_decision_evidence, OutcomeStatus
    original = build_decision_evidence(snapshot_id="snap-test",
                                       proposed_candidate_ids=["a"],
                                       admitted_candidate_id="a",
                                       outcome_status=OutcomeStatus.ADMITTED)
    override = build_decision_evidence(snapshot_id="snap-test",
                                       proposed_candidate_ids=["a", "b"],
                                       admitted_candidate_id="b",
                                       outcome_status=OutcomeStatus.OVERRIDE,
                                       human_override=True,
                                       override_of_decision_id=original.decision_id)
    assert override.decision_id != original.decision_id
    assert original.admitted_candidate_id == "a"


@pytest.mark.skipif(not _has_full_stack(), reason="full stack not available")
def test_tamper_detected_and_duplicate_idempotent():
    from mods.evidence_integrity import (build_evidence_object, verify_integrity,
                                         IntegrityStatus, EvidenceStore, EvidenceObject)
    obj = build_evidence_object({"kind": "t", "v": 1}, node_id="n", sequence=1)
    assert verify_integrity(obj) == IntegrityStatus.VALID
    bad = EvidenceObject(content_hash=obj.content_hash, payload={"kind": "t", "v": 99},
                         schema_id=obj.schema_id, schema_version=obj.schema_version)
    assert verify_integrity(bad) == IntegrityStatus.HASH_MISMATCH
    store = EvidenceStore(); store.append(obj)
    r = store.replicate([obj])
    assert obj.content_hash in r.duplicates


@pytest.mark.skipif(not _has_full_stack(), reason="full stack not available")
def test_deterministic_repeated_runs_equivalent_plans():
    r1, r2 = run_demo(), run_demo()
    assert r1["overall"] == "PASS" and r2["overall"] == "PASS"
    assert r1["adapted"]["plan"] == r2["adapted"]["plan"]
    assert r1["adapted"]["metrics"]["admissible"] == r2["adapted"]["metrics"]["admissible"]


@pytest.mark.skipif(not _has_full_stack(), reason="full stack not available")
def test_full_demo_passes_acceptance():
    report = run_demo()
    assert report["overall"] == "PASS"
    assert report["scenario_seed"] == SCENARIO_SEED
    failed = [c for c in report["acceptance_criteria"] if not c["pass"]]
    assert failed == []
