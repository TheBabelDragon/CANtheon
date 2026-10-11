# Chimera v1.3 — Adaptive Scheduling Demonstrator

**Status:** Synthetic end-to-end adaptive scheduling demonstration.  
**Not** clinical validation, production readiness, or live hardware operation.

## Scenario

Fictional hospital day-shift operations:

| Resource | Role |
|----------|------|
| room-a, room-b | Procedure rooms (capacity 1) |
| tech-1, tech-2 | Technicians |

| Task | Duration | Window |
|------|----------|--------|
| Intake Screening | 30 min | 08:00–12:00 |
| Imaging Slot | 60 min | 09:00–15:00 |
| Consult Window | 45 min | 10:00–16:00 |
| Follow-up Check | 30 min | 12:00–17:00 |

**Disruption:** Room A goes offline (availability cleared).  
**Adaptation:** Classical solver reassigns tasks to remaining capacity (Room B + techs).

Constraints: NoOverlap, Availability, Capability.

## Command

```bash
python examples/chimera_adaptive_scheduling_demo.py -o /tmp/adaptive_report.json
```

Exit 0 only if all acceptance criteria pass.

## Acceptance criteria

1. Baseline schedule is admissible (zero hard violations).
2. Adapted schedule is admissible (zero hard violations).
3. Adapted plan does not assign work to offline Room A.
4. Evidence path CANtheon → MetaField → TensorGate → MultiFlow → Aurora Mesh all PASS.
5. Mesh integrity VALID; duplicate replication recorded.
6. Decision evidence outcome is ADMITTED (not merely proposed).

## Evidence trail

The disruption is emitted as a synthetic resource-status observation through the existing Shared Evidence Contract path. Quality, dual timestamps, lineage, decision admission, and mesh integrity are recorded in the JSON report.

## Metrics

Computed from actual solver output (not hard-coded):

- tasks assigned / total
- tasks within allowed windows
- hard violations / resource conflicts
- admissible flag
- tasks unassigned

## Determinism

Identical scenario seed and problem definition. Classical solver is deterministic. Repeated runs produce equivalent plans and metrics (decision UUIDs may differ).

## Limitations

- Synthetic data only; no patient records or PHI.
- In-memory mesh replication is not a distributed deployment.
- Does not claim hospital performance or clinical suitability.
- TensorGate path uses deterministic normalize only (no ML models).
