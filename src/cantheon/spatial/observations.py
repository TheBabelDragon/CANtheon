"""Typed spatial observation dataclasses.

Every observation carries:
  source_id, sequence, timestamp_ns, validity, confidence, schema identity.
Derived observations retain source sequence(s) for provenance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence, Union

from .types import (
    ObservationKind,
    ValidityStatus,
    GeometryType,
    AccelUnit,
    GyroUnit,
    SPATIAL_SCHEMA_ID,
    SPATIAL_SCHEMA_VERSION,
    CONFIDENCE_UNKNOWN,
    RANGE_UNAVAILABLE,
)


@dataclass(frozen=True)
class RangeObservation:
    """Single range / distance measurement.

    Units: range_mm is millimetres (uint32 semantics on the wire).
    Invalid/unavailable ranges use ValidityStatus, never silent zero.
    """

    source_id: str
    sequence: int
    timestamp_ns: int
    range_mm: int
    status: ValidityStatus = ValidityStatus.VALID
    confidence: int = CONFIDENCE_UNKNOWN  # 0.01 % units, 0xFFFF = unknown
    zone_index: Optional[int] = None
    schema_id: str = SPATIAL_SCHEMA_ID
    schema_version: str = SPATIAL_SCHEMA_VERSION

    kind: ObservationKind = field(default=ObservationKind.RANGE, init=False, repr=False)

    def is_valid(self) -> bool:
        return self.status == ValidityStatus.VALID

    def to_dict(self) -> dict:
        d = {
            "kind": self.kind.name,
            "source_id": self.source_id,
            "sequence": self.sequence,
            "timestamp_ns": self.timestamp_ns,
            "range_mm": self.range_mm,
            "status": self.status.name,
            "confidence": self.confidence,
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
        }
        if self.zone_index is not None:
            d["zone_index"] = self.zone_index
        return d


@dataclass(frozen=True)
class TofZoneObservation:
    """One zone of a multizone ToF sensor (e.g. VL53L5CX 8×8).

    zone_id: 0..N-1 linear index.
    zone_x, zone_y: grid coordinates (0-based).
    range_mm: millimetres.
    signal_rate_kcps: kilo-counts-per-second × 100 (fixed-point, int32).
    ambient_kcps: ambient light rate × 100 (fixed-point, int32).
    Negative / sentinel values indicate unavailable.
    """

    source_id: str
    sequence: int
    timestamp_ns: int
    zone_id: int
    zone_x: int
    zone_y: int
    range_mm: int
    status: ValidityStatus = ValidityStatus.VALID
    confidence: int = CONFIDENCE_UNKNOWN
    signal_rate_kcps_x100: int = -1  # -1 = unavailable
    ambient_kcps_x100: int = -1      # -1 = unavailable
    schema_id: str = SPATIAL_SCHEMA_ID
    schema_version: str = SPATIAL_SCHEMA_VERSION

    kind: ObservationKind = field(default=ObservationKind.TOF_ZONE, init=False, repr=False)

    def is_valid(self) -> bool:
        return self.status == ValidityStatus.VALID

    def to_dict(self) -> dict:
        return {
            "kind": self.kind.name,
            "source_id": self.source_id,
            "sequence": self.sequence,
            "timestamp_ns": self.timestamp_ns,
            "zone_id": self.zone_id,
            "zone_x": self.zone_x,
            "zone_y": self.zone_y,
            "range_mm": self.range_mm,
            "status": self.status.name,
            "confidence": self.confidence,
            "signal_rate_kcps_x100": self.signal_rate_kcps_x100,
            "ambient_kcps_x100": self.ambient_kcps_x100,
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True)
class Point3DObservation:
    """Cartesian 3-D point derived from a range/zone measurement.

    Coordinates are millimetres (signed int32 on the wire).
    reference_frame_id identifies the coordinate frame.
    source_sequences lists the sequence number(s) of the producing
    observation(s) so provenance is never lost.
    """

    source_id: str
    sequence: int
    timestamp_ns: int
    x_mm: int
    y_mm: int
    z_mm: int
    confidence: int = CONFIDENCE_UNKNOWN
    status: ValidityStatus = ValidityStatus.VALID
    reference_frame_id: str = ""
    source_sequences: tuple[int, ...] = ()
    schema_id: str = SPATIAL_SCHEMA_ID
    schema_version: str = SPATIAL_SCHEMA_VERSION

    kind: ObservationKind = field(default=ObservationKind.POINT3D, init=False, repr=False)

    def is_valid(self) -> bool:
        return self.status == ValidityStatus.VALID

    def to_dict(self) -> dict:
        return {
            "kind": self.kind.name,
            "source_id": self.source_id,
            "sequence": self.sequence,
            "timestamp_ns": self.timestamp_ns,
            "x_mm": self.x_mm,
            "y_mm": self.y_mm,
            "z_mm": self.z_mm,
            "confidence": self.confidence,
            "status": self.status.name,
            "reference_frame_id": self.reference_frame_id,
            "source_sequences": list(self.source_sequences),
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True)
class ImuObservation:
    """Inertial measurement unit sample.

    Acceleration and gyro use explicit unit enums.
    Values are fixed-point: milli-units of the declared unit
    (e.g. milli-m/s² when unit is M_S2, or the raw milli-g value).
    """

    source_id: str
    sequence: int
    timestamp_ns: int
    ax: int
    ay: int
    az: int
    gx: int
    gy: int
    gz: int
    accel_unit: AccelUnit = AccelUnit.MILLI_G
    gyro_unit: GyroUnit = GyroUnit.MILLI_DEG_S
    status: ValidityStatus = ValidityStatus.VALID
    confidence: int = CONFIDENCE_UNKNOWN
    schema_id: str = SPATIAL_SCHEMA_ID
    schema_version: str = SPATIAL_SCHEMA_VERSION

    kind: ObservationKind = field(default=ObservationKind.IMU, init=False, repr=False)

    def is_valid(self) -> bool:
        return self.status == ValidityStatus.VALID

    def to_dict(self) -> dict:
        return {
            "kind": self.kind.name,
            "source_id": self.source_id,
            "sequence": self.sequence,
            "timestamp_ns": self.timestamp_ns,
            "ax": self.ax,
            "ay": self.ay,
            "az": self.az,
            "gx": self.gx,
            "gy": self.gy,
            "gz": self.gz,
            "accel_unit": self.accel_unit.name,
            "gyro_unit": self.gyro_unit.name,
            "status": self.status.name,
            "confidence": self.confidence,
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True)
class GeometryObservation:
    """Derived geometric primitive.

    parameters: fixed-point integer tuple whose meaning depends on
    geometry_type (documented per type).  source_sequences retains
    provenance back to the originating sensor observations.
    """

    source_id: str
    sequence: int
    timestamp_ns: int
    geometry_type: GeometryType
    reference_frame_id: str
    parameters: tuple[int, ...]
    confidence: int = CONFIDENCE_UNKNOWN
    status: ValidityStatus = ValidityStatus.VALID
    source_sequences: tuple[int, ...] = ()
    schema_id: str = SPATIAL_SCHEMA_ID
    schema_version: str = SPATIAL_SCHEMA_VERSION

    kind: ObservationKind = field(default=ObservationKind.GEOMETRY, init=False, repr=False)

    def is_valid(self) -> bool:
        return self.status == ValidityStatus.VALID

    def to_dict(self) -> dict:
        return {
            "kind": self.kind.name,
            "source_id": self.source_id,
            "sequence": self.sequence,
            "timestamp_ns": self.timestamp_ns,
            "geometry_type": self.geometry_type.name,
            "reference_frame_id": self.reference_frame_id,
            "parameters": list(self.parameters),
            "confidence": self.confidence,
            "status": self.status.name,
            "source_sequences": list(self.source_sequences),
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
        }


SpatialObservation = Union[
    RangeObservation,
    TofZoneObservation,
    Point3DObservation,
    ImuObservation,
    GeometryObservation,
]
