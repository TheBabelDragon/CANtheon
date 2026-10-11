# Cross-repository Shared Evidence Contract — conformance path

**Status:** Chimera Readiness Gate **v1.3** — adaptive scheduling demonstrator on top of the v1.2 evidence path.

## Path

```
CANtheon (boundary envelope)
    → MetaField (FieldObservation + EvidenceLineage)
    → TensorGate (ComputationalLineage)
    → MultiFlow (DecisionEvidence)
    → Aurora Mesh (EvidenceStore integrity + replication)
```

## Compatibility pins

Exact sibling commit SHAs are locked in `config/chimera-compatibility.json`.

- **Sibling pins** are exact: the Evidence Conformance workflow checks out those SHAs.
- **CANtheon pin** is **informational** (baseline verified with those siblings). CI checks out the **triggering** CANtheon commit for the event under test.

Update procedure: verify new sibling → edit SHA in the manifest → re-run `validate_chimera_manifest.py` and verification commands → commit → confirm CI uses the new pins.

## Verification commands

```bash
python scripts/validate_chimera_manifest.py
python -m pytest -q --tb=short
python -m pytest tests/test_chimera_failure_injection.py -q --tb=short
python scripts/evidence_conformance_smoke.py
python examples/live_host_wiring.py
python examples/chimera_controlled_demonstrator.py
python examples/chimera_adaptive_scheduling_demo.py
```

## Controlled demonstrator (v1.2)

```bash
python examples/chimera_controlled_demonstrator.py -o /tmp/chimera_demo_report.json
```

Synthetic end-to-end valid + invalid evidence scenarios. Report distinguishes PASS / FAIL / INCONCLUSIVE.

## Adaptive scheduling (v1.3)

```bash
python examples/chimera_adaptive_scheduling_demo.py -o /tmp/chimera_adaptive_report.json
```

See `docs/CHIMERA_ADAPTIVE_SCHEDULING.md`. Synthetic hospital-ops disruption; classical solver reassigns away from an offline resource. Acceptance criteria are computed from actual plans — not hard-coded success.

## CI

The **Evidence Conformance** workflow:

1. Checks out sibling repos at the exact SHAs in the manifest
2. Validates the manifest
3. Runs unit, failure-injection, smoke, live-host, controlled demonstrator, and adaptive scheduling demonstrator
4. Uploads `chimera-demo-report` and `chimera-adaptive-report` artifacts

A successful adaptive demonstrator is required to produce a report (`if-no-files-found: error`).

## Readiness

| Milestone | State |
|-----------|--------|
| v1.2 synthetic evidence path | DEMONSTRATOR_VERIFIED |
| v1.3 adaptive scheduling | DEMONSTRATOR_VERIFIED |

Not clinical validation, production readiness, or live hardware operation.
