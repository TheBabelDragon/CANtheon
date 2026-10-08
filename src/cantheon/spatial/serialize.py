"""Deterministic binary serialization for spatial observations.

Encoding rules (all little-endian):
  - Header: magic(4) + schema_version_major(u8) + kind(u8) + flags(u16)
  - Strings: u16 length + utf-8 bytes
  - Integers: explicit width and signedness per field
  - No floating-point on the wire

Magic: b"CTSP"  (CANtheon SPatial)
"""
from ._encode import SerializationError, encode_observation, MAGIC, SCHEMA_MAJOR, SCHEMA_MINOR
from ._decode import decode_observation, encode_frame, decode_frame

__all__ = [
    "SerializationError",
    "encode_observation",
    "decode_observation",
    "encode_frame",
    "decode_frame",
]
