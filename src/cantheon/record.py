"""Deterministic recording and replay of canonical CANtheon events.

Simple line-oriented JSONL format — inspectable, no database.
Preserves Classical CAN and CAN-FD transport metadata.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Optional, TextIO, Union

from .diagnostics import Diagnostic
from .frame import CanFrame
from .observation import Observation


RECORD_FORMAT_VERSION = "1.0"


@dataclass
class RecordedEvent:
    """One recorded event — enough to replay canonical state."""

    event_type: str  # "frame" | "observation" | "diagnostic"
    ingest_timestamp_ns: int
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "format_version": RECORD_FORMAT_VERSION,
            "event_type": self.event_type,
            "ingest_timestamp_ns": self.ingest_timestamp_ns,
            "data": dict(self.data),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "RecordedEvent":
        return cls(
            event_type=d["event_type"],
            ingest_timestamp_ns=int(d["ingest_timestamp_ns"]),
            data=dict(d.get("data", {})),
        )

    @classmethod
    def from_frame(
        cls,
        frame: CanFrame,
        *,
        node_id: str,
        ingest_timestamp_ns: int,
        source_timestamp_ns: Optional[int] = None,
        schema_id: str = "",
        schema_version: str = "",
    ) -> "RecordedEvent":
        return cls(
            event_type="frame",
            ingest_timestamp_ns=ingest_timestamp_ns,
            data={
                "can_id": frame.can_id,
                "data_hex": frame.data.hex(),
                "dlc": frame.dlc,
                "payload_length": len(frame.data),
                "frame_format": frame.frame_format.value,
                "identifier_format": frame.identifier_format.value,
                "bit_rate_switch": frame.bit_rate_switch,
                "error_state_indicator": frame.error_state_indicator,
                "is_remote": frame.is_remote,
                "node_id": node_id,
                "source_timestamp_ns": source_timestamp_ns,
                "schema_id": schema_id,
                "schema_version": schema_version,
            },
        )

    @classmethod
    def from_observation(cls, obs: Observation) -> "RecordedEvent":
        return cls(
            event_type="observation",
            ingest_timestamp_ns=obs.ingest_timestamp_ns,
            data=obs.to_dict(),
        )

    @classmethod
    def from_diagnostic(cls, diag: Diagnostic) -> "RecordedEvent":
        return cls(
            event_type="diagnostic",
            ingest_timestamp_ns=diag.timestamp_ns,
            data=diag.to_dict(),
        )


class Recorder:
    """Append-only recorder. Writes JSONL lines."""

    def __init__(self, path: Optional[Union[str, Path]] = None) -> None:
        self._path = Path(path) if path else None
        self._events: list[RecordedEvent] = []
        self._fp: Optional[TextIO] = None
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._fp = open(self._path, "w", encoding="utf-8")

    def record(self, event: RecordedEvent) -> None:
        self._events.append(event)
        if self._fp is not None:
            self._fp.write(json.dumps(event.to_dict(), separators=(",", ":")) + "\n")
            self._fp.flush()

    def record_frame(
        self,
        frame: CanFrame,
        *,
        node_id: str,
        ingest_timestamp_ns: int,
        source_timestamp_ns: Optional[int] = None,
        schema_id: str = "",
        schema_version: str = "",
    ) -> None:
        self.record(
            RecordedEvent.from_frame(
                frame,
                node_id=node_id,
                ingest_timestamp_ns=ingest_timestamp_ns,
                source_timestamp_ns=source_timestamp_ns,
                schema_id=schema_id,
                schema_version=schema_version,
            )
        )

    def record_observation(self, obs: Observation) -> None:
        self.record(RecordedEvent.from_observation(obs))

    def record_diagnostic(self, diag: Diagnostic) -> None:
        self.record(RecordedEvent.from_diagnostic(diag))

    @property
    def events(self) -> list[RecordedEvent]:
        return list(self._events)

    def close(self) -> None:
        if self._fp is not None:
            self._fp.close()
            self._fp = None

    def __enter__(self) -> "Recorder":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


class Replay:
    """Load recorded events and drive a Runtime deterministically."""

    def __init__(self, events: list[RecordedEvent]) -> None:
        self._events = list(events)

    @classmethod
    def from_path(cls, path: Union[str, Path]) -> "Replay":
        events: list[RecordedEvent] = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                events.append(RecordedEvent.from_dict(json.loads(line)))
        return cls(events)

    @classmethod
    def from_recorder(cls, recorder: Recorder) -> "Replay":
        return cls(recorder.events)

    def events(self) -> list[RecordedEvent]:
        return list(self._events)

    def frames(self) -> Iterator[tuple[CanFrame, dict[str, Any]]]:
        """Yield (CanFrame, metadata) for each recorded frame event."""
        from .frame import FrameFormat, IdentifierFormat
        for ev in self._events:
            if ev.event_type != "frame":
                continue
            d = ev.data
            ff = FrameFormat(d.get("frame_format", "CLASSICAL_CAN"))
            idf = IdentifierFormat(d.get("identifier_format", "STANDARD_11"))
            frame = CanFrame(
                can_id=int(d["can_id"]),
                data=bytes.fromhex(d["data_hex"]),
                frame_format=ff,
                identifier_format=idf,
                bit_rate_switch=bool(d.get("bit_rate_switch", False)),
                error_state_indicator=bool(d.get("error_state_indicator", False)),
                is_remote=bool(d.get("is_remote", False)),
                dlc=d.get("dlc"),
                timestamp_ns=d.get("source_timestamp_ns"),
            )
            meta = {
                "node_id": d.get("node_id", ""),
                "ingest_timestamp_ns": ev.ingest_timestamp_ns,
                "source_timestamp_ns": d.get("source_timestamp_ns"),
                "schema_id": d.get("schema_id", ""),
                "schema_version": d.get("schema_version", ""),
            }
            yield frame, meta

    def run(self, runtime: Any) -> list[Observation]:
        """Replay frames into runtime. Returns all produced observations."""
        results: list[Observation] = []
        for frame, meta in self.frames():
            obs_list = runtime.process(
                frame,
                timestamp_ns=meta.get("source_timestamp_ns"),
                ingest_timestamp_ns=meta["ingest_timestamp_ns"],
            )
            results.extend(obs_list)
        return results

    def observations(self) -> list[dict]:
        return [
            ev.data for ev in self._events if ev.event_type == "observation"
        ]

    def diagnostics(self) -> list[dict]:
        return [
            ev.data for ev in self._events if ev.event_type == "diagnostic"
        ]
