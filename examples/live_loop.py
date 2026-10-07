#!/usr/bin/env python3
"""Complete CANtheon example: CAN frame → temperature °C → provenance → CANgate.

Demonstrates both a valid observation and an out-of-range case so that
validation state survives rather than disappearing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow running from repo root without install
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cantheon import (
    CanFrame,
    Node,
    SchemaRegistry,
    Runtime,
    InMemorySink,
    CANgate,
    Quality,
)


def build_runtime() -> tuple[CANgate, InMemorySink]:
    schema_path = ROOT / "schemas" / "example_node.json"
    registry = SchemaRegistry()
    registry.load_json(schema_path)

    node = Node(
        node_id="temp_sensor_01",
        name="Temperature Sensor Module",
        capabilities=("temperature",),
        schema_version="1.0",
    )
    sink = InMemorySink()
    runtime = Runtime(registry, node, sink=sink)
    gate = CANgate(runtime)
    return gate, sink


def temperature_frame(tenths_c: int, timestamp_ns: int = 1_700_000_000_000_000_000) -> CanFrame:
    """Build a CAN 2.0 frame carrying a signed 16-bit temperature in 0.1 °C units."""
    # little-endian two's complement
    if tenths_c < 0:
        raw = (1 << 16) + tenths_c
    else:
        raw = tenths_c
    data = bytes([raw & 0xFF, (raw >> 8) & 0xFF])
    return CanFrame.from_id_and_bytes(0x100, data, timestamp_ns=timestamp_ns)


def main() -> None:
    gate, sink = build_runtime()

    print("=== CANtheon live_loop example ===\n")

    # --- valid temperature: 25.0 °C (250 tenths) ---
    frame_ok = temperature_frame(250)
    print("1. Valid frame (25.0 °C)")
    print(f"   raw CAN: id=0x{frame_ok.can_id:03X} data={frame_ok.data.hex()}")
    obs_list = gate.ingest(frame_ok)
    for obs in obs_list:
        print(f"   observation: {obs.signal_id} = {obs.value} {obs.unit}")
        print(f"   quality: {obs.quality.value}")
        print(f"   sequence: {obs.sequence}")
        print(f"   provenance: {json.dumps(obs.provenance.to_dict(), indent=6)}")
    events = gate.published
    print(f"   CANgate event: {json.dumps(events[-1].to_dict(), indent=6)}")
    print()

    # --- out-of-range: 200.0 °C (2000 tenths) exceeds max 125 ---
    frame_oor = temperature_frame(2000, timestamp_ns=1_700_000_000_100_000_000)
    print("2. Out-of-range frame (200.0 °C > max 125 °C)")
    print(f"   raw CAN: id=0x{frame_oor.can_id:03X} data={frame_oor.data.hex()}")
    obs_list = gate.ingest(frame_oor)
    for obs in obs_list:
        print(f"   observation: {obs.signal_id} = {obs.value} {obs.unit}")
        print(f"   quality: {obs.quality.value}  ← validation state preserved")
        assert obs.quality == Quality.OUT_OF_RANGE
    print()

    # --- unknown message → DECODE_ERROR ---
    frame_unk = CanFrame.from_id_and_bytes(0x7FF, b"\x00\x01", timestamp_ns=1_700_000_000_200_000_000)
    print("3. Unknown CAN ID (0x7FF) → DECODE_ERROR")
    obs_list = gate.ingest(frame_unk)
    for obs in obs_list:
        print(f"   quality: {obs.quality.value}")
        assert obs.quality == Quality.DECODE_ERROR
    print()

    # --- health ---
    print("4. CANgate health()")
    print(json.dumps(gate.health(), indent=2))
    print()

    # --- conceptual reverse path (no transmit, no autonomy) ---
    print("5. Reverse conceptual path: decision → CAN message (interface only)")
    cmd = gate.encode_command(0x100, {"temperature": 25.0})
    if cmd is not None:
        print(f"   encoded CAN: id=0x{cmd.can_id:03X} data={cmd.data.hex()}")
        # round-trip check
        round_trip = gate.ingest(CanFrame(can_id=cmd.can_id, data=cmd.data, timestamp_ns=1_700_000_000_300_000_000))
        print(f"   round-trip value: {round_trip[0].value} {round_trip[0].unit}")
    print()

    print("=== path proven: CAN → CANtheon → CANgate → MetaField-compatible event ===")


if __name__ == "__main__":
    main()
