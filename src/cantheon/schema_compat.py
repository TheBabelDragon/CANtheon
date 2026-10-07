"""Schema identity and deterministic compatibility rules.

A schema change must never silently reinterpret an existing CAN payload.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Compatibility(str, Enum):
    COMPATIBLE = "compatible"
    INCOMPATIBLE = "incompatible"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SchemaIdentity:
    """Explicit schema identity attached to every definition and observation."""

    schema_id: str
    schema_version: str

    def to_dict(self) -> dict:
        return {
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SchemaIdentity":
        return cls(
            schema_id=str(d.get("schema_id", "unknown")),
            schema_version=str(d.get("schema_version", "0.0")),
        )

    def __str__(self) -> str:
        return f"{self.schema_id}@{self.schema_version}"


def _parse_version(v: str) -> tuple[int, ...]:
    """Parse dotted version into integer tuple. Non-numeric parts → 0."""
    parts = []
    for p in v.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return tuple(parts) if parts else (0,)


def check_compatibility(
    expected: SchemaIdentity,
    actual: SchemaIdentity,
) -> Compatibility:
    """Deterministic compatibility check.

    Rules (documented in schemas/README.md):
    - same schema_id + same version → compatible
    - same schema_id + different version:
        major equal and actual minor/patch >= expected → compatible
        major different → incompatible
    - different schema_id → incompatible
    - missing/unknown identity → unknown
    """
    if not expected.schema_id or expected.schema_id == "unknown":
        return Compatibility.UNKNOWN
    if not actual.schema_id or actual.schema_id == "unknown":
        return Compatibility.UNKNOWN

    if expected.schema_id != actual.schema_id:
        return Compatibility.INCOMPATIBLE

    if expected.schema_version == actual.schema_version:
        return Compatibility.COMPATIBLE

    exp = _parse_version(expected.schema_version)
    act = _parse_version(actual.schema_version)

    n = max(len(exp), len(act))
    exp = exp + (0,) * (n - len(exp))
    act = act + (0,) * (n - len(act))

    if exp[0] != act[0]:
        return Compatibility.INCOMPATIBLE

    if act >= exp:
        return Compatibility.COMPATIBLE

    return Compatibility.INCOMPATIBLE
