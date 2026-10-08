"""Spatial observation decoders and multi-observation frames."""
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
)
from ._encode import (
    SerializationError,
    MAGIC,
    SCHEMA_MAJOR,
    SCHEMA_MINOR,
    _MAX_STR,
    _MAX_SEQ_LIST,
    _MAX_PARAMS,
    _pack_str,
    _unpack_str,
    _pack_header,
    _check_header,
    encode_observation,
)


# ── per-kind decoders ────────────────────────────────────────────────

def _decode_range(data: bytes, offset: int) -> RangeObservation:
    source_id, offset = _unpack_str(data, offset)
    need = 8 + 8 + 4 + 4 + 2 + 2  # seq Q, ts q, range I, status i, conf H, zone H
    if offset + need > len(data):
        raise SerializationError("truncated RANGE body")
    seq, ts, range_mm, status_i, conf, zone_u = struct.unpack_from(
        "<QqIiHH", data, offset
    )
    offset += need
    schema_id, offset = _unpack_str(data, offset)
    schema_ver, offset = _unpack_str(data, offset)
    zone_index = None if zone_u == 0xFFFF else zone_u
    try:
        status = ValidityStatus(status_i)
    except ValueError as exc:
        raise SerializationError(f"bad status {status_i}") from exc
    return RangeObservation(
        source_id=source_id,
        sequence=seq,
        timestamp_ns=ts,
        range_mm=range_mm,
        status=status,
        confidence=conf,
        zone_index=zone_index,
        schema_id=schema_id,
        schema_version=schema_ver,
    )


def _decode_tof_zone(data: bytes, offset: int) -> TofZoneObservation:
    source_id, offset = _unpack_str(data, offset)
    need = 42
    if offset + need > len(data):
        raise SerializationError("truncated TOF_ZONE body")
    (
        seq, ts, zone_id, zone_x, zone_y, _res,
        range_mm, status_i, conf, sig, amb,
    ) = struct.unpack_from("<QqHHHHIiHii", data, offset)
    offset += need
    schema_id, offset = _unpack_str(data, offset)
    schema_ver, offset = _unpack_str(data, offset)
    try:
        status = ValidityStatus(status_i)
    except ValueError as exc:
        raise SerializationError(f"bad status {status_i}") from exc
    if range_mm == 0xFFFFFFFF:
        range_mm = -1
    return TofZoneObservation(
        source_id=source_id,
        sequence=seq,
        timestamp_ns=ts,
        zone_id=zone_id,
        zone_x=zone_x,
        zone_y=zone_y,
        range_mm=range_mm,
        status=status,
        confidence=conf,
        signal_rate_kcps_x100=sig,
        ambient_kcps_x100=amb,
        schema_id=schema_id,
        schema_version=schema_ver,
    )


def _decode_point3d(data: bytes, offset: int) -> Point3DObservation:
    source_id, offset = _unpack_str(data, offset)
    need = 8 + 8 + 4 + 4 + 4 + 4 + 2
    if offset + need > len(data):
        raise SerializationError("truncated POINT3D body")
    seq, ts, x, y, z, status_i, conf = struct.unpack_from("<QqiiiiH", data, offset)
    offset += need
    ref_frame, offset = _unpack_str(data, offset)
    if offset + 2 > len(data):
        raise SerializationError("truncated source_sequences count")
    (nseq,) = struct.unpack_from("<H", data, offset)
    offset += 2
    if nseq > _MAX_SEQ_LIST:
        raise SerializationError("source_sequences count exceeds max")
    if offset + nseq * 8 > len(data):
        raise SerializationError("truncated source_sequences")
    src_seqs = []
    for _ in range(nseq):
        (s,) = struct.unpack_from("<Q", data, offset)
        src_seqs.append(s)
        offset += 8
    schema_id, offset = _unpack_str(data, offset)
    schema_ver, offset = _unpack_str(data, offset)
    try:
        status = ValidityStatus(status_i)
    except ValueError as exc:
        raise SerializationError(f"bad status {status_i}") from exc
    return Point3DObservation(
        source_id=source_id,
        sequence=seq,
        timestamp_ns=ts,
        x_mm=x,
        y_mm=y,
        z_mm=z,
        confidence=conf,
        status=status,
        reference_frame_id=ref_frame,
        source_sequences=tuple(src_seqs),
        schema_id=schema_id,
        schema_version=schema_ver,
    )


def _decode_imu(data: bytes, offset: int) -> ImuObservation:
    source_id, offset = _unpack_str(data, offset)
    need = 48
    if offset + need > len(data):
        raise SerializationError("truncated IMU body")
    (
        seq, ts, ax, ay, az, gx, gy, gz,
        accel_u, gyro_u, status_i, conf,
    ) = struct.unpack_from("<QqiiiiiiBBiH", data, offset)
    offset += need
    schema_id, offset = _unpack_str(data, offset)
    schema_ver, offset = _unpack_str(data, offset)
    try:
        status = ValidityStatus(status_i)
        accel_unit = AccelUnit(accel_u)
        gyro_unit = GyroUnit(gyro_u)
    except ValueError as exc:
        raise SerializationError(f"bad enum value: {exc}") from exc
    return ImuObservation(
        source_id=source_id,
        sequence=seq,
        timestamp_ns=ts,
        ax=ax, ay=ay, az=az,
        gx=gx, gy=gy, gz=gz,
        accel_unit=accel_unit,
        gyro_unit=gyro_unit,
        status=status,
        confidence=conf,
        schema_id=schema_id,
        schema_version=schema_ver,
    )


def _decode_geometry(data: bytes, offset: int) -> GeometryObservation:
    source_id, offset = _unpack_str(data, offset)
    need = 8 + 8 + 1 + 4 + 2
    if offset + need > len(data):
        raise SerializationError("truncated GEOMETRY body")
    seq, ts, gtype_u, status_i, conf = struct.unpack_from("<QqBiH", data, offset)
    offset += need
    ref_frame, offset = _unpack_str(data, offset)
    if offset + 2 > len(data):
        raise SerializationError("truncated parameters count")
    (npar,) = struct.unpack_from("<H", data, offset)
    offset += 2
    if npar > _MAX_PARAMS:
        raise SerializationError("parameters count exceeds max")
    if offset + npar * 4 > len(data):
        raise SerializationError("truncated parameters")
    params = []
    for _ in range(npar):
        (p,) = struct.unpack_from("<i", data, offset)
        params.append(p)
        offset += 4
    if offset + 2 > len(data):
        raise SerializationError("truncated source_sequences count")
    (nseq,) = struct.unpack_from("<H", data, offset)
    offset += 2
    if nseq > _MAX_SEQ_LIST:
        raise SerializationError("source_sequences count exceeds max")
    if offset + nseq * 8 > len(data):
        raise SerializationError("truncated source_sequences")
    src_seqs = []
    for _ in range(nseq):
        (s,) = struct.unpack_from("<Q", data, offset)
        src_seqs.append(s)
        offset += 8
    schema_id, offset = _unpack_str(data, offset)
    schema_ver, offset = _unpack_str(data, offset)
    try:
        status = ValidityStatus(status_i)
        gtype = GeometryType(gtype_u)
    except ValueError as exc:
        raise SerializationError(f"bad enum: {exc}") from exc
    return GeometryObservation(
        source_id=source_id,
        sequence=seq,
        timestamp_ns=ts,
        geometry_type=gtype,
        reference_frame_id=ref_frame,
        parameters=tuple(params),
        confidence=conf,
        status=status,
        source_sequences=tuple(src_seqs),
        schema_id=schema_id,
        schema_version=schema_ver,
    )


_DECODERS = {
    ObservationKind.RANGE: _decode_range,
    ObservationKind.TOF_ZONE: _decode_tof_zone,
    ObservationKind.POINT3D: _decode_point3d,
    ObservationKind.IMU: _decode_imu,
    ObservationKind.GEOMETRY: _decode_geometry,
}


def decode_observation(data: bytes) -> SpatialObservation:
    """Decode a single spatial observation from bytes.

    Raises SerializationError on malformed / truncated / unknown payloads.
    """
    kind, offset = _check_header(data)
    decoder = _DECODERS[kind]
    return decoder(data, offset)


FRAME_MAGIC = b"CTSF"


def encode_frame(observations: list[SpatialObservation]) -> bytes:
    """Encode a list of observations as a single deterministic frame."""
    parts = [FRAME_MAGIC, struct.pack("<I", len(observations))]
    for obs in observations:
        blob = encode_observation(obs)
        parts.append(struct.pack("<I", len(blob)))
        parts.append(blob)
    return b"".join(parts)


def decode_frame(data: bytes) -> list[SpatialObservation]:
    """Decode a spatial frame.  Rejects truncated / malformed payloads."""
    if len(data) < 8:
        raise SerializationError("truncated frame header")
    if data[:4] != FRAME_MAGIC:
        raise SerializationError(f"bad frame magic {data[:4]!r}")
    (count,) = struct.unpack_from("<I", data, 4)
    if count > 10_000:
        raise SerializationError(f"unreasonable observation count {count}")
    offset = 8
    result: list[SpatialObservation] = []
    for _ in range(count):
        if offset + 4 > len(data):
            raise SerializationError("truncated observation length")
        (length,) = struct.unpack_from("<I", data, offset)
        offset += 4
        if length > 1_000_000:
            raise SerializationError(f"unreasonable observation length {length}")
        if offset + length > len(data):
            raise SerializationError("truncated observation body")
        result.append(decode_observation(data[offset : offset + length]))
        offset += length
    return result
