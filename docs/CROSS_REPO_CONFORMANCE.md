# Cross-repository Shared Evidence Contract — conformance path

**Status:** Chimera Readiness Gate **v1.2** — behavior-driven failure injection + controlled demonstrator.

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

Update procedure: verify new sibling → edit SHA in manifest → run validator + all verification commands → commit → confirm CI.

## Verification commands

```bash
python scripts/validate_chimera_manifest.py
python -m pytest -q --tb=short
python -m pytest tests/test_chimera_failure_injection.py -q --tb=short
python scripts/evidence_conformance_smoke.py
python examples/live_host_wiring.py
python examples/chimera_controlled_demonstrator.py -o /tmp/chimera_demo_report.json
```

## What the failure-injection tests really exercise

| Area | Real boundary |
|------|----------------|
| Schema major / schema_id | CANtheon `assert_compatible` → `BoundaryError`; MetaField `boundary_to_field_observation` → `BoundaryAdapterError` |
| Missing node_id | MetaField rejects with `BoundaryAdapterError` |
| Dual timestamps | Preserved CANtheon → MetaField EvidenceLineage |
| Quality preservation | OUT_OF_RANGE / INVALID not upgraded to VALID through MetaField |
| Determinism | Identical inputs → identical envelopes; value change → different payload |
| Decision admission | MultiFlow: ADMITTED requires `admitted_candidate_id`; PROPOSED ≠ ADMITTED; OVERRIDE is new record |
| Mesh integrity | Aurora: content-hash identity, tamper → HASH_MISMATCH, replicate idempotent, schema fail-closed |

## Controlled demonstrator

```bash
python examples/chimera_controlled_demonstrator.py -o reports/chimera_demo.json
```

- **Valid scenario:** synthetic temperature observation through full path; admits a decision; mesh integrity VALID; replication accepted then duplicate.
- **Invalid scenario:** injects incompatible boundary major version; expects `BoundaryAdapterError` at MetaField; must not admit or publish.

Exit 0 only if both scenarios meet expectations. Synthetic fixtures only — not live hardware.

## Readiness states

| State | Meaning |
|-------|---------|
| BLOCKED | Required checks fail or pins missing |
| READY_FOR_DEMONSTRATOR | Pinned integration + failure-injection pass |
| DEMONSTRATOR_VERIFIED | Named demonstrator ran; valid PASS and invalid rejected; report recorded |

## Known gaps

- TensorGate NONDETERMINISTIC paths not covered.
- Human override is MultiFlow DecisionEvidence API (append-only new record), not a full operator UI path.
- No live CAN bus / hardware in CI.
