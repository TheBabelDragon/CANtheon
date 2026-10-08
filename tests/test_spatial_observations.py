"""Comprehensive host-side tests for spatial / ToF observations (v0.3)."""

from __future__ import annotations

import pytest

from cantheon.spatial import (
    ObservationKind,
    ValidityStatus,
    GeometryType,
    AccelUnit,
    GyroUnit,
    SPATIAL_SCHEMA_ID,
    SPATIAL_SCHEMA_VERSION,
    RangeObservation,
    TofZoneObservation,
    Point3DObservation,
    ImuObservation,
    GeometryObservation,
    ReferenceFrame,
    ZoneCalibration,
    zone_to_point3d,
    encode_observation,
    decode_observation,
    encode_frame,
    decode_frame,
)
from cantheon.spatial.serialize import SerializationError
from cantheon.spatial.types import CONFIDENCE_MAX, CONFIDENCE_UNKNOWN, RANGE_UNAVAILABLE
from cantheon.adapters.vl53l5cx import (
    VL53L5CXAdapter,
    TofFrame,
    TofZoneReading,
    make_synthetic_8x8,
    default_forward_calibration,
    ZONE_COUNT,
    GRID_SIZE,
    zone_xy,
)


def _range(**kw):
    defaults = dict(
        source_id="src",
        sequence=1,
        timestamp_ns=1000,
        range_mm=500,
        status=ValidityStatus.VALID,
        confidence=CONFIDENCE_MAX,
    )
    defaults.update(kw)
    return RangeObservation(**defaults)


def _tof(**kw):
    defaults = dict(
        source_id="tof",
        sequence=1,
        timestamp_ns=2000,
        zone_id=0,
        zone_x=0,
        zone_y=0,
        range_mm=400,
        status=ValidityStatus.VALID,
        confidence=9000,
        signal_rate_kcps_x100=12000,
        ambient_kcps_x100=150,
    )
    defaults.update(kw)
    return TofZoneObservation(**defaults)


def _point(**kw):
    defaults = dict(
        source_id="tof",
        sequence=2,
        timestamp_ns=2000,
        x_mm=10,
        y_mm=20,
        z_mm=400,
        confidence=9000,
        status=ValidityStatus.VALID,
        reference_frame_id="tof_sensor",
        source_sequences=(1,),
    )
    defaults.update(kw)
    return Point3DObservation(**defaults)


def _imu(**kw):
    defaults = dict(
        source_id="imu0",
        sequence=5,
        timestamp_ns=3000,
        ax=0, ay=0, az=1000,
        gx=0, gy=0, gz=0,
        accel_unit=AccelUnit.MILLI_G,
        gyro_unit=GyroUnit.MILLI_DEG_S,
        status=ValidityStatus.VALID,
        confidence=CONFIDENCE_MAX,
    )
    defaults.update(kw)
    return ImuObservation(**defaults)


def _geom(**kw):
    defaults = dict(
        source_id="derived",
        sequence=10,
        timestamp_ns=4000,
        geometry_type=GeometryType.PLANE,
        reference_frame_id="body",
        parameters=(0, 0, 1000, 500),
        confidence=8000,
        status=ValidityStatus.VALID,
        source_sequences=(1, 2, 3),
    )
    defaults.update(kw)
    return GeometryObservation(**defaults)


def test_schema_identity():
    obs = _range()
    assert obs.schema_id == SPATIAL_SCHEMA_ID
    assert obs.schema_version == SPATIAL_SCHEMA_VERSION
    assert SPATIAL_SCHEMA_VERSION.startswith("0.3")


def test_observation_kinds():
    assert ObservationKind.RANGE == 1
    assert ObservationKind.TOF_ZONE == 2
    assert ObservationKind.POINT3D == 3
    assert ObservationKind.IMU == 4
    assert ObservationKind.GEOMETRY == 5


def test_valid_range():
    obs = _range(range_mm=1234)
    assert obs.is_valid()
    assert obs.range_mm == 1234


def test_invalid_not_silently_zero():
    obs = _range(range_mm=0, status=ValidityStatus.INVALID)
    assert not obs.is_valid()
    assert obs.status == ValidityStatus.INVALID
    assert obs.range_mm == 0


def test_unavailable_range():
    obs = _range(range_mm=-1, status=ValidityStatus.UNAVAILABLE)
    assert not obs.is_valid()
    assert obs.status == ValidityStatus.UNAVAILABLE


def test_quality_confidence_bounds():
    obs = _range(confidence=0)
    assert obs.confidence == 0
    obs2 = _range(confidence=CONFIDENCE_MAX)
    assert obs2.confidence == 10000
    obs3 = _range(confidence=CONFIDENCE_UNKNOWN)
    assert obs3.confidence == 0xFFFF


@pytest.mark.parametrize("factory", [_range, _tof, _point, _imu, _geom])
def test_roundtrip_all_kinds(factory):
    obs = factory()
    blob = encode_observation(obs)
    restored = decode_observation(blob)
    assert type(restored) is type(obs)
    assert restored.to_dict() == obs.to_dict()


def test_deterministic_encoding():
    obs = _range(sequence=42, timestamp_ns=99, range_mm=777)
    a = encode_observation(obs)
    b = encode_observation(obs)
    assert a == b


def test_sequence_timestamp_preserved():
    obs = _tof(sequence=12345, timestamp_ns=9_876_543_210)
    restored = decode_observation(encode_observation(obs))
    assert restored.sequence == 12345
    assert restored.timestamp_ns == 9_876_543_210


def test_point3d_provenance_preserved():
    obs = _point(source_sequences=(10, 20, 30))
    restored = decode_observation(encode_observation(obs))
    assert restored.source_sequences == (10, 20, 30)
    assert restored.reference_frame_id == "tof_sensor"


def test_geometry_parameters_and_provenance():
    obs = _geom(parameters=(1, -2, 3, 400), source_sequences=(7, 8))
    restored = decode_observation(encode_observation(obs))
    assert restored.parameters == (1, -2, 3, 400)
    assert restored.source_sequences == (7, 8)
    assert restored.geometry_type == GeometryType.PLANE


def test_reject_empty():
    with pytest.raises(SerializationError):
        decode_observation(b"")


def test_reject_bad_magic():
    with pytest.raises(SerializationError):
        decode_observation(b"XXXX" + b"\x00" * 20)


def test_reject_truncated():
    obs = _range()
    blob = encode_observation(obs)
    with pytest.raises(SerializationError):
        decode_observation(blob[:10])


def test_reject_unknown_kind():
    bad = b"CTSP" + bytes([0, 3, 99, 0]) + b"\x00" * 20
    with pytest.raises(SerializationError):
        decode_observation(bad)


def test_large_sequence():
    obs = _range(sequence=2**63 - 1)
    restored = decode_observation(encode_observation(obs))
    assert restored.sequence == 2**63 - 1


def test_negative_coordinates():
    obs = _point(x_mm=-1500, y_mm=-200, z_mm=50)
    restored = decode_observation(encode_observation(obs))
    assert restored.x_mm == -1500
    assert restored.y_mm == -200
    assert restored.z_mm == 50


def test_zero_range_valid():
    obs = _range(range_mm=0, status=ValidityStatus.VALID)
    assert obs.is_valid()
    restored = decode_observation(encode_observation(obs))
    assert restored.range_mm == 0
    assert restored.is_valid()


def test_frame_roundtrip():
    obs_list = [_range(), _tof(), _point(), _imu(), _geom()]
    blob = encode_frame(obs_list)
    restored = decode_frame(blob)
    assert len(restored) == 5
    for a, b in zip(obs_list, restored):
        assert a.to_dict() == b.to_dict()


def test_frame_empty():
    blob = encode_frame([])
    assert decode_frame(blob) == []


def test_frame_truncated():
    blob = encode_frame([_range()])
    with pytest.raises(SerializationError):
        decode_frame(blob[:6])
