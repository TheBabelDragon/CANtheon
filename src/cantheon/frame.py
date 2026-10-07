"""CAN / CAN-FD frame representation.

Transport layer is FD-aware. Canonical observations remain transport-independent.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class FrameFormat(str, Enum):
    CLASSICAL_CAN = "CLASSICAL_CAN"
    CAN_FD = "CAN_FD"


class IdentifierFormat(str, Enum):
    STANDARD_11 = "STANDARD_11"
    EXTENDED_29 = "EXTENDED_29"


# ISO 11898-1 CAN-FD DLC → payload length mapping
_FD_DLC_TO_LEN: dict[int, int] = {
    0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 7, 8: 8,
    9: 12, 10: 16, 11: 20, 12: 24, 13: 32, 14: 48, 15: 64,
}
_FD_LEN_TO_DLC: dict[int, int] = {v: k for k, v in _FD_DLC_TO_LEN.items()}
FD_VALID_LENGTHS: frozenset[int] = frozenset(_FD_LEN_TO_DLC.keys())


def fd_dlc_to_length(dlc: int) -> int:
    """Convert CAN-FD DLC code (0–15) to payload byte length."""
    if dlc not in _FD_DLC_TO_LEN:
        raise ValueError(f"invalid CAN-FD DLC {dlc}; valid 0..15")
    return _FD_DLC_TO_LEN[dlc]


def fd_length_to_dlc(length: int) -> int:
    """Convert payload byte length to CAN-FD DLC code."""
    if length not in _FD_LEN_TO_DLC:
        raise ValueError(
            f"unsupported CAN-FD payload length {length}; "
            f"valid lengths: {sorted(FD_VALID_LENGTHS)}"
        )
    return _FD_LEN_TO_DLC[length]


def classical_dlc_to_length(dlc: int) -> int:
    if not (0 <= dlc <= 8):
        raise ValueError(f"invalid Classical CAN DLC {dlc}; valid 0..8")
    return dlc


@dataclass(frozen=True)
class CanFrame:
    """CAN / CAN-FD frame at the transport boundary.

    Defaults preserve Classical CAN 11-bit behaviour for backward compatibility.
    """

    can_id: int
    data: bytes
    frame_format: FrameFormat = FrameFormat.CLASSICAL_CAN
    identifier_format: IdentifierFormat = IdentifierFormat.STANDARD_11
    bit_rate_switch: bool = False  # BRS (CAN-FD only)
    error_state_indicator: bool = False  # ESI (CAN-FD only)
    is_remote: bool = False
    dlc: Optional[int] = None  # wire DLC; derived from len(data) if None
    timestamp_ns: Optional[int] = None

    # Backward-compat aliases
    @property
    def is_extended(self) -> bool:
        return self.identifier_format == IdentifierFormat.EXTENDED_29

    def __post_init__(self) -> None:
        # Coerce data to bytes
        if not isinstance(self.data, (bytes, bytearray)):
            object.__setattr__(self, "data", bytes(self.data))
        else:
            object.__setattr__(self, "data", bytes(self.data))

        # Identifier validation
        if self.identifier_format == IdentifierFormat.STANDARD_11:
            if not (0 <= self.can_id <= 0x7FF):
                raise ValueError(
                    f"standard 11-bit CAN ID must be 0..0x7FF, got 0x{self.can_id:X}"
                )
        else:
            if not (0 <= self.can_id <= 0x1FFFFFFF):
                raise ValueError(
                    f"extended 29-bit CAN ID must be 0..0x1FFFFFFF, got 0x{self.can_id:X}"
                )

        payload_len = len(self.data)

        # Payload length validation by format
        if self.frame_format == FrameFormat.CLASSICAL_CAN:
            if payload_len > 8:
                raise ValueError(
                    f"Classical CAN payload max 8 bytes, got {payload_len}"
                )
            # Classical: BRS/ESI must be false
            if self.bit_rate_switch or self.error_state_indicator:
                raise ValueError(
                    "BRS/ESI are CAN-FD-only flags; invalid on Classical CAN"
                )
            # DLC for classical equals length (0-8)
            if self.dlc is None:
                object.__setattr__(self, "dlc", payload_len)
            else:
                if not (0 <= self.dlc <= 8):
                    raise ValueError(f"invalid Classical CAN DLC {self.dlc}")
                # DLC may be >= length (padding); but not less than length
                if self.dlc < payload_len:
                    raise ValueError(
                        f"Classical CAN DLC {self.dlc} < payload length {payload_len}"
                    )
        else:
            # CAN-FD
            if payload_len > 64:
                raise ValueError(
                    f"CAN-FD payload max 64 bytes, got {payload_len}"
                )
            if payload_len not in FD_VALID_LENGTHS:
                raise ValueError(
                    f"unsupported CAN-FD payload length {payload_len}; "
                    f"valid: {sorted(FD_VALID_LENGTHS)}"
                )
            if self.dlc is None:
                object.__setattr__(self, "dlc", fd_length_to_dlc(payload_len))
            else:
                if not (0 <= self.dlc <= 15):
                    raise ValueError(f"invalid CAN-FD DLC {self.dlc}; valid 0..15")
                expected_len = fd_dlc_to_length(self.dlc)
                if expected_len != payload_len:
                    raise ValueError(
                        f"CAN-FD DLC {self.dlc} expects {expected_len} bytes, "
                        f"got {payload_len}"
                    )

        # Remote frames typically have empty data
        if self.is_remote and payload_len > 0:
            raise ValueError("remote frame must have empty payload")

    @property
    def payload_length(self) -> int:
        return len(self.data)

    def to_dict(self) -> dict:
        id_width = 3 if self.identifier_format == IdentifierFormat.STANDARD_11 else 8
        return {
            "can_id": self.can_id,
            "can_id_hex": f"0x{self.can_id:0{id_width}X}",
            "data_hex": self.data.hex(),
            "dlc": self.dlc,
            "payload_length": self.payload_length,
            "frame_format": self.frame_format.value,
            "identifier_format": self.identifier_format.value,
            "bit_rate_switch": self.bit_rate_switch,
            "error_state_indicator": self.error_state_indicator,
            "is_extended": self.is_extended,
            "is_remote": self.is_remote,
            "timestamp_ns": self.timestamp_ns,
        }

    @classmethod
    def from_id_and_bytes(
        cls,
        can_id: int,
        data: bytes | bytearray | list[int],
        timestamp_ns: Optional[int] = None,
        *,
        frame_format: FrameFormat = FrameFormat.CLASSICAL_CAN,
        identifier_format: IdentifierFormat = IdentifierFormat.STANDARD_11,
        bit_rate_switch: bool = False,
        error_state_indicator: bool = False,
        is_extended: Optional[bool] = None,
    ) -> "CanFrame":
        """Convenience constructor. is_extended is a backward-compat alias."""
        if is_extended is not None:
            identifier_format = (
                IdentifierFormat.EXTENDED_29 if is_extended
                else IdentifierFormat.STANDARD_11
            )
        return cls(
            can_id=can_id,
            data=bytes(data),
            frame_format=frame_format,
            identifier_format=identifier_format,
            bit_rate_switch=bit_rate_switch,
            error_state_indicator=error_state_indicator,
            timestamp_ns=timestamp_ns,
        )

    @classmethod
    def classical(
        cls,
        can_id: int,
        data: bytes | bytearray | list[int] = b"",
        *,
        extended: bool = False,
        timestamp_ns: Optional[int] = None,
    ) -> "CanFrame":
        return cls.from_id_and_bytes(
            can_id, data, timestamp_ns=timestamp_ns,
            frame_format=FrameFormat.CLASSICAL_CAN,
            identifier_format=(
                IdentifierFormat.EXTENDED_29 if extended
                else IdentifierFormat.STANDARD_11
            ),
        )

    @classmethod
    def can_fd(
        cls,
        can_id: int,
        data: bytes | bytearray | list[int] = b"",
        *,
        extended: bool = False,
        brs: bool = False,
        esi: bool = False,
        timestamp_ns: Optional[int] = None,
    ) -> "CanFrame":
        return cls.from_id_and_bytes(
            can_id, data, timestamp_ns=timestamp_ns,
            frame_format=FrameFormat.CAN_FD,
            identifier_format=(
                IdentifierFormat.EXTENDED_29 if extended
                else IdentifierFormat.STANDARD_11
            ),
            bit_rate_switch=brs,
            error_state_indicator=esi,
        )
