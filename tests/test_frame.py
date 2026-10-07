"""Raw CAN frame construction and constraints."""

import pytest
from cantheon.frame import CanFrame


def test_standard_id_ok():
    f = CanFrame(can_id=0x100, data=b"\x01\x02")
    assert f.can_id == 0x100
    assert f.dlc == 2
    assert f.data == b"\x01\x02"


def test_standard_id_max():
    f = CanFrame(can_id=0x7FF, data=b"")
    assert f.can_id == 0x7FF


def test_standard_id_out_of_range():
    with pytest.raises(ValueError):
        CanFrame(can_id=0x800, data=b"")


def test_payload_max_8():
    CanFrame(can_id=1, data=b"\x00" * 8)
    with pytest.raises(ValueError):
        CanFrame(can_id=1, data=b"\x00" * 9)


def test_from_id_and_bytes():
    f = CanFrame.from_id_and_bytes(0x123, [0xAA, 0xBB], timestamp_ns=42)
    assert f.can_id == 0x123
    assert f.data == b"\xaa\xbb"
    assert f.timestamp_ns == 42


def test_to_dict():
    f = CanFrame(can_id=0x100, data=b"\x01\x02")
    d = f.to_dict()
    assert d["can_id"] == 0x100
    assert d["can_id_hex"] == "0x100"
    assert d["data_hex"] == "0102"
    assert d["dlc"] == 2
