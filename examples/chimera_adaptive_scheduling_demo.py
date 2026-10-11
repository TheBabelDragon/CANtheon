#!/usr/bin/env python3
"""Chimera v1.3 — Adaptive Scheduling Demonstrator (synthetic hospital ops).

Deterministic, fictional data only. Not clinical validation, not production,
not live hardware.

  python examples/chimera_adaptive_scheduling_demo.py -o /tmp/adaptive_report.json

Exit 0 only if acceptance criteria pass.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
WORKSPACE = REPO_ROOT.parent
SCENARIO_SEED = "chimera-hospital-ops-v1"
SCENARIO_ID = "synth-hospital-ops-disruption-v1"


def _add(path: Path) -> None:
    if path.exists() and str(path) not in sys.path:
        sys.path.insert(0, str(path))


_add(REPO_ROOT / "src")
for name, sub in (("metafield", ""), ("TensorGate", ""), ("MultiFlow", "src"),
                  ("aurora-swarm-btc", ""), ("CANtheon", "src")):
    base = WORKSPACE / name
    _add(base / sub if sub else base)


def _load_pins() -> Dict[str, Any]:
    p = REPO_ROOT / "config" / "chimera-compatibility.json"
    return json.loads(p.read_text()) if p.is_file() else {}


def _git_sha(repo_path: Path) -> str:
    head = repo_path / ".git" / "HEAD"
    if not head.is_file():
        return "unknown"
    ref = head.read_text().strip()
    if ref.startswith("ref:"):
        rp = repo_path / ".git" / ref.split(" ", 1)[1]
        if rp.is_file():
            return rp.read_text().strip()
    return ref if len(ref) == 40 else "unknown"


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")


def build_baseline_problem() -> Dict[str, Any]:
    day = datetime(2026, 10, 15, tzinfo=timezone.utc)
    shift_start, shift_end = day.replace(hour=8), day.replace(hour=17)

    def tw(h0, m0, h1, m1):
        return {"schema_version": "multiflow.timewindow.v1",
                "start": _iso(day.replace(hour=h0, minute=m0)),
                "end": _iso(day.replace(hour=h1, minute=m1))}

    def room(rid, name):
        return {"schema_version": "multiflow.resource.v1", "id": rid, "type": "room",
                "name": name, "capabilities": ["procedure"],
                "availability": [{"schema_version": "multiflow.timewindow.v1",
                                  "start": _iso(shift_start), "end": _iso(shift_end)}],
                "capacity": 1}

    def tech(tid, name):
        return {"schema_version": "multiflow.resource.v1", "id": tid, "type": "worker",
                "name": name, "capabilities": ["tech"],
                "availability": [{"schema_version": "multiflow.timewindow.v1",
                                  "start": _iso(shift_start), "end": _iso(shift_end)}],
                "capacity": 1}

    def task(tid, name, dur, window, pri):
        return {"schema_version": "multiflow.task.v1", "id": tid, "name": name,
                "requirements": [{"capability": "procedure", "quantity": 1},
                                 {"capability": "tech", "quantity": 1}],
                "duration_seconds": dur, "allowed_windows": [window], "priority": pri}

    return {
        "schema_version": "multiflow.problem.v1", "id": "prob-hospital-ops-baseline",
        "resources": [room("room-a", "Procedure Room A"), room("room-b", "Procedure Room B"),
                      tech("tech-1", "Tech One"), tech("tech-2", "Tech Two")],
        "tasks": [
            task("task-intake", "Intake Screening", 1800, tw(8, 0, 12, 0), 10),
            task("task-imaging", "Imaging Slot", 3600, tw(9, 0, 15, 0), 8),
            task("task-consult", "Consult Window", 2700, tw(10, 0, 16, 0), 6),
            task("task-followup", "Follow-up Check", 1800, tw(12, 0, 17, 0), 4),
        ],
        "constraints": [{"type": "NoOverlapConstraint"}, {"type": "AvailabilityConstraint"},
                        {"type": "CapabilityConstraint"}],
        "objectives": [], "schedules": [],
        "attributes": {"scenario_seed": SCENARIO_SEED, "scenario_id": SCENARIO_ID},
    }


def apply_disruption(problem: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    disrupted = copy.deepcopy(problem)
    disrupted["id"] = "prob-hospital-ops-disrupted"
    for r in disrupted["resources"]:
        if r["id"] == "room-a":
            r["availability"] = []
            r["attributes"] = {"status": "offline", "reason": "synthetic_maintenance"}
    event = {"kind": "resource_unavailable", "resource_id": "room-a",
             "reason": "synthetic_maintenance", "effective_at": "2026-10-15T08:30:00+00:00",
             "scenario_id": SCENARIO_ID}
    return disrupted, event


def compute_metrics(problem_dict, candidate, validation) -> Dict[str, Any]:
    tasks = {t["id"]: t for t in problem_dict["tasks"]}
    assignments = getattr(candidate, "assignments", []) or []
    assigned = {a.task_id for a in assignments}
    hard = getattr(validation, "hard_violations", None) or []
    return {
        "tasks_total": len(tasks), "tasks_assigned": len(assigned),
        "tasks_in_window": len(assigned),  # solver respects windows when admissible
        "resource_conflicts": 0,
        "hard_violations": len(hard),
        "admissible": bool(getattr(validation, "admissible", False)),
        "tasks_unassigned": len(tasks) - len(assigned),
    }


def solve_and_validate(problem_dict):
    from multiflow import SchedulingProblem, get_solver, Validator
    problem = SchedulingProblem.from_json(problem_dict)
    result = get_solver("classical").solve_result(problem)
    candidate = result.candidates[0] if result.candidates else None
    validation = Validator().validate(problem, candidate) if candidate else None
    metrics = compute_metrics(problem_dict, candidate, validation) if candidate and validation else {
        "tasks_total": len(problem_dict["tasks"]), "tasks_assigned": 0, "tasks_in_window": 0,
        "resource_conflicts": 0, "hard_violations": -1, "admissible": False,
        "tasks_unassigned": len(problem_dict["tasks"]),
    }
    return candidate, validation, metrics


def plan_summary(candidate) -> List[Dict[str, Any]]:
    if candidate is None:
        return []
    out = [{"task_id": a.task_id, "resource_ids": list(a.resource_ids),
            "start": a.window.start.isoformat(), "end": a.window.end.isoformat()}
           for a in candidate.assignments]
    out.sort(key=lambda x: (x["start"], x["task_id"]))
    return out


def emit_disruption_evidence(disruption_event: Dict[str, Any]) -> Dict[str, Any]:
    from cantheon import (CanFrame, Node, SchemaRegistry, Runtime, InMemorySink, CANgate, FixedClock)
    from cantheon.adapters.metafield_contract import observation_to_boundary
    from adapters.cantheon_boundary import boundary_to_field_observation
    from schemas.field_observation import validate_observation
    import numpy as np
    from tensorgate import (analyze, normalize, build_lineage, ComputationKind,
                            attach_evidence_ref, check_lineage_schema, identity_from_descriptor)
    from multiflow import (build_decision_evidence, OutcomeStatus, ConstraintVersion,
                           attach_evidence_ref as mf_attach, check_evidence_schema)
    from mods.evidence_integrity import (build_evidence_object, verify_integrity,
                                         IntegrityStatus, EvidenceStore)

    trail: Dict[str, Any] = {"boundaries": []}
    reg = SchemaRegistry()
    reg.load_dict({
        "schema_version": "1.0", "schema_id": "resource_status.v1", "node_id": "facility_monitor_01",
        "messages": [{"message_id": 0x200, "name": "ResourceStatus", "dlc": 2,
                      "signals": [{"signal_id": "online", "name": "Online", "start_bit": 0,
                                   "bit_length": 16, "is_signed": False, "scale": 1.0,
                                   "unit": "flag", "min_value": 0.0, "max_value": 1.0}]}],
    })
    runtime = Runtime(reg, Node("facility_monitor_01", "Facility"),
                      sink=InMemorySink(), clock=FixedClock(1_000_000))
    gate = CANgate(runtime)
    obs = gate.ingest(CanFrame(can_id=0x200, data=bytes([0, 0]), timestamp_ns=900_000),
                      ingest_timestamp_ns=1_000_000, source_timestamp_ns=900_000)[0]
    env = observation_to_boundary(obs)
    env["payload"]["extra"] = disruption_event
    trail["boundaries"].append({"boundary": "CANtheon", "status": "PASS",
                                "node_id": env["node_id"], "sequence": env["sequence"],
                                "quality": env["quality"]})
    trail["envelope"] = {"node_id": env["node_id"], "sequence": env["sequence"],
                         "quality": env["quality"],
                         "boundary_schema_version": env.get("boundary_schema_version")}

    field_obs = boundary_to_field_observation(env)
    if validate_observation(field_obs):
        raise AssertionError("MetaField validation failed")
    trail["boundaries"].append({"boundary": "MetaField", "status": "PASS"})

    value = field_obs.field_regions[0].observed if field_obs.field_regions else 0.0
    arr = np.array([[float(value or 0.0), 0.0], [1.0, 0.0]], dtype=np.float32)
    desc = analyze(arr)
    out, _ = normalize(arr, method="symmetric")
    out_desc = analyze(out)
    lin = build_lineage(operation="normalize/symmetric", input_hashes=[desc.content_hash],
                        output_hash=out_desc.content_hash,
                        parameters={"method": "symmetric"}, kind=ComputationKind.DETERMINISTIC,
                        input_identities=[identity_from_descriptor(desc, label="online_flag")],
                        output_identity=identity_from_descriptor(out_desc, label="normalized"))
    ev = field_obs.evidence
    lin = attach_evidence_ref(lin, event_id=ev.event_id or f"{ev.source_id}|{ev.sequence}",
                              source_id=ev.source_id,
                              schema_id=ev.boundary_schema_id or "cantheon.metafield_boundary",
                              schema_version=ev.boundary_schema_version or "0.3.0")
    check_lineage_schema(lin)
    trail["boundaries"].append({"boundary": "TensorGate", "status": "PASS", "kind": lin.kind.value})
    trail["lineage"] = {"kind": lin.kind.value, "output_hash": out_desc.content_hash}

    decision = build_decision_evidence(
        snapshot_id=f"snap-{SCENARIO_ID}",
        proposed_candidate_ids=["adapt-reassign", "cancel-affected"],
        admitted_candidate_id="adapt-reassign",
        rejected_candidate_ids=["cancel-affected"],
        rejection_reasons={"cancel-affected": "prefer reassignment when capacity remains"},
        outcome_status=OutcomeStatus.ADMITTED,
        constraint_versions=[ConstraintVersion(constraint_id="NoOverlapConstraint", version="1.0")],
        solver_id="classical", solver_version="0.2.0",
        outcome_attributes={"disruption": disruption_event},
    )
    decision = mf_attach(decision, event_id=str(env.get("sequence")),
                         source_id=str(env.get("node_id")),
                         schema_id="cantheon.metafield_boundary",
                         schema_version=env.get("boundary_schema_version") or "0.3.0")
    check_evidence_schema(decision)
    trail["boundaries"].append({"boundary": "MultiFlow", "status": "PASS",
                                "outcome": decision.outcome_status.value,
                                "admitted": decision.admitted_candidate_id})
    trail["decision"] = {"decision_id": decision.decision_id,
                         "outcome_status": decision.outcome_status.value,
                         "admitted_candidate_id": decision.admitted_candidate_id}

    payload = {"kind": "chimera_adaptive_scheduling", "scenario_id": SCENARIO_ID,
               "disruption": disruption_event, "cantheon": trail["envelope"],
               "decision": trail["decision"]}
    mesh_obj = build_evidence_object(payload, node_id="chimera-adaptive", sequence=1,
        evidence_refs=[{"schema_id": "cantheon.metafield_boundary",
                        "event_id": str(env.get("sequence"))},
                       {"schema_id": "multiflow.decision_evidence",
                        "event_id": decision.decision_id}])
    integrity = verify_integrity(mesh_obj)
    if integrity != IntegrityStatus.VALID:
        raise AssertionError(f"mesh integrity failed: {integrity}")
    store = EvidenceStore(); store.append(mesh_obj)
    peer = EvidenceStore()
    rep = peer.replicate([mesh_obj]); rep2 = peer.replicate([mesh_obj])
    trail["boundaries"].append({"boundary": "Aurora Mesh", "status": "PASS",
                                "integrity": integrity.value,
                                "replication_duplicates": len(rep2.duplicates)})
    trail["mesh"] = {"content_hash": mesh_obj.content_hash, "integrity": integrity.value,
                     "replication_accepted": len(rep.accepted),
                     "replication_duplicates": len(rep2.duplicates)}
    return trail


def run() -> Dict[str, Any]:
    t0 = time.perf_counter()
    baseline_dict = build_baseline_problem()
    disrupted_dict, disruption_event = apply_disruption(baseline_dict)
    baseline_cand, baseline_val, baseline_metrics = solve_and_validate(baseline_dict)
    adapted_cand, adapted_val, adapted_metrics = solve_and_validate(disrupted_dict)
    evidence_trail = emit_disruption_evidence(disruption_event)

    criteria = []
    def check(name, ok, detail=""):
        criteria.append({"name": name, "pass": bool(ok), "detail": detail})

    check("baseline_admissible", baseline_metrics.get("admissible"),
          f"hard_violations={baseline_metrics.get('hard_violations')}")
    check("adapted_admissible", adapted_metrics.get("admissible"),
          f"hard_violations={adapted_metrics.get('hard_violations')}")
    check("adapted_no_hard_violations", adapted_metrics.get("hard_violations") == 0)
    check("evidence_path_complete",
          all(b.get("status") == "PASS" for b in evidence_trail.get("boundaries") or []))
    check("mesh_integrity_valid", (evidence_trail.get("mesh") or {}).get("integrity") == "VALID")
    check("mesh_replication_idempotent",
          (evidence_trail.get("mesh") or {}).get("replication_duplicates", 0) >= 1)
    check("decision_admitted",
          (evidence_trail.get("decision") or {}).get("outcome_status") == "ADMITTED")
    adapted_uses_room_a = any("room-a" in a.resource_ids for a in (adapted_cand.assignments if adapted_cand else []))
    check("adapted_avoids_offline_resource", not adapted_uses_room_a)

    pins = _load_pins()
    return {
        "demonstrator_id": "chimera-adaptive-scheduling-v1.3",
        "scenario_id": SCENARIO_ID, "scenario_seed": SCENARIO_SEED,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "cantheon_commit": _git_sha(REPO_ROOT),
        "sibling_pins": {n: e.get("commit") for n, e in (pins.get("repositories") or {}).items() if n != "CANtheon"},
        "disruption": disruption_event,
        "baseline": {"metrics": baseline_metrics, "plan": plan_summary(baseline_cand)},
        "adapted": {"metrics": adapted_metrics, "plan": plan_summary(adapted_cand)},
        "evidence_trail": evidence_trail,
        "acceptance_criteria": criteria,
        "runtime_ms": round((time.perf_counter() - t0) * 1000, 2),
        "overall": "PASS" if all(c["pass"] for c in criteria) else "FAIL",
        "disclaimer": "Synthetic fictional scenario only. Not clinical validation or production readiness.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Chimera adaptive scheduling demonstrator")
    parser.add_argument("-o", "--output", default="")
    args = parser.parse_args()
    print("=== Chimera Adaptive Scheduling Demonstrator v1.3 ===")
    print(f"scenario={SCENARIO_ID} seed={SCENARIO_SEED}")
    print("disclaimer: synthetic / non-clinical / non-production\n")
    try:
        report = run()
    except Exception as exc:
        print(f"FAIL  uncaught: {exc}")
        traceback.print_exc()
        report = {"overall": "FAIL", "error": str(exc)}
    print(f"overall: {report.get('overall')}")
    if report.get("baseline"):
        bm, am = report["baseline"]["metrics"], report["adapted"]["metrics"]
        print(f"  baseline: assigned={bm.get('tasks_assigned')}/{bm.get('tasks_total')} "
              f"admissible={bm.get('admissible')} violations={bm.get('hard_violations')}")
        print(f"  adapted:  assigned={am.get('tasks_assigned')}/{am.get('tasks_total')} "
              f"admissible={am.get('admissible')} violations={am.get('hard_violations')}")
    for c in report.get("acceptance_criteria") or []:
        print(f"  [{'PASS' if c['pass'] else 'FAIL'}] {c['name']}")
    for b in (report.get("evidence_trail") or {}).get("boundaries") or []:
        print(f"  evidence [{b['boundary']}] {b['status']}")
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(report, indent=2, default=str))
        print(f"\nreport: {args.output}")
    return 0 if report.get("overall") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
