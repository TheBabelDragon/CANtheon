#!/usr/bin/env python3
"""Live host wiring: CANgate → MetaField → MultiFlow decision evidence → Aurora Mesh.

Host-side only. CANtheon does not import MetaField/MultiFlow/Aurora.
Sibling checkouts (or installed packages) supply downstream adapters.

  PYTHONPATH=src python examples/live_host_wiring.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, List

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
WORKSPACE = REPO_ROOT.parent


def _add(path: Path) -> None:
    if path.exists() and str(path) not in sys.path:
        sys.path.insert(0, str(path))


_add(REPO_ROOT / "src")
for name, sub in (
    ("metafield", ""),
    ("MultiFlow", "src"),
    ("aurora-swarm-btc", ""),
    ("CANtheon", "src"),
):
    base = WORKSPACE / name
    _add(base / sub if sub else base)


class LiveHost:
    """Wires CANgate publish hooks into MetaField, MultiFlow, and Aurora Mesh."""

    def __init__(self) -> None:
        from cantheon import (
            Node,
            SchemaRegistry,
            Runtime,
            InMemorySink,
            CANgate,
            FixedClock,
        )
        from cantheon.adapters.metafield_contract import event_to_boundary
        from multiflow import SchedulingProblem, LiveEngine, DecisionSource
        from mods.evidence_integrity import (
            EvidenceStore,
            build_evidence_object,
            verify_integrity,
            IntegrityStatus,
        )

        schema_path = REPO_ROOT / "schemas" / "example_node.json"
        registry = SchemaRegistry()
        if schema_path.exists():
            registry.load_json(schema_path)
        else:
            registry.load_dict(
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
                                    "unit": "\u00b0C",
                                    "min_value": -40.0,
                                    "max_value": 125.0,
                                }
                            ],
                        }
                    ],
                }
            )

        self.runtime = Runtime(
            registry,
            Node("temp_sensor_01", "Temp Sensor"),
            sink=InMemorySink(),
            clock=FixedClock(0),
        )
        self.gate = CANgate(self.runtime)
        self._event_to_boundary = event_to_boundary

        from adapters.cantheon_boundary import boundary_to_field_observation
        from schemas.field_observation import validate_observation

        self._to_field = boundary_to_field_observation
        self._validate_obs = validate_observation
        self.field_observations: List[Any] = []

        problem_path = WORKSPACE / "MultiFlow" / "examples" / "simple.json"
        self.engine = LiveEngine(
            initial_problem=SchedulingProblem.from_json(str(problem_path))
        )
        self.DecisionSource = DecisionSource

        self.mesh = EvidenceStore()
        self._build_evidence_object = build_evidence_object
        self._verify_integrity = verify_integrity
        self.IntegrityStatus = IntegrityStatus

        self.boundary_envelopes: List[dict] = []
        self.mesh_hashes: List[str] = []

        self.gate.on_publish(self._on_publish)

    def _on_publish(self, event: Any) -> None:
        envelope = self._event_to_boundary(event)
        self.boundary_envelopes.append(envelope)

        field_obs = self._to_field(envelope)
        problems = self._validate_obs(field_obs)
        if problems:
            return
        self.field_observations.append(field_obs)

        result = self.engine.recalculate()
        selected = None
        if result["has_admissible_plan"] and result["ranked"]:
            selected = result["ranked"][0][0].id
        elif result["admissible"]:
            selected = result["admissible"][0].id

        record = self.engine.record_decision(
            selected_candidate_id=selected,
            source=self.DecisionSource.SOLVER,
            outcome={
                "trigger": "cantheon_observation",
                "node_id": envelope.get("node_id"),
                "signal_id": (envelope.get("payload") or {}).get("signal_id"),
                "value": (envelope.get("payload") or {}).get("value"),
                "quality": envelope.get("quality"),
            },
            attributes={
                "source_timestamp_ns": envelope.get("source_timestamp_ns"),
                "ingest_timestamp_ns": envelope.get("ingest_timestamp_ns"),
                "sequence": envelope.get("sequence"),
            },
        )

        evidence = self.engine.evidence_history[-1]
        from multiflow import attach_evidence_ref

        evidence = attach_evidence_ref(
            evidence,
            event_id=str(envelope.get("sequence")),
            source_id=str(envelope.get("node_id") or ""),
            schema_id=str(
                envelope.get("boundary_schema_id") or "cantheon.metafield_boundary"
            ),
            schema_version=str(envelope.get("boundary_schema_version") or "0.3.0"),
        )
        self.engine.evidence_history[-1] = evidence

        payload = {
            "kind": "live_host_chain",
            "cantheon": {
                "node_id": envelope.get("node_id"),
                "sequence": envelope.get("sequence"),
                "quality": envelope.get("quality"),
            },
            "metafield": {
                "body_id": field_obs.body_id,
                "health": field_obs.health,
                "evidence_quality": (
                    field_obs.evidence.quality.value if field_obs.evidence else None
                ),
            },
            "multiflow": {
                "decision_id": record.id,
                "outcome_status": evidence.outcome_status.value,
                "admitted_candidate_id": evidence.admitted_candidate_id,
            },
        }
        obj = self._build_evidence_object(
            payload,
            node_id="live-host",
            sequence=len(self.mesh_hashes) + 1,
            evidence_refs=[
                {
                    "schema_id": "cantheon.metafield_boundary",
                    "event_id": str(envelope.get("sequence")),
                },
                {
                    "schema_id": "multiflow.decision_evidence",
                    "event_id": evidence.decision_id,
                },
            ],
        )
        assert self._verify_integrity(obj) == self.IntegrityStatus.VALID
        self.mesh.append(obj)
        self.mesh_hashes.append(obj.content_hash)

    def ingest_temperature(self, tenths_c: int, *, ts: int = 1000) -> None:
        from cantheon import CanFrame

        if tenths_c < 0:
            raw = (1 << 16) + tenths_c
        else:
            raw = tenths_c
        data = bytes([raw & 0xFF, (raw >> 8) & 0xFF])
        frame = CanFrame(can_id=0x100, data=data, timestamp_ns=ts)
        self.gate.ingest(
            frame,
            ingest_timestamp_ns=ts,
            source_timestamp_ns=ts - 100 if ts > 100 else ts,
        )


def main() -> int:
    print("=== Live host wiring ===\n")
    host = LiveHost()

    print("1. Ingest 25.0 \u00b0C (VALID)")
    host.ingest_temperature(250, ts=1000)
    print(f"   field observations: {len(host.field_observations)}")
    print(f"   decisions: {len(host.engine.decision_history)}")
    print(f"   evidence:  {len(host.engine.evidence_history)}")
    print(f"   mesh objs: {len(host.mesh)}")
    fo = host.field_observations[-1]
    print(
        f"   MetaField body={fo.body_id} health={fo.health} "
        f"value={fo.field_regions[0].observed}"
    )
    ev = host.engine.evidence_history[-1]
    print(
        f"   DecisionEvidence status={ev.outcome_status.value} "
        f"admitted={ev.admitted_candidate_id}"
    )
    print(f"   mesh hash={host.mesh_hashes[-1][:16]}\u2026")
    print()

    print("2. Ingest second sample 26.0 \u00b0C")
    host.ingest_temperature(260, ts=2000)
    print(f"   field observations: {len(host.field_observations)}")
    print(f"   mesh objs: {len(host.mesh)}")
    from mods.evidence_integrity import EvidenceStore, EvidenceObject

    peer = EvidenceStore()
    objs = [EvidenceObject.from_dict(d) for d in host.mesh.export()]
    result = peer.replicate(objs)
    print(
        f"   peer accepted={len(result.accepted)} duplicates={len(result.duplicates)}"
    )
    print()

    print("3. Summary")
    print(
        json.dumps(
            {
                "cangate_health": host.gate.health(),
                "decisions": len(host.engine.decision_history),
                "evidence_records": len(host.engine.evidence_history),
                "mesh_objects": len(host.mesh),
                "peer_objects": len(peer),
            },
            indent=2,
        )
    )
    print(
        "\n=== live path: CAN \u2192 CANgate \u2192 MetaField "
        "\u2192 MultiFlow evidence \u2192 Aurora Mesh ==="
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
