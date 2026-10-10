#!/usr/bin/env python3
"""Cross-repo Shared Evidence Contract conformance smoke path.

Path:
  CANtheon boundary envelope
    → MetaField FieldObservation (+ EvidenceLineage)
    → TensorGate ComputationalLineage
    → MultiFlow DecisionEvidence
    → Aurora Mesh EvidenceStore (integrity + replication)

  python scripts/evidence_conformance_smoke.py
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
WORKSPACE = REPO_ROOT.parent


def _add(path: Path) -> None:
    if path.exists() and str(path) not in sys.path:
        sys.path.insert(0, str(path))


_add(REPO_ROOT / "src")
for name, sub in (
    ("metafield", ""),
    ("TensorGate", ""),
    ("MultiFlow", "src"),
    ("aurora-swarm-btc", ""),
    ("CANtheon", "src"),
):
    base = WORKSPACE / name
    _add(base / sub if sub else base)


def step_cantheon_envelope() -> dict:
    from cantheon import (
        CanFrame,
        Node,
        SchemaRegistry,
        Runtime,
        InMemorySink,
        CANgate,
        FixedClock,
    )
    from cantheon.adapters.metafield_contract import observation_to_boundary

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
    runtime = Runtime(
        reg,
        Node("temp_sensor_01", "Temp"),
        sink=InMemorySink(),
        clock=FixedClock(1000),
    )
    gate = CANgate(runtime)
    data = bytes([0xFA, 0x00])
    frame = CanFrame(can_id=0x100, data=data, timestamp_ns=500)
    obs = gate.ingest(
        frame,
        ingest_timestamp_ns=1000,
        source_timestamp_ns=500,
    )[0]
    env = observation_to_boundary(obs)
    assert env["kind"] == "observation"
    assert env["node_id"] == "temp_sensor_01"
    assert abs(env["payload"]["value"] - 25.0) < 1e-9
    assert env["source_timestamp_ns"] == 500
    assert env["ingest_timestamp_ns"] == 1000
    print("  [1] CANtheon boundary envelope OK")
    return env


def step_metafield(envelope: dict):
    from adapters.cantheon_boundary import boundary_to_field_observation
    from schemas.evidence import EvidenceKind, EvidenceQuality
    from schemas.field_observation import validate_observation

    obs = boundary_to_field_observation(envelope)
    problems = validate_observation(obs)
    assert problems == [], problems
    assert obs.evidence is not None
    assert obs.evidence.kind == EvidenceKind.RAW
    assert obs.evidence.quality == EvidenceQuality.VALID
    assert obs.evidence.source_id == "temp_sensor_01"
    assert obs.evidence.sequence == envelope.get("sequence")
    print("  [2] MetaField FieldObservation + EvidenceLineage OK")
    return obs


def step_tensorgate(field_obs):
    import numpy as np
    from tensorgate import (
        analyze,
        normalize,
        build_lineage,
        ComputationKind,
        attach_evidence_ref,
        check_lineage_schema,
        identity_from_descriptor,
    )

    value = field_obs.field_regions[0].observed or 0.0
    arr = np.array([[value, value * 0.1], [0.0, 1.0]], dtype=np.float32)
    desc = analyze(arr)
    out, _meta = normalize(arr, method="symmetric")
    out_desc = analyze(out)

    lin = build_lineage(
        operation="normalize/symmetric",
        input_hashes=[desc.content_hash],
        output_hash=out_desc.content_hash,
        parameters={"method": "symmetric"},
        kind=ComputationKind.DETERMINISTIC,
        input_identities=[identity_from_descriptor(desc, label="field_value")],
        output_identity=identity_from_descriptor(out_desc, label="normalized"),
    )
    ev = field_obs.evidence
    lin = attach_evidence_ref(
        lin,
        event_id=ev.event_id or f"{ev.source_id}|{ev.sequence}",
        source_id=ev.source_id,
        schema_id=ev.boundary_schema_id or "cantheon.metafield_boundary",
        schema_version=ev.boundary_schema_version or "0.3.0",
    )
    check_lineage_schema(lin)
    assert lin.kind == ComputationKind.DETERMINISTIC
    assert len(lin.evidence_refs) >= 1
    print("  [3] TensorGate ComputationalLineage OK")
    return lin


def step_multiflow(lineage):
    from multiflow import (
        build_decision_evidence,
        OutcomeStatus,
        ConstraintVersion,
        attach_evidence_ref,
        check_evidence_schema,
    )

    out_hash = lineage.output.content_hash if lineage.output else ""
    ev = build_decision_evidence(
        snapshot_id="snap-conformance-1",
        proposed_candidate_ids=["plan-a", "plan-b"],
        admitted_candidate_id="plan-a",
        rejected_candidate_ids=["plan-b"],
        rejection_reasons={"plan-b": "lower score"},
        outcome_status=OutcomeStatus.ADMITTED,
        constraint_versions=[
            ConstraintVersion(constraint_id="no_overlap", version="1.0"),
        ],
        solver_id="classical",
        solver_version="0.2.0",
        outcome_attributes={"tensor_output_hash": out_hash},
    )
    ev = attach_evidence_ref(
        ev,
        event_id=out_hash[:16] if out_hash else "lin",
        source_id="tensorgate",
        schema_id=lineage.schema_id,
        schema_version=lineage.schema_version,
    )
    check_evidence_schema(ev)
    assert ev.admitted_candidate_id == "plan-a"
    assert ev.outcome_status == OutcomeStatus.ADMITTED
    print("  [4] MultiFlow DecisionEvidence OK")
    return ev


def step_aurora(decision_ev, lineage, field_obs, envelope: dict):
    from mods.evidence_integrity import (
        build_evidence_object,
        verify_integrity,
        IntegrityStatus,
        EvidenceStore,
        check_schema,
    )

    payload = {
        "kind": "shared_evidence_chain",
        "cantheon": {
            "node_id": envelope.get("node_id"),
            "sequence": envelope.get("sequence"),
            "quality": envelope.get("quality"),
            "source_timestamp_ns": envelope.get("source_timestamp_ns"),
            "ingest_timestamp_ns": envelope.get("ingest_timestamp_ns"),
        },
        "metafield": {
            "body_id": field_obs.body_id,
            "body_type": field_obs.body_type,
            "health": field_obs.health,
            "evidence_quality": (
                field_obs.evidence.quality.value if field_obs.evidence else None
            ),
        },
        "tensorgate": {
            "transformation_id": lineage.transformation_id,
            "output_hash": lineage.output.content_hash if lineage.output else None,
            "kind": lineage.kind.value,
        },
        "multiflow": {
            "decision_id": decision_ev.decision_id,
            "outcome_id": decision_ev.outcome_id,
            "outcome_status": decision_ev.outcome_status.value,
            "admitted_candidate_id": decision_ev.admitted_candidate_id,
        },
    }
    obj = build_evidence_object(
        payload,
        node_id="conformance-runner",
        sequence=1,
        evidence_refs=[
            {
                "schema_id": "cantheon.metafield_boundary",
                "event_id": str(envelope.get("sequence")),
            },
            {
                "schema_id": "tensorgate.lineage",
                "event_id": (lineage.output.content_hash[:16] if lineage.output else ""),
            },
            {
                "schema_id": "multiflow.decision_evidence",
                "event_id": decision_ev.decision_id,
            },
        ],
    )
    assert verify_integrity(obj) == IntegrityStatus.VALID
    check_schema(obj)

    store_a = EvidenceStore()
    store_a.append(obj)

    store_b = EvidenceStore()
    result = store_b.replicate([obj])
    assert obj.content_hash in result.accepted
    assert len(store_b) == 1
    assert verify_integrity(store_b.get(obj.content_hash)) == IntegrityStatus.VALID

    result2 = store_b.replicate([obj])
    assert obj.content_hash in result2.duplicates
    assert len(store_b) == 1

    print("  [5] Aurora Mesh EvidenceStore integrity + replication OK")
    return obj.content_hash


def main() -> int:
    print("Shared Evidence Contract — cross-repo conformance smoke")
    print("=" * 60)
    envelope = step_cantheon_envelope()
    field_obs = step_metafield(envelope)
    lineage = step_tensorgate(field_obs)
    decision = step_multiflow(lineage)
    mesh_hash = step_aurora(decision, lineage, field_obs, envelope)
    print("=" * 60)
    print(f"PASS  mesh content_hash={mesh_hash[:16]}\u2026")
    print("Path: CANtheon \u2192 MetaField \u2192 TensorGate \u2192 MultiFlow \u2192 Aurora Mesh")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FAIL  {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
