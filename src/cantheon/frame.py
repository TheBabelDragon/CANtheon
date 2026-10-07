"""Raw CAN 2.0 frame representation.

Distinguishes the wire-level frame from decoded signals and normalized
observations. No silent conversion.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class CanFrame:
    """Standard CAN 2.0 frame (11-bit ID, 0–8 byte payload).

    CAN-FD is intentionally out of scope for the initial target.
    """

    can_id: int
    data: bytes
    is_extended: bool = False  # always False for standard 11-bit in v0.1
    is_remote: bool = False
    timestamp_ns: Optional[int] = None  # host receive time if available

    def __post_init__(self) -> None:
        if not (0 <= self.can_id <= 0x7FF) and not self.is_extended:
            raise ValueError(
                f"standard CAN ID must be 0..0x7FF, got 0x{self.can_id:X}"
            )
        if len(self.data) > 8:
            raise ValueError(
                f"CAN 2.0 payload max 8 bytes, got {len(self.data)}"
            )
        if not isinstance(self.data, (bytes, bytearray)):
            object.__setattr__(self, "data", bytes(self.data))

    @property
    def dlc(self) -> int:
        return len(self.data)

    def to_dict(self) -> dict:
        return {
            "can_id": self.can_id,
            "can_id_hex": f"0x{self.can_id:03X}",
            "data_hex": self.data.hex(),
            "dlc": self.dlc,
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
    ) -> "CanFrame":
        return cls(
            can_id=can_id,
            data=bytes(data),
            timestamp_ns=timestamp_ns,
        )
