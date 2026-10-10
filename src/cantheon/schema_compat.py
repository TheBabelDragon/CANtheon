"""Schema identity and deterministic compatibility rules.

A schema change must never silently reinterpret an existing CAN payload.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Compatibility(str, Enum):
    COMPATIBLE = "COMPATIBLE"
    INCOMPATIBLE = "INCOMPATIBLE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class SchemaIdentity:
    schema_id: str
    schema_version: str

    def __str__(self) -> str:
        return f"{self.schema_id}@{self.schema_version}"

    def to_dict(self) -> dict:
        return {"schema_id": self.schema_id, "schema_version": self.schema_version}

    @classmethod
    def from_dict(cls, d: dict) -> "SchemaIdentity":
        return cls(schema_id=str(d.get("schema_id", "")), schema_version=str(d.get("schema_version", "")))

    @property
    def major(self) -> int:
        try:
            return int(self.schema_version.split(".")[0])
        except (ValueError, IndexError):
            return -1

    @property
    def minor(self) -> int:
        parts = self.schema_version.split(".")
        try:
            return int(parts[1]) if len(parts) > 1 else 0
        except ValueError:
            return 0


def check_compatibility(
    expected: SchemaIdentity,
    actual: SchemaIdentity,
) -> Compatibility:
    """Deterministic compatibility check.

    Rules:
    - missing / "unknown" identity → UNKNOWN
    - different schema_id → INCOMPATIBLE
    - same schema_id + same version → COMPATIBLE
    - same schema_id + same major, actual ≥ expected → COMPATIBLE
    - same schema_id + different major → INCOMPATIBLE
    """
    if (
        not expected.schema_id
        or not actual.schema_id
        or expected.schema_id == "unknown"
        or actual.schema_id == "unknown"
    ):
        return Compatibility.UNKNOWN

    if expected.schema_id != actual.schema_id:
        return Compatibility.INCOMPATIBLE

    if expected.schema_version == actual.schema_version:
        return Compatibility.COMPATIBLE

    exp_major = expected.major
    act_major = actual.major
    if exp_major < 0 or act_major < 0:
        return Compatibility.UNKNOWN

    if exp_major != act_major:
        return Compatibility.INCOMPATIBLE

    # same major: actual must be >= expected (minor.micro as float-ish)
    try:
        exp_parts = [int(x) for x in expected.schema_version.split(".")]
        act_parts = [int(x) for x in actual.schema_version.split(".")]
        # pad
        while len(exp_parts) < 3:
            exp_parts.append(0)
        while len(act_parts) < 3:
            act_parts.append(0)
        if tuple(act_parts) >= tuple(exp_parts):
            return Compatibility.COMPATIBLE
        return Compatibility.INCOMPATIBLE
    except ValueError:
        return Compatibility.UNKNOWN
