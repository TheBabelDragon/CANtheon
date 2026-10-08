"""VL53L5CX reference adapter — hardware-independent.

Produces TOF_ZONE_OBSERVATION[64] from an abstract 8×8 multizone ToF
reading.  No vendor SDK, no embedded driver, fully host-testable with
synthetic data.

The adapter is a *reference producer*.  It does not define the canonical
CANtheon data model; it only demonstrates how a multizone ToF source
maps into typed spatial observations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

from ..spatial.observations import TofZoneObservation, Point3DObservation
from ..spatial.calibration import ZoneCalibration, zone_to_point3d
from ..spatial.types import (
    ValidityStatus,
    CONFIDENCE_UNKNOWN,
    CONFIDENCE_MAX,
    RANGE_UNAVAILABLE,
)


# VL53L5CX is an 8×8 grid
GRID_SIZE = 8
ZONE_COUNT = GRID_SIZE * GRID_SIZE  # 64


@dataclass(frozen=True)
class TofZoneReading:
    """One zone of a synthetic / abstract ToF reading.

    All fields are host-side integers — no hardware types.
    range_mm: measured range in millimetres, or None if unavailable.
    status: validity of this zone.
    confidence: 0–10000 (0.01 % units) or CONFIDENCE_UNKNOWN.
    signal_rate_kcps_x100 / ambient_kcps_x100: optional fixed-point rates.
    """

    zone_id: int
    range_mm: Optional[int] = None
    status: ValidityStatus = ValidityStatus.VALID
    confidence: int = CONFIDENCE_UNKNOWN
    signal_rate_kcps_x100: int = -1
    ambient_kcps_x100: int = -1


@dataclass(frozen=True)
class TofFrame:
    """Complete 8×8 (or arbitrary) multizone ToF frame.

    zones must contain exactly ZONE_COUNT entries for a standard
    VL53L5CX-style producer, but the adapter tolerates other counts
    for future sensors.
    """

    source_id: str
    sequence: int
    timestamp_ns: int
    zones: tuple[TofZoneReading, ...]


def zone_xy(zone_id: int, grid: int = GRID_SIZE) -> tuple[int, int]:
    """Map linear zone_id → (zone_x, zone_y).  Row-major."""
    return zone_id % grid, zone_id // grid


class VL53L5CXAdapter:
    """Reference adapter: abstract ToF frame → TOF_ZONE_OBSERVATION list.

    Instantiable with no hardware.  Feed synthetic TofFrame objects.
    """

    def __init__(
        self,
        source_id: str = "vl53l5cx_ref",
        *,
        grid_size: int = GRID_SIZE,
        calibration: Optional[ZoneCalibration] = None,
    ) -> None:
        self.source_id = source_id
        self.grid_size = grid_size
        self.zone_count = grid_size * grid_size
        self.calibration = calibration

    def produce(self, frame: TofFrame) -> list[TofZoneObservation]:
        """Convert a TofFrame into a list of TOF_ZONE_OBSERVATION.

        Each zone retains independent validity, confidence, signal, and
        ambient.  Unavailable ranges are marked UNAVAILABLE — never zeroed.
        """
        observations: list[TofZoneObservation] = []
        for zr in frame.zones:
            zx, zy = zone_xy(zr.zone_id, self.grid_size)
            if zr.range_mm is None:
                range_val = -1  # wire encodes as uint32 0xFFFFFFFF
                status = ValidityStatus.UNAVAILABLE
            else:
                range_val = int(zr.range_mm)
                status = zr.status

            observations.append(
                TofZoneObservation(
                    source_id=frame.source_id or self.source_id,
                    sequence=frame.sequence,
                    timestamp_ns=frame.timestamp_ns,
                    zone_id=zr.zone_id,
                    zone_x=zx,
                    zone_y=zy,
                    range_mm=range_val,
                    status=status,
                    confidence=zr.confidence,
                    signal_rate_kcps_x100=zr.signal_rate_kcps_x100,
                    ambient_kcps_x100=zr.ambient_kcps_x100,
                )
            )
        return observations

    def produce_points(
        self,
        frame: TofFrame,
        *,
        calibration: Optional[ZoneCalibration] = None,
    ) -> list[Point3DObservation]:
        """Produce TOF_ZONE observations then convert valid ones to Point3D.

        Requires calibration (constructor or argument).  Invalid zones
        still yield Point3D observations with matching invalid status
        and provenance.
        """
        cal = calibration or self.calibration
        if cal is None:
            raise ValueError("calibration required for produce_points")
        zones = self.produce(frame)
        return [zone_to_point3d(z, cal) for z in zones]


def make_synthetic_8x8(
    *,
    source_id: str = "vl53l5cx_synth",
    sequence: int = 1,
    timestamp_ns: int = 1_000_000_000,
    valid_ranges: Optional[dict[int, int]] = None,
    invalid_zones: Optional[Sequence[int]] = None,
    confidence_map: Optional[dict[int, int]] = None,
    signal_map: Optional[dict[int, int]] = None,
    ambient_map: Optional[dict[int, int]] = None,
) -> TofFrame:
    """Build a deterministic synthetic 8×8 VL53L5CX-style frame.

    valid_ranges: zone_id → range_mm for valid measurements.
    invalid_zones: zone ids marked INVALID (range may still be present).
    Remaining zones default to UNAVAILABLE.
    """
    valid_ranges = dict(valid_ranges or {})
    invalid_set = set(invalid_zones or ())
    confidence_map = dict(confidence_map or {})
    signal_map = dict(signal_map or {})
    ambient_map = dict(ambient_map or {})

    zones: list[TofZoneReading] = []
    for zid in range(ZONE_COUNT):
        if zid in invalid_set:
            zones.append(
                TofZoneReading(
                    zone_id=zid,
                    range_mm=valid_ranges.get(zid, 0),
                    status=ValidityStatus.INVALID,
                    confidence=confidence_map.get(zid, 0),
                    signal_rate_kcps_x100=signal_map.get(zid, -1),
                    ambient_kcps_x100=ambient_map.get(zid, -1),
                )
            )
        elif zid in valid_ranges:
            zones.append(
                TofZoneReading(
                    zone_id=zid,
                    range_mm=valid_ranges[zid],
                    status=ValidityStatus.VALID,
                    confidence=confidence_map.get(zid, CONFIDENCE_MAX),
                    signal_rate_kcps_x100=signal_map.get(zid, 15000),
                    ambient_kcps_x100=ambient_map.get(zid, 200),
                )
            )
        else:
            zones.append(
                TofZoneReading(
                    zone_id=zid,
                    range_mm=None,
                    status=ValidityStatus.UNAVAILABLE,
                    confidence=CONFIDENCE_UNKNOWN,
                )
            )
    return TofFrame(
        source_id=source_id,
        sequence=sequence,
        timestamp_ns=timestamp_ns,
        zones=tuple(zones),
    )


def default_forward_calibration(
    frame_id: str = "tof_sensor",
    *,
    origin_x_mm: int = 0,
    origin_y_mm: int = 0,
    origin_z_mm: int = 0,
    grid: int = GRID_SIZE,
    fov_half_mdeg: int = 22500,  # ±22.5° typical for VL53L5CX wide
) -> ZoneCalibration:
    """Build a simple forward-looking zone calibration.

    Zones are mapped to rays in a rectangular FOV centred on +Z.
    Direction vectors are unit vectors in milli-units.
    This is a *reference* model, not a factory calibration.
    """
    from ..spatial.calibration import ReferenceFrame

    import math

    frame = ReferenceFrame(
        frame_id=frame_id,
        origin_x_mm=origin_x_mm,
        origin_y_mm=origin_y_mm,
        origin_z_mm=origin_z_mm,
    )
    directions: dict[int, tuple[int, int, int]] = {}
    half = fov_half_mdeg / 1000.0  # degrees
    for zid in range(grid * grid):
        zx, zy = zone_xy(zid, grid)
        # Normalise to [-1, 1]
        nx = (zx + 0.5) / grid * 2.0 - 1.0
        ny = (zy + 0.5) / grid * 2.0 - 1.0
        # Angle from centre
        ax = math.radians(nx * half)
        ay = math.radians(ny * half)
        # Ray direction (sensor looks along +Z)
        dx = math.sin(ax)
        dy = math.sin(ay)
        dz = math.cos(ax) * math.cos(ay)
        norm = math.sqrt(dx * dx + dy * dy + dz * dz)
        directions[zid] = (
            int(round(dx / norm * 1000)),
            int(round(dy / norm * 1000)),
            int(round(dz / norm * 1000)),
        )
    return ZoneCalibration(reference_frame=frame, zone_directions=directions)
