"""Spatial / ToF adapter + calibration tests (v0.3)."""
from __future__ import annotations

import pytest

from cantheon.spatial import (
    ValidityStatus, GeometryType, AccelUnit, GyroUnit,
    RangeObservation, TofZoneObservation, Point3DObservation,
    ImuObservation, GeometryObservation, ReferenceFrame, ZoneCalibration,
    zone_to_point3d, encode_observation, decode_observation, encode_frame, decode_frame,
)
from cantheon.spatial.serialize import SerializationError
from cantheon.spatial.types import CONFIDENCE_MAX, CONFIDENCE_UNKNOWN
from cantheon.adapters.vl53l5cx import (
    VL53L5CXAdapter, make_synthetic_8x8, default_forward_calibration,
    ZONE_COUNT, zone_xy,
)


def _tof(**kw):
    defaults = dict(
        source_id="tof", sequence=1, timestamp_ns=2000, zone_id=0, zone_x=0, zone_y=0,
        range_mm=400, status=ValidityStatus.VALID, confidence=9000,
        signal_rate_kcps_x100=12000, ambient_kcps_x100=150,
    )
    defaults.update(kw)
    return TofZoneObservation(**defaults)


def _point(**kw):
    defaults = dict(
        source_id="tof", sequence=2, timestamp_ns=2000, x_mm=10, y_mm=20, z_mm=400,
        confidence=9000, status=ValidityStatus.VALID, reference_frame_id="tof_sensor",
        source_sequences=(1,),
    )
    defaults.update(kw)
    return Point3DObservation(**defaults)


def _imu(**kw):
    defaults = dict(
        source_id="imu0", sequence=5, timestamp_ns=3000,
        ax=0, ay=0, az=1000, gx=0, gy=0, gz=0,
        accel_unit=AccelUnit.MILLI_G, gyro_unit=GyroUnit.MILLI_DEG_S,
        status=ValidityStatus.VALID, confidence=CONFIDENCE_MAX,
    )
    defaults.update(kw)
    return ImuObservation(**defaults)


def _range(**kw):
    defaults = dict(
        source_id="src", sequence=1, timestamp_ns=1000, range_mm=500,
        status=ValidityStatus.VALID, confidence=CONFIDENCE_MAX,
    )
    defaults.update(kw)
    return RangeObservation(**defaults)


def test_synthetic_64_zones():
    frame = make_synthetic_8x8(
        valid_ranges={0: 500, 7: 600, 63: 700},
        invalid_zones=[32],
        confidence_map={0: 9500, 7: 8000, 63: 7000},
    )
    assert len(frame.zones) == ZONE_COUNT == 64
    obs = VL53L5CXAdapter().produce(frame)
    assert len(obs) == 64


def test_zone_indexing():
    assert zone_xy(0) == (0, 0)
    assert zone_xy(7) == (7, 0)
    assert zone_xy(8) == (0, 1)
    assert zone_xy(63) == (7, 7)


def test_zone_coordinates_in_observations():
    frame = make_synthetic_8x8(valid_ranges={0: 100, 63: 200})
    obs = VL53L5CXAdapter().produce(frame)
    assert obs[0].zone_id == 0 and obs[0].zone_x == 0 and obs[0].zone_y == 0
    assert obs[63].zone_id == 63 and obs[63].zone_x == 7 and obs[63].zone_y == 7


def test_valid_and_invalid_zones():
    frame = make_synthetic_8x8(valid_ranges={1: 350, 2: 400}, invalid_zones=[3])
    obs = VL53L5CXAdapter().produce(frame)
    assert obs[1].is_valid() and obs[1].range_mm == 350
    assert obs[2].is_valid() and obs[2].range_mm == 400
    assert not obs[3].is_valid() and obs[3].status == ValidityStatus.INVALID
    assert not obs[10].is_valid()
    assert obs[10].status == ValidityStatus.UNAVAILABLE


def test_range_unit_mm():
    frame = make_synthetic_8x8(valid_ranges={0: 1234})
    obs = VL53L5CXAdapter().produce(frame)
    assert obs[0].range_mm == 1234


def test_signal_and_ambient():
    frame = make_synthetic_8x8(
        valid_ranges={5: 300}, signal_map={5: 18000}, ambient_map={5: 250},
    )
    obs = VL53L5CXAdapter().produce(frame)
    assert obs[5].signal_rate_kcps_x100 == 18000
    assert obs[5].ambient_kcps_x100 == 250


def test_tof_roundtrip_all_64():
    frame = make_synthetic_8x8(
        valid_ranges={i: 100 + i * 10 for i in range(0, 64, 4)},
        invalid_zones=[1, 2, 3],
    )
    obs_list = VL53L5CXAdapter().produce(frame)
    blob = encode_frame(obs_list)
    restored = decode_frame(blob)
    assert len(restored) == 64
    for a, b in zip(obs_list, restored):
        assert a.to_dict() == b.to_dict()


def test_zone_to_point3d_forward():
    cal = default_forward_calibration(frame_id="tof0")
    zone = _tof(zone_id=0, zone_x=0, zone_y=0, range_mm=1000, sequence=7)
    pt = zone_to_point3d(zone, cal)
    assert pt.is_valid()
    assert pt.reference_frame_id == "tof0"
    assert pt.source_sequences == (7,)
    assert pt.z_mm > 0
    assert pt.source_id == zone.source_id
    assert pt.timestamp_ns == zone.timestamp_ns


def test_invalid_zone_to_point3d():
    cal = default_forward_calibration()
    zone = _tof(status=ValidityStatus.NO_SIGNAL, range_mm=0)
    pt = zone_to_point3d(zone, cal)
    assert not pt.is_valid()
    assert pt.status == ValidityStatus.NO_SIGNAL
    assert pt.source_sequences == (zone.sequence,)
    assert pt.x_mm == 0 and pt.y_mm == 0 and pt.z_mm == 0


def test_missing_calibration_direction():
    frame = ReferenceFrame(frame_id="empty")
    cal = ZoneCalibration(reference_frame=frame, zone_directions={})
    zone = _tof(zone_id=99, range_mm=500)
    pt = zone_to_point3d(zone, cal)
    assert pt.status == ValidityStatus.UNAVAILABLE


def test_adapter_produce_points():
    cal = default_forward_calibration(frame_id="body")
    frame = make_synthetic_8x8(
        valid_ranges={0: 500, 36: 800, 63: 1200},
        invalid_zones=[1], sequence=42, timestamp_ns=555,
    )
    adapter = VL53L5CXAdapter(calibration=cal)
    points = adapter.produce_points(frame)
    assert len(points) == 64
    valid_pts = [p for p in points if p.is_valid()]
    assert len(valid_pts) == 3
    for p in valid_pts:
        assert p.source_sequences == (42,)
        assert p.timestamp_ns == 555
        assert p.reference_frame_id == "body"
    assert not points[1].is_valid()


def test_point3d_integer_arithmetic():
    cal = default_forward_calibration()
    zone = _tof(zone_id=36, zone_x=4, zone_y=4, range_mm=1000)
    pt = zone_to_point3d(zone, cal)
    assert isinstance(pt.x_mm, int)
    assert isinstance(pt.y_mm, int)
    assert isinstance(pt.z_mm, int)


def test_geometry_observation_from_points():
    pts = [
        _point(sequence=10, source_sequences=(1,), x_mm=0, y_mm=0, z_mm=500),
        _point(sequence=11, source_sequences=(2,), x_mm=100, y_mm=0, z_mm=500),
        _point(sequence=12, source_sequences=(3,), x_mm=0, y_mm=100, z_mm=500),
    ]
    geom = GeometryObservation(
        source_id="plane_fit", sequence=100, timestamp_ns=pts[0].timestamp_ns,
        geometry_type=GeometryType.PLANE, reference_frame_id="tof_sensor",
        parameters=(0, 0, 1000, 500), confidence=7500,
        source_sequences=tuple(p.sequence for p in pts),
    )
    assert geom.source_sequences == (10, 11, 12)
    restored = decode_observation(encode_observation(geom))
    assert restored.source_sequences == (10, 11, 12)


def test_to_dict_roundtrip_shape():
    for factory in (_range, _tof, _point, _imu):
        obs = factory()
        d = obs.to_dict()
        assert "kind" in d and "source_id" in d and "sequence" in d
        assert "timestamp_ns" in d and "schema_id" in d


def test_timestamp_ns_field_present():
    obs = _range(timestamp_ns=42)
    assert obs.timestamp_ns == 42
    assert obs.to_dict()["timestamp_ns"] == 42


def test_end_to_end_vl53l5cx_pipeline():
    cal = default_forward_calibration(frame_id="sensor_frame")
    frame = make_synthetic_8x8(
        source_id="vl53l5cx_0", sequence=100, timestamp_ns=1_500_000_000,
        valid_ranges={i: 400 + i for i in range(16)},
        invalid_zones=[60, 61],
        confidence_map={i: 9000 for i in range(16)},
    )
    adapter = VL53L5CXAdapter(source_id="vl53l5cx_0", calibration=cal)
    zones = adapter.produce(frame)
    assert len(zones) == 64
    assert sum(1 for z in zones if z.is_valid()) == 16
    points = adapter.produce_points(frame)
    valid_points = [p for p in points if p.is_valid()]
    assert len(valid_points) == 16
    for p in valid_points:
        assert p.source_sequences == (100,)
        assert p.reference_frame_id == "sensor_frame"
    if valid_points:
        cx = sum(p.x_mm for p in valid_points) // len(valid_points)
        cy = sum(p.y_mm for p in valid_points) // len(valid_points)
        cz = sum(p.z_mm for p in valid_points) // len(valid_points)
        geom = GeometryObservation(
            source_id="vl53l5cx_0", sequence=101, timestamp_ns=1_500_000_000,
            geometry_type=GeometryType.SPHERE, reference_frame_id="sensor_frame",
            parameters=(cx, cy, cz, 200), confidence=8500,
            source_sequences=tuple(p.sequence for p in valid_points),
        )
        g2 = decode_observation(encode_observation(geom))
        assert g2.geometry_type == GeometryType.SPHERE
        assert g2.parameters[3] == 200
    assert len(decode_frame(encode_frame(zones))) == 64


def test_imu_units_explicit():
    obs = _imu(accel_unit=AccelUnit.M_S2, gyro_unit=GyroUnit.RAD_S)
    restored = decode_observation(encode_observation(obs))
    assert restored.accel_unit == AccelUnit.M_S2
    assert restored.gyro_unit == GyroUnit.RAD_S


def test_overflow_protection_string():
    long_id = "x" * 300
    obs = _range(source_id=long_id)
    with pytest.raises(SerializationError):
        encode_observation(obs)
