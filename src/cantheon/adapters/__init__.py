"""Adapter boundary for future ecosystem integrations.

CANtheon core stays free of MetaField / TensorGate dependencies.
Adapters live here and consume Observation / Diagnostic / MetaFieldEvent.

Spatial sensor reference adapters (e.g. VL53L5CX) produce typed spatial
observations without pulling vendor SDKs into the core.
"""

from .metafield import MetaFieldAdapter
from .vl53l5cx import (
    VL53L5CXAdapter,
    TofFrame,
    TofZoneReading,
    make_synthetic_8x8,
    default_forward_calibration,
    ZONE_COUNT,
    GRID_SIZE,
)

__all__ = [
    "MetaFieldAdapter",
    "VL53L5CXAdapter",
    "TofFrame",
    "TofZoneReading",
    "make_synthetic_8x8",
    "default_forward_calibration",
    "ZONE_COUNT",
    "GRID_SIZE",
]
