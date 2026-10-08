"""Enums and schema identity for spatial observations."""

from __future__ import annotations

from enum import IntEnum, Enum


# Schema identity — reuses CANtheon versioning conventions.
SPATIAL_SCHEMA_ID = "cantheon.spatial"
SPATIAL_SCHEMA_VERSION = "0.3.0"


class ObservationKind(IntEnum):
    """Typed observation families.  Wire value is the uint8 tag."""

    RANGE = 1
    TOF_ZONE = 2
    POINT3D = 3
    IMU = 4
    GEOMETRY = 5


class ValidityStatus(IntEnum):
    """Explicit validity — never silently map unavailable → 0."""

    VALID = 0
    INVALID = 1
    UNAVAILABLE = 2
    OUT_OF_RANGE = 3
    SATURATED = 4
    NO_SIGNAL = 5
    WRAP_AROUND = 6


class GeometryType(IntEnum):
    """Geometry kinds for GEOMETRY_OBSERVATION."""

    POINT = 1
    PLANE = 2
    SPHERE = 3
    BOX = 4
    LINE = 5
    CUSTOM = 255


class AccelUnit(IntEnum):
    """Explicit acceleration units (never implicit)."""

    M_S2 = 0          # m/s²  (SI)
    MILLI_G = 1       # milli-g  (1/1000 g)
    MICRO_G = 2       # micro-g


class GyroUnit(IntEnum):
    """Explicit angular-rate units."""

    RAD_S = 0         # rad/s
    MILLI_DEG_S = 1   # milli-degrees per second
    MICRO_RAD_S = 2   # micro-rad/s


# Quality / confidence is uint16 in 0.01 % units:
#   0      = 0 %
#   10000  = 100.00 %
#   0xFFFF = unknown / not reported
CONFIDENCE_UNKNOWN = 0xFFFF
CONFIDENCE_MAX = 10000

# Sentinel range values (mm, uint32)
RANGE_UNAVAILABLE = 0xFFFFFFFF
RANGE_INVALID = 0xFFFFFFFE
RANGE_SATURATED = 0xFFFFFFFD
