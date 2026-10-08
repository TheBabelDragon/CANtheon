"""Spatial observation encoders."""

from __future__ import annotations

import struct
from typing import Optional

from .observations import (
    RangeObservation,
    TofZoneObservation,
    Point3DObservation,
    ImuObservation,
    GeometryObservation,
    SpatialObservation,
)
from .types import (
    ObservationKind,
    ValidityStatus,
    GeometryType,
    AccelUnit,
    GyroUnit,
    SPATIAL_SCHEMA_ID,
    SPATIAL_SCHEMA_VERSION,
)

MAGIC = b"CTSP"
SCHEMA_MAJOR = 0
SCHEMA_MINOR = 3

_MAX_STR = 256
_MAX_SEQ_LIST = 64
_MAX_PARAMS = 32


class SerializationError(ValueError):
    """Malformed or truncated spatial payload."""


def _pack_str(s: str) -> bytes:
    raw = s.encode("utf-8")
    if len(raw) > _MAX_STR:
        raise SerializationError(f"string too long ({len(raw)} > {_MAX_STR})")
    return struct.pack("<H", len(raw)) + raw


def _unpack_str(data: bytes, offset: int) -> tuple[str, int]:
    if offset + 2 > len(data):
        raise SerializationError("truncated string length")
    (n,) = struct.unpack_from("<H", data, offset)
    offset += 2
    if n > _MAX_STR:
        raise SerializationError(f"string length {n} exceeds max")
    if offset + n > len(data):
        raise SerializationError("truncated string body")
    s = data[offset : offset + n].decode("utf-8")
    return s, offset + n


def _pack_header(kind: ObservationKind) -> bytes:
    return MAGIC + struct.pack("<BBBB", SCHEMA_MAJOR, SCHEMA_MINOR, int(kind), 0)


def _check_header(data: bytes) -> tuple[ObservationKind, int]:
    if len(data) < 8:
        raise SerializationError("truncated header")
    if data[:4] != MAGIC:
        raise SerializationError(f"bad magic {data[:4]!r}")
    major, minor, kind_u8, _res = struct.unpack_from("<BBBB", data, 4)
    if major != SCHEMA_MAJOR:
        raise SerializationError(
            f"unsupported schema major {major} (expected {SCHEMA_MAJOR})"
        )
    try:
        kind = ObservationKind(kind_u8)
    except ValueError as exc:
        raise SerializationError(f"unknown observation kind {kind_u8}") from exc
    return kind, 8


def _encode_range(obs: RangeObservation) -> bytes:
    body = _pack_str(obs.source_id)
    body += struct.pack(
        "<QqIiHH",
        obs.sequence & 0xFFFFFFFFFFFFFFFF,
        obs.timestamp_ns,
        obs.range_mm & 0xFFFFFFFF,
        int(obs.status),
        obs.confidence & 0xFFFF,
        (obs.zone_index if obs.zone_index is not None else 0xFFFF) & 0xFFFF,
    )
    body += _pack_str(obs.schema_id)
    body += _pack_str(obs.schema_version)
    return _pack_header(ObservationKind.RANGE) + body


def _encode_tof_zone(obs: TofZoneObservation) -> bytes:
    body = _pack_str(obs.source_id)
    body += struct.pack(
        "<QqHHHHIiHii",
        obs.sequence & 0xFFFFFFFFFFFFFFFF,
        obs.timestamp_ns,
        obs.zone_id & 0xFFFF,
        obs.zone_x & 0xFFFF,
        obs.zone_y & 0xFFFF,
        0,
        obs.range_mm & 0xFFFFFFFF,
        int(obs.status),
        obs.confidence & 0xFFFF,
        obs.signal_rate_kcps_x100,
        obs.ambient_kcps_x100,
    )
    body += _pack_str(obs.schema_id)
    body += _pack_str(obs.schema_version)
    return _pack_header(ObservationKind.TOF_ZONE) + body


def _encode_point3d(obs: Point3DObservation) -> bytes:
    body = _pack_str(obs.source_id)
    body += struct.pack(
        "<QqiiiiH",
        obs.sequence & 0xFFFFFFFFFFFFFFFF,
        obs.timestamp_ns,
        obs.x_mm,
        obs.y_mm,
        obs.z_mm,
        int(obs.status),
        obs.confidence & 0xFFFF,
    )
    body += _pack_str(obs.reference_frame_id)
    nseq = len(obs.source_sequences)
    if nseq > _MAX_SEQ_LIST:
        raise SerializationError("too many source_sequences")
    body += struct.pack("<H", nseq)
    for s in obs.source_sequences:
        body += struct.pack("<Q", s & 0xFFFFFFFFFFFFFFFF)
    body += _pack_str(obs.schema_id)
    body += _pack_str(obs.schema_version)
    return _pack_header(ObservationKind.POINT3D) + body


def _encode_imu(obs: ImuObservation) -> bytes:
    body = _pack_str(obs.source_id)
    body += struct.pack(
        "<QqiiiiiiBBiH",
        obs.sequence & 0xFFFFFFFFFFFFFFFF,
        obs.timestamp_ns,
        obs.ax,
        obs.ay,
        obs.az,
        obs.gx,
        obs.gy,
        obs.gz,
        int(obs.accel_unit),
        int(obs.gyro_unit),
        int(obs.status),
        obs.confidence & 0xFFFF,
    )
    body += _pack_str(obs.schema_id)
    body += _pack_str(obs.schema_version)
    return _pack_header(ObservationKind.IMU) + body


def _encode_geometry(obs: GeometryObservation) -> bytes:
    body = _pack_str(obs.source_id)
    body += struct.pack(
        "<QqBiH",
        obs.sequence & 0xFFFFFFFFFFFFFFFF,
        obs.timestamp_ns,
        int(obs.geometry_type),
        int(obs.status),
        obs.confidence & 0xFFFF,
    )
    body += _pack_str(obs.reference_frame_id)
    npar = len(obs.parameters)
    if npar > _MAX_PARAMS:
        raise SerializationError("too many parameters")
    body += struct.pack("<H", npar)
    for p in obs.parameters:
        body += struct.pack("<i", p)
    nseq = len(obs.source_sequences)
    if nseq > _MAX_SEQ_LIST:
        raise SerializationError("too many source_sequences")
    body += struct.pack("<H", nseq)
    for s in obs.source_sequences:
        body += struct.pack("<Q", s & 0xFFFFFFFFFFFFFFFF)
    body += _pack_str(obs.schema_id)
    body += _pack_str(obs.schema_version)
    return _pack_header(ObservationKind.GEOMETRY) + body


def encode_observation(obs: SpatialObservation) -> bytes:
    """Encode a single spatial observation to deterministic bytes."""
    if isinstance(obs, RangeObservation):
        return _encode_range(obs)
    if isinstance(obs, TofZoneObservation):
        return _encode_tof_zone(obs)
    if isinstance(obs, Point3DObservation):
        return _encode_point3d(obs)
    if isinstance(obs, ImuObservation):
        return _encode_imu(obs)
    if isinstance(obs, GeometryObservation):
        return _encode_geometry(obs)
    raise TypeError(f"unsupported observation type {type(obs)}")
