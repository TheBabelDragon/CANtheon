"""Message and signal definitions + bit-level extraction.

Supports unsigned/signed integers, configurable bit offset/length,
scale, offset, endianness, and units. No silent unit conversion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class Endianness(str, Enum):
    LITTLE = "little"
    BIG = "big"


@dataclass(frozen=True)
class SignalDef:
    """Definition of one signal inside a CAN message."""

    signal_id: str
    name: str
    start_bit: int  # bit offset from start of payload (LSB-first numbering)
    bit_length: int
    is_signed: bool = False
    scale: float = 1.0
    offset: float = 0.0
    unit: str = ""
    endianness: Endianness = Endianness.LITTLE
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    description: str = ""

    def __post_init__(self) -> None:
        if self.bit_length < 1 or self.bit_length > 64:
            raise ValueError(f"bit_length must be 1..64, got {self.bit_length}")
        if self.start_bit < 0:
            raise ValueError(f"start_bit must be >= 0, got {self.start_bit}")


@dataclass(frozen=True)
class MessageDef:
    """Definition of one CAN message (by 11-bit ID)."""

    message_id: int  # CAN ID
    name: str
    signals: tuple[SignalDef, ...] = field(default_factory=tuple)
    dlc: Optional[int] = None  # expected DLC if fixed
    description: str = ""
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        if not (0 <= self.message_id <= 0x7FF):
            raise ValueError(
                f"message_id must be 0..0x7FF, got 0x{self.message_id:X}"
            )


def _extract_raw_bits(
    data: bytes,
    start_bit: int,
    bit_length: int,
    endianness: Endianness,
) -> int:
    """Extract unsigned bit field from payload.

    Bit numbering is LSB-first within the byte stream for little-endian
    signals (common automotive convention). Big-endian uses Motorola-style
    start bit as the MSB of the field.
    """
    if endianness == Endianness.LITTLE:
        # Intel / little-endian: start_bit is the least-significant bit
        value = 0
        for i in range(bit_length):
            bit_pos = start_bit + i
            byte_idx = bit_pos // 8
            bit_in_byte = bit_pos % 8
            if byte_idx >= len(data):
                raise ValueError(
                    f"signal spans beyond payload (need byte {byte_idx}, "
                    f"have {len(data)})"
                )
            if (data[byte_idx] >> bit_in_byte) & 1:
                value |= 1 << i
        return value
    else:
        # Motorola / big-endian: start_bit is the most-significant bit
        # We walk downward in bit significance.
        value = 0
        for i in range(bit_length):
            # bit index relative to start (MSB first)
            bit_pos = start_bit - i
            if bit_pos < 0:
                raise ValueError("big-endian signal start_bit too small")
            byte_idx = bit_pos // 8
            bit_in_byte = bit_pos % 8
            if byte_idx >= len(data):
                raise ValueError(
                    f"signal spans beyond payload (need byte {byte_idx}, "
                    f"have {len(data)})"
                )
            if (data[byte_idx] >> bit_in_byte) & 1:
                value |= 1 << (bit_length - 1 - i)
        return value


def extract_signal(data: bytes, sig: SignalDef) -> tuple[int, float]:
    """Extract raw integer and engineering value from payload.

    Returns (raw_int, engineering_value).
    Raises ValueError on out-of-bounds access.
    """
    raw = _extract_raw_bits(
        data, sig.start_bit, sig.bit_length, sig.endianness
    )
    if sig.is_signed:
        # two's complement
        sign_bit = 1 << (sig.bit_length - 1)
        if raw & sign_bit:
            raw = raw - (1 << sig.bit_length)
    engineering = raw * sig.scale + sig.offset
    return raw, engineering


def signal_def_from_dict(d: dict[str, Any]) -> SignalDef:
    endian = d.get("endianness", "little")
    if isinstance(endian, str):
        endian = Endianness(endian.lower())
    return SignalDef(
        signal_id=d["signal_id"],
        name=d.get("name", d["signal_id"]),
        start_bit=int(d["start_bit"]),
        bit_length=int(d["bit_length"]),
        is_signed=bool(d.get("is_signed", False)),
        scale=float(d.get("scale", 1.0)),
        offset=float(d.get("offset", 0.0)),
        unit=str(d.get("unit", "")),
        endianness=endian,
        min_value=d.get("min_value"),
        max_value=d.get("max_value"),
        description=str(d.get("description", "")),
    )


def message_def_from_dict(d: dict[str, Any]) -> MessageDef:
    signals = tuple(
        signal_def_from_dict(s) for s in d.get("signals", [])
    )
    return MessageDef(
        message_id=int(d["message_id"]),
        name=d.get("name", f"msg_{d['message_id']}"),
        signals=signals,
        dlc=d.get("dlc"),
        description=str(d.get("description", "")),
        schema_version=str(d.get("schema_version", "1.0")),
    )
