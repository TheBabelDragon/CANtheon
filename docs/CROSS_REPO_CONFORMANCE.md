# Cross-repository Shared Evidence Contract — conformance path

**Status:** Chimera Readiness Gate v1.1 — pinned, failure-tested integration path.

**Readiness:** See `config/chimera-compatibility.json` → `verification_status` and the latest CI run.

## Path

```
CANtheon (boundary envelope)
    → MetaField (FieldObservation + EvidenceLineage)
    → TensorGate (ComputationalLineage)
    → MultiFlow (DecisionEvidence)
    → Aurora Mesh (EvidenceStore integrity + replication)
```

## Compatibility pins

Exact commit SHAs are locked in:

```
config/chimera-compatibility.json
```

The Evidence Conformance workflow checks out **those exact revisions**, not floating `main`.  
Updating a pin is intentional:

1. Verify the new sibling commit passes local smoke + failure-injection.
2. Edit the SHA in the manifest.
3. Run `python scripts/validate_chimera_manifest.py` and all verification commands.
4. Commit the manifest change; confirm CI consumes the new pins.

## Local setup (sibling checkouts)

```bash
# Workspace layout (siblings next to CANtheon):
#   CANtheon/  metafield/  TensorGate/  MultiFlow/  aurora-swarm-btc/

python -m pip install -e "CANtheon[dev]" -e TensorGate -e MultiFlow
python -m pip install numpy pydantic
```

## Exact verification commands

```bash
python scripts/validate_chimera_manifest.py
python -m pytest -q --tb=short
python -m pytest tests/test_chimera_failure_injection.py -q --tb=short
python scripts/evidence_conformance_smoke.py
python examples/live_host_wiring.py
```

Expected smoke ending:

```
PASS  mesh content_hash=…
Path: CANtheon → MetaField → TensorGate → MultiFlow → Aurora Mesh
```

## What each step asserts

| Step | Checks |
|------|--------|
| CANtheon | Dual timestamps, sequence, quality, boundary envelope shape (`cantheon.metafield_boundary@0.3.0`) |
| MetaField | `boundary_to_field_observation`, evidence lineage, validation |
| TensorGate | Deterministic lineage, upstream evidence ref, schema check |
| MultiFlow | Admitted vs proposed, constraint versions, evidence ref |
| Aurora Mesh | Content-hash identity, integrity verify, replicate idempotent |

## Failure-injection coverage

`tests/test_chimera_failure_injection.py` covers:

- Unsupported schema major version → `BoundaryError` (fail-closed)
- Different schema_id → rejected
- Missing source timestamp remains explicit `None` (never fabricated on envelope)
- Dual timestamps preserved
- Quality not silently rewritten to VALID
- Identical canonical input → identical envelope (determinism)
- Duplicate ingest → distinct sequences; envelopes remain valid
- Manifest structural validation (SHAs, contract versions)

## Rules preserved end-to-end

- No silent quality rewrite
- Dual timestamps preserved into MetaField lineage
- DETERMINISTIC TensorGate lineage (no model_id)
- Solver proposals ≠ admitted results
- Mesh never rewrites history (duplicate = idempotent)
- Unsupported schema major → fail-closed

## CI

`.github/workflows/evidence_conformance.yml`:

1. Reads pin SHAs from the compatibility manifest
2. Checks out each sibling at the pinned commit
3. Validates the manifest
4. Runs unit tests, failure-injection tests, smoke, and live host wiring
5. Returns nonzero on any failure; does not silently skip missing integrations

Unit-only matrix remains in `.github/workflows/ci.yml` (Python 3.11 / 3.12).

## Related docs

- `docs/SHARED_EVIDENCE_CONTRACT.md` (this repo)
- MetaField / TensorGate / MultiFlow / aurora-swarm-btc each carry their own `docs/SHARED_EVIDENCE_CONTRACT.md`
- `config/chimera-compatibility.json` — authoritative pins and verification status
