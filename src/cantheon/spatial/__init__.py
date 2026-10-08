"""Sensor-neutral spatial and ToF observation layer (CANtheon v0.3).

Architecture
------------
    RAW SENSOR
         ↓
    SENSOR OBSERVATION   (RANGE, TOF_ZONE, IMU, …)
         ↓
    DERIVED SPATIAL DATA (POINT3D, …)
         ↓
    GEOMETRY             (GEOMETRY_OBSERVATION)

CANtheon remains sensor-neutral.  Hardware-specific producers (e.g. a
VL53L5CX 8×8 ToF adapter) emit typed observations; they are never part of
the canonical data model.

All serializations are deterministic, integer/fixed-point preferred,
little-endian, with explicit validity and provenance.
"""

from .types import (
    ObservationKind,
    ValidityStatus,
    GeometryType,
    AccelUnit,
    GyroUnit,
    SPATIAL_SCHEMA_ID,
    SPATIAL_SCHEMA_VERSION,
)
from .observations import (
    RangeObservation,
    TofZoneObservation,
    Point3DObservation,
    ImuObservation,
    GeometryObservation,
    SpatialObservation,
)
from .calibration import (
    ReferenceFrame,
    ZoneCalibration,
    zone_to_point3d,
)
from .serialize import (
    encode_observation,
    decode_observation,
    encode_frame,
    decode_frame,
)

__all__ = [
    "ObservationKind",
    "ValidityStatus",
    "GeometryType",
    "AccelUnit",
    "GyroUnit",
    "SPATIAL_SCHEMA_ID",
    "SPATIAL_SCHEMA_VERSION",
    "RangeObservation",
    "TofZoneObservation",
    "Point3DObservation",
    "ImuObservation",
    "GeometryObservation",
    "SpatialObservation",
    "ReferenceFrame",
    "ZoneCalibration",
    "zone_to_point3d",
    "encode_observation",
    "decode_observation",
    "encode_frame",
    "decode_frame",
]
