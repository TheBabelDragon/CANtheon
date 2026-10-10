# Cross-repository Shared Evidence Contract — conformance path

**Status:** Smoke path implemented and verified.

## Path

```
CANtheon (boundary envelope)
    → MetaField (FieldObservation + EvidenceLineage)
    → TensorGate (ComputationalLineage)
    → MultiFlow (DecisionEvidence)
    → Aurora Mesh (EvidenceStore integrity + replication)
```

## Smoke script

```bash
# Sibling checkouts of metafield, TensorGate, MultiFlow, aurora-swarm-btc
# next to this repo, then:
python scripts/evidence_conformance_smoke.py
```

Expected output ends with:

```
PASS  mesh content_hash=…
Path: CANtheon → MetaField → TensorGate → MultiFlow → Aurora Mesh
```

## What each step asserts

| Step | Checks |
|------|--------|
| CANtheon | Dual timestamps, sequence, quality, boundary envelope shape |
| MetaField | `boundary_to_field_observation`, evidence lineage, validation |
| TensorGate | Deterministic lineage, upstream evidence ref, schema check |
| MultiFlow | Admitted vs proposed, constraint versions, evidence ref |
| Aurora Mesh | Content-hash identity, integrity verify, replicate idempotent |

## Rules preserved end-to-end

- No silent quality rewrite
- Dual timestamps preserved into MetaField lineage
- DETERMINISTIC TensorGate lineage (no model_id)
- Solver proposals ≠ admitted results
- Mesh never rewrites history (duplicate = idempotent)

## Related docs

- `docs/SHARED_EVIDENCE_CONTRACT.md` (this repo)
- MetaField / TensorGate / MultiFlow / aurora-swarm-btc each carry their own `docs/SHARED_EVIDENCE_CONTRACT.md`
