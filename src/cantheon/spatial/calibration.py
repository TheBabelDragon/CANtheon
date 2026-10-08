"""Minimal calibration / reference-frame abstraction.

Sufficient to convert a zone+range observation into a Point3D when
calibration data exists.  Not a full camera model, SLAM, or registration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .observations import TofZoneObservation, Point3DObservation
from .types import ValidityStatus, CONFIDENCE_UNKNOWN


@dataclass(frozen=True)
class ReferenceFrame:
    """Named coordinate frame.

    origin_x/y/z_mm: origin of this frame expressed in a parent frame
    (millimetres, signed).  For a sensor-mounted frame the parent is
    typically the body / vehicle frame.
    """

    frame_id: str
    origin_x_mm: int = 0
    origin_y_mm: int = 0
    origin_z_mm: int = 0
    # Orientation: fixed-point milli-degrees for roll/pitch/yaw relative
    # to parent.  0 = identity.  Full rotation matrices are out of scope.
    roll_mdeg: int = 0
    pitch_mdeg: int = 0
    yaw_mdeg: int = 0

    def to_dict(self) -> dict:
        return {
            "frame_id": self.frame_id,
            "origin_x_mm": self.origin_x_mm,
            "origin_y_mm": self.origin_y_mm,
            "origin_z_mm": self.origin_z_mm,
            "roll_mdeg": self.roll_mdeg,
            "pitch_mdeg": self.pitch_mdeg,
            "yaw_mdeg": self.yaw_mdeg,
        }


@dataclass(frozen=True)
class ZoneCalibration:
    """Per-zone ray direction for a multizone ToF sensor.

    For each zone the sensor measures a range along a known ray.
    direction is a unit vector stored as milli-units (×1000):
        dir_x_milli, dir_y_milli, dir_z_milli
    so that  (dir · dir) ≈ 1_000_000.

    point = origin + (range_mm) * direction
    computed in integer arithmetic with rounding.
    """

    reference_frame: ReferenceFrame
    # zone_id → (dir_x_milli, dir_y_milli, dir_z_milli)
    zone_directions: dict[int, tuple[int, int, int]]

    def direction_for(self, zone_id: int) -> Optional[tuple[int, int, int]]:
        return self.zone_directions.get(zone_id)


def zone_to_point3d(
    zone: TofZoneObservation,
    calibration: ZoneCalibration,
    *,
    sequence: Optional[int] = None,
) -> Point3DObservation:
    """Convert a TOF_ZONE observation into a POINT3D using calibration.

    Invalid / unavailable zones produce a POINT3D with matching status
    and zero coordinates (explicitly invalid, not a silent zero range).
    Provenance: source_sequences carries the zone's sequence.
    """
    seq = sequence if sequence is not None else zone.sequence
    frame = calibration.reference_frame

    if not zone.is_valid():
        return Point3DObservation(
            source_id=zone.source_id,
            sequence=seq,
            timestamp_ns=zone.timestamp_ns,
            x_mm=0,
            y_mm=0,
            z_mm=0,
            confidence=zone.confidence,
            status=zone.status,
            reference_frame_id=frame.frame_id,
            source_sequences=(zone.sequence,),
            schema_id=zone.schema_id,
            schema_version=zone.schema_version,
        )

    direction = calibration.direction_for(zone.zone_id)
    if direction is None:
        return Point3DObservation(
            source_id=zone.source_id,
            sequence=seq,
            timestamp_ns=zone.timestamp_ns,
            x_mm=0,
            y_mm=0,
            z_mm=0,
            confidence=CONFIDENCE_UNKNOWN,
            status=ValidityStatus.UNAVAILABLE,
            reference_frame_id=frame.frame_id,
            source_sequences=(zone.sequence,),
            schema_id=zone.schema_id,
            schema_version=zone.schema_version,
        )

    dx, dy, dz = direction
    r = zone.range_mm
    # point = origin + range * direction / 1000  (integer rounding)
    # direction components are milli-units of a unit vector.
    x = frame.origin_x_mm + (r * dx + (500 if dx >= 0 else -500)) // 1000
    y = frame.origin_y_mm + (r * dy + (500 if dy >= 0 else -500)) // 1000
    z = frame.origin_z_mm + (r * dz + (500 if dz >= 0 else -500)) // 1000

    return Point3DObservation(
        source_id=zone.source_id,
        sequence=seq,
        timestamp_ns=zone.timestamp_ns,
        x_mm=x,
        y_mm=y,
        z_mm=z,
        confidence=zone.confidence,
        status=ValidityStatus.VALID,
        reference_frame_id=frame.frame_id,
        source_sequences=(zone.sequence,),
        schema_id=zone.schema_id,
        schema_version=zone.schema_version,
    )
