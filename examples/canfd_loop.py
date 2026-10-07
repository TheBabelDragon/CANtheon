#!/usr/bin/env python3
"""CAN-FD example: 64-byte frame → signal beyond byte 7 → record → replay."""

from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cantheon import (
    CanFrame, Node, SchemaRegistry, Runtime, InMemorySink,
    CANgate, FixedClock, Recorder, Replay, Quality, FrameFormat,
)


def main():
    reg = SchemaRegistry()
    reg.load_dict({
        "schema_id": "fd_demo.v1",
        "schema_version": "1.0",
        "node_id": "fd_node",
        "capabilities": ["pressure"],
        "messages": [{
            "message_id": 0x400,
            "name": "FarField",
            "frame_format": "CAN_FD",
            "signals": [{
                "signal_id": "pressure",
                "name": "Pressure",
                "start_bit": 160,  # byte 20
                "bit_length": 16,
                "is_signed": False,
                "scale": 0.1,
                "unit": "kPa",
                "min_value": 0.0,
                "max_value": 1000.0,
            }],
        }],
    })

    clock = FixedClock(0)
    recorder = Recorder()
    rt = Runtime(reg, Node("fd_node", "FD Node"), sink=InMemorySink(),
                 clock=clock, recorder=recorder)
    gate = CANgate(rt)

    data = bytearray(32)
    raw = 2500
    data[20] = raw & 0xFF
    data[21] = (raw >> 8) & 0xFF
    frame = CanFrame.can_fd(0x400, bytes(data), brs=True)

    print("=== CAN-FD path ===")
    print(f"frame_format={frame.frame_format.value}  dlc={frame.dlc}  "
          f"payload={frame.payload_length}  brs={frame.bit_rate_switch}")

    obs = gate.ingest(frame, ingest_timestamp_ns=100, source_timestamp_ns=90)[0]
    print(f"observation: {obs.signal_id}={obs.value} {obs.unit}  "
          f"quality={obs.quality.value}")
    assert abs(obs.value - 250.0) < 1e-9

    replayed = Replay.from_recorder(recorder).run(
        Runtime(reg, Node("fd_node", "FD Node"), sink=InMemorySink(),
                clock=FixedClock(0))
    )
    assert replayed[0].canonical_key() == obs.canonical_key()
    print("replay: canonical state matches")

    reg2 = SchemaRegistry()
    reg2.load_dict({
        "schema_id": "classic_only",
        "schema_version": "1.0",
        "node_id": "n",
        "messages": [{
            "message_id": 0x400,
            "name": "T",
            "frame_format": "CLASSICAL_CAN",
            "signals": [{"signal_id": "v", "name": "V",
                         "start_bit": 0, "bit_length": 8}],
        }],
    })
    rt2 = Runtime(reg2, Node("n", "N"), sink=InMemorySink(), clock=FixedClock(0))
    rt2.process(frame, ingest_timestamp_ns=1)
    from cantheon import DiagnosticType
    assert any(d.diagnostic_type == DiagnosticType.SCHEMA_TRANSPORT_MISMATCH
               for d in rt2.diagnostics)
    print("schema transport mismatch diagnosed (not silently coerced)")
    print("=== done ===")


if __name__ == "__main__":
    main()
