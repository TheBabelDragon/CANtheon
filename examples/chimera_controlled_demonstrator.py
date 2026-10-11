#!/usr/bin/env python3
"""Controlled Chimera demonstrator — synthetic end-to-end evidence path.

Uses real integration APIs from pinned sibling repositories.
Does NOT exercise live hardware or production CAN buses.

  python examples/chimera_controlled_demonstrator.py
  python examples/chimera_controlled_demonstrator.py --output reports/chimera_demo.json

Exit 0 only if valid scenario succeeds AND invalid scenario is rejected.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

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


def _load_pins() -> Dict[str, Any]:
    path = REPO_ROOT / "config" / "chimera-compatibility.json"
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _git_sha(repo_path: Path) -> str:
    head = repo_path / ".git" / "HEAD"
    if not head.is_file():
        return "unknown"
    ref = head.read_text().strip()
    if ref.startswith("ref:"):
        ref_path = repo_path / ".git" / ref.split(" ", 1)[1]
        if ref_path.is_file():
            return ref_path.read_text().strip()
    return ref if len(ref) == 40 else "unknown"


def run_valid() -> Dict[str, Any]:
    from cantheon import (
        CanFrame, Node, SchemaRegistry, Runtime, InMemorySink, CANgate, FixedClock,
    )
    from cantheon.adapters.metafield_contract import observation_to_boundary
    from adapters.cantheon_boundary import boundary_to_field_observation
    from schemas.field_observation import validate_observation
    import numpy as np
    from tensorgate import (
        analyze, normalize, build_lineage, ComputationKind,
        attach_evidence_ref, check_lineage_schema, identity_from_descriptor,
    )
    from multiflow import (
        build_decision_evidence, OutcomeStatus, ConstraintVersion,
        attach_evidence_ref as mf_attach, check_evidence_schema,
    )
    from mods.evidence_integrity import (
        build_evidence_object, verify_integrity, IntegrityStatus, EvidenceStore,
    )

    boundaries: List[Dict[str, Any]] = []

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
    runtime = Runtime(reg, Node("temp_sensor_01", "Temp"), sink=InMemorySink(), clock=FixedClock(1000))
    gate = CANgate(runtime)
    frame = CanFrame(can_id=0x100, data=bytes([0xFA, 0x00]), timestamp_ns=500)
    obs = gate.ingest(frame, ingest_timestamp_ns=1000, source_timestamp_ns=500)[0]
    env = observation_to_boundary(obs)
    boundaries.append({"boundary": "CANtheon", "status": "PASS", "node_id": env["node_id"],
                       "sequence": env["sequence"], "quality": env["quality"]})

    field_obs = boundary_to_field_observation(env)
    problems = validate_observation(field_obs)
    if problems:
        raise AssertionError(f"MetaField validation failed: {problems}")
    boundaries.append({"boundary": "MetaField", "status": "PASS",
                       "quality": field_obs.evidence.quality.value if field_obs.evidence else None})

    value = field_obs.field_regions[0].observed or 0.0
    arr = np.array([[value, value * 0.1], [0.0, 1.0]], dtype=np.float32)
    desc = analyze(arr)
    out, _ = normalize(arr, method="symmetric")
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
    boundaries.append({"boundary": "TensorGate", "status": "PASS", "kind": lin.kind.value})

    out_hash = lin.output.content_hash if lin.output else ""
    decision = build_decision_evidence(
        snapshot_id="chimera-demo-1",
        proposed_candidate_ids=["plan-a", "plan-b"],
        admitted_candidate_id="plan-a",
        rejected_candidate_ids=["plan-b"],
        rejection_reasons={"plan-b": "lower score"},
        outcome_status=OutcomeStatus.ADMITTED,
        constraint_versions=[ConstraintVersion(constraint_id="no_overlap", version="1.0")],
        solver_id="classical", solver_version="0.2.0",
        outcome_attributes={"tensor_output_hash": out_hash},
    )
    decision = mf_attach(
        decision, event_id=out_hash[:16] if out_hash else "lin",
        source_id="tensorgate", schema_id=lin.schema_id, schema_version=lin.schema_version,
    )
    check_evidence_schema(decision)
    assert decision.outcome_status == OutcomeStatus.ADMITTED
    boundaries.append({"boundary": "MultiFlow", "status": "PASS",
                       "outcome": decision.outcome_status.value,
                       "admitted": decision.admitted_candidate_id})

    payload = {
        "kind": "chimera_controlled_demonstrator",
        "cantheon": {"node_id": env.get("node_id"), "sequence": env.get("sequence"),
                     "quality": env.get("quality")},
        "multiflow": {"decision_id": decision.decision_id,
                      "outcome_status": decision.outcome_status.value},
    }
    mesh_obj = build_evidence_object(
        payload, node_id="chimera-demo", sequence=1,
        evidence_refs=[
            {"schema_id": "cantheon.metafield_boundary", "event_id": str(env.get("sequence"))},
            {"schema_id": "multiflow.decision_evidence", "event_id": decision.decision_id},
        ],
    )
    integrity = verify_integrity(mesh_obj)
    assert integrity == IntegrityStatus.VALID
    store = EvidenceStore()
    store.append(mesh_obj)
    peer = EvidenceStore()
    rep = peer.replicate([mesh_obj])
    assert mesh_obj.content_hash in rep.accepted
    rep2 = peer.replicate([mesh_obj])
    assert mesh_obj.content_hash in rep2.duplicates
    boundaries.append({"boundary": "Aurora Mesh", "status": "PASS",
                       "content_hash": mesh_obj.content_hash[:16],
                       "integrity": integrity.value})

    return {
        "scenario": "valid", "status": "PASS",
        "node_id": env["node_id"], "sequence": env["sequence"],
        "source_timestamp_ns": env["source_timestamp_ns"],
        "ingest_timestamp_ns": env["ingest_timestamp_ns"],
        "quality": env["quality"],
        "decision_status": decision.outcome_status.value,
        "admitted_candidate_id": decision.admitted_candidate_id,
        "mesh_content_hash": mesh_obj.content_hash,
        "mesh_integrity": integrity.value,
        "boundaries": boundaries,
    }


def run_invalid() -> Dict[str, Any]:
    from cantheon import (
        CanFrame, Node, SchemaRegistry, Runtime, InMemorySink, CANgate, FixedClock,
    )
    from cantheon.adapters.metafield_contract import observation_to_boundary
    from adapters.cantheon_boundary import boundary_to_field_observation, BoundaryAdapterError

    reg = SchemaRegistry()
    reg.load_dict({
        "schema_version": "1.0", "schema_id": "temp.v1", "node_id": "temp_sensor_01",
        "messages": [{
            "message_id": 0x100, "name": "TemperatureStatus", "dlc": 2,
            "signals": [{
                "signal_id": "temperature", "name": "Temperature",
                "start_bit": 0, "bit_length": 16, "is_signed": True,
                "scale": 0.1, "unit": "\u00b0C", "min_value": -40.0, "max_value": 125.0,
            }],
        }],
    })
    runtime = Runtime(reg, Node("temp_sensor_01", "Temp"), sink=InMemorySink(), clock=FixedClock(1000))
    gate = CANgate(runtime)
    frame = CanFrame(can_id=0x100, data=bytes([0xFA, 0x00]), timestamp_ns=500)
    obs = gate.ingest(frame, ingest_timestamp_ns=1000, source_timestamp_ns=500)[0]
    env = observation_to_boundary(obs)
    env["boundary_schema_version"] = "1.0.0"

    rejected = False
    error_msg = ""
    try:
        boundary_to_field_observation(env)
    except BoundaryAdapterError as exc:
        rejected = True
        error_msg = str(exc)

    return {
        "scenario": "invalid_schema_major",
        "status": "PASS" if rejected else "FAIL",
        "expected": "rejection at MetaField boundary (BoundaryAdapterError)",
        "observed_rejection": rejected,
        "error": error_msg,
        "admitted": False,
        "mesh_published": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Chimera controlled demonstrator")
    parser.add_argument("--output", "-o", type=str, default="",
                        help="Write machine-readable report JSON to this path")
    args = parser.parse_args()

    pins = _load_pins()
    report: Dict[str, Any] = {
        "demonstrator_id": "chimera-controlled-v1.2",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "cantheon_commit": _git_sha(REPO_ROOT),
        "sibling_pins": {
            name: entry.get("commit")
            for name, entry in (pins.get("repositories") or {}).items()
            if name != "CANtheon"
        },
        "contracts": pins.get("contracts"),
        "valid": None,
        "invalid": None,
        "overall": "FAIL",
    }

    print("=== Chimera Controlled Demonstrator v1.2 ===\n")
    try:
        valid = run_valid()
        report["valid"] = valid
        print("VALID scenario: PASS")
        for b in valid.get("boundaries") or []:
            print(f"  [{b['boundary']}] {b['status']}")
        print(f"  mesh_hash={valid.get('mesh_content_hash', '')[:16]}\u2026")
    except Exception as exc:
        report["valid"] = {"scenario": "valid", "status": "FAIL", "error": str(exc),
                           "traceback": traceback.format_exc()}
        print(f"VALID scenario: FAIL — {exc}")

    try:
        invalid = run_invalid()
        report["invalid"] = invalid
        print(f"\nINVALID scenario: {invalid['status']}")
        print(f"  rejection={invalid['observed_rejection']} error={invalid.get('error', '')[:80]}")
    except Exception as exc:
        report["invalid"] = {"scenario": "invalid", "status": "FAIL", "error": str(exc)}
        print(f"\nINVALID scenario: FAIL — {exc}")

    valid_ok = report.get("valid") and report["valid"].get("status") == "PASS"
    invalid_ok = report.get("invalid") and report["invalid"].get("status") == "PASS"
    report["overall"] = "PASS" if (valid_ok and invalid_ok) else "FAIL"

    print(f"\n=== overall: {report['overall']} ===")

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"report written: {out_path}")

    return 0 if report["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
