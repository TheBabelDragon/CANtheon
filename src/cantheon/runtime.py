"""Minimal deterministic host runtime.

receive frame → decode → normalize → validate → timestamp → provenance → emit

v0.2: injectable clock, sequence tracking, diagnostics, liveness, recording.
"""

from __future__ import annotations

from typing import Callable, Optional, Protocol

from .clock import Clock, SystemClock
from .diagnostics import Diagnostic, DiagnosticType
from .frame import CanFrame, FrameFormat, IdentifierFormat
from .liveness import LivenessState, LivenessTracker
from .node import Node
from .normalize import normalize_frame
from .observation import Observation, Quality
from .record import Recorder
from .schema import SchemaRegistry
from .schema_compat import Compatibility, SchemaIdentity
from .sequence import SequenceAnomaly, SequenceTracker
from .validate import validate_observation


class ObservationSink(Protocol):
    def emit(self, obs: Observation) -> None: ...


class InMemorySink:
    """Simple list-backed sink for tests and examples."""

    def __init__(self) -> None:
        self.observations: list[Observation] = []

    def emit(self, obs: Observation) -> None:
        self.observations.append(obs)

    def clear(self) -> None:
        self.observations.clear()

    def by_signal(self, signal_id: str) -> list[Observation]:
        return [o for o in self.observations if o.signal_id == signal_id]


class Runtime:
    """Host-side pipeline. No global state. No hardware required."""

    def __init__(
        self,
        registry: SchemaRegistry,
        node: Node,
        sink: Optional[ObservationSink] = None,
        *,
        source: str = "cantheon",
        clock: Optional[Clock] = None,
        timeout_threshold_ns: int = 5_000_000_000,
        stale_threshold_ns: Optional[int] = None,
        recorder: Optional[Recorder] = None,
    ) -> None:
        self.registry = registry
        self.node = node
        self.sink: ObservationSink = sink if sink is not None else InMemorySink()
        self.source = source
        self.clock: Clock = clock if clock is not None else SystemClock()
        self._sequence = 0
        self._hooks: list[Callable[[Observation], None]] = []
        self._diag_hooks: list[Callable[[Diagnostic], None]] = []
        self.diagnostics: list[Diagnostic] = []
        self.recorder = recorder
        self._liveness = LivenessTracker(
            timeout_threshold_ns=timeout_threshold_ns,
            stale_threshold_ns=stale_threshold_ns,
        )
        self._seq_trackers: dict[tuple[str, int], SequenceTracker] = {}

    @property
    def sequence(self) -> int:
        return self._sequence

    def on_observation(self, callback: Callable[[Observation], None]) -> None:
        self._hooks.append(callback)

    def on_diagnostic(self, callback: Callable[[Diagnostic], None]) -> None:
        self._diag_hooks.append(callback)

    def _emit_diagnostic(self, diag: Diagnostic) -> None:
        self.diagnostics.append(diag)
        if self.recorder is not None:
            self.recorder.record_diagnostic(diag)
        for h in self._diag_hooks:
            h(diag)

    def _get_seq_tracker(self, node_id: str, message_id: int) -> SequenceTracker:
        key = (node_id, message_id)
        if key not in self._seq_trackers:
            msg_def = self.registry.get(message_id)
            width = msg_def.sequence_width if msg_def else None
            self._seq_trackers[key] = SequenceTracker(sequence_width=width)
        return self._seq_trackers[key]

    def process(
        self,
        frame: CanFrame,
        *,
        timestamp_ns: Optional[int] = None,
        ingest_timestamp_ns: Optional[int] = None,
        source_timestamp_ns: Optional[int] = None,
    ) -> list[Observation]:
        self._sequence += 1
        seq = self._sequence
        ingest_ts = (
            ingest_timestamp_ns
            if ingest_timestamp_ns is not None
            else self.clock.now_ns()
        )
        src_ts = source_timestamp_ns
        if src_ts is None:
            src_ts = timestamp_ns
        if src_ts is None and frame.timestamp_ns is not None:
            src_ts = frame.timestamp_ns

        self._liveness.touch(ingest_ts)
        self.node.touch(ingest_ts)

        if self.recorder is not None:
            self.recorder.record_frame(
                frame,
                node_id=self.node.node_id,
                ingest_timestamp_ns=ingest_ts,
                source_timestamp_ns=src_ts,
                schema_id=self.registry.schema_id,
                schema_version=self.registry.schema_version,
            )

        msg_def = self.registry.get(frame.can_id)

        if msg_def is not None:
            req = getattr(msg_def, "frame_format", "EITHER") or "EITHER"
            if req != "EITHER" and req != frame.frame_format.value:
                self._emit_diagnostic(Diagnostic(
                    diagnostic_type=DiagnosticType.SCHEMA_TRANSPORT_MISMATCH,
                    message=(
                        f"schema requires {req}, got {frame.frame_format.value} "
                        f"for CAN ID 0x{frame.can_id:X}"
                    ),
                    timestamp_ns=ingest_ts,
                    node_id=self.node.node_id,
                    can_message_id=frame.can_id,
                    sequence=seq,
                    detail={"required": req, "actual": frame.frame_format.value},
                ))

        if msg_def is None:
            self._emit_diagnostic(Diagnostic(
                diagnostic_type=DiagnosticType.UNKNOWN_MESSAGE,
                message=f"no message definition for CAN ID 0x{frame.can_id:03X}",
                timestamp_ns=ingest_ts,
                node_id=self.node.node_id,
                can_message_id=frame.can_id,
                sequence=seq,
                detail={"data_hex": frame.data.hex()},
            ))

        observations = normalize_frame(
            frame,
            self.registry,
            node_id=self.node.node_id,
            sequence=seq,
            ingest_timestamp_ns=ingest_ts,
            source_timestamp_ns=src_ts,
            source=self.source,
        )

        if msg_def is not None and (
            msg_def.sequence_width is not None or msg_def.sequence_signal() is not None
        ):
            tracker = self._get_seq_tracker(self.node.node_id, frame.can_id)
            if observations:
                eff_seq = observations[0].sequence
                anomaly = tracker.observe(eff_seq)
                if anomaly == SequenceAnomaly.GAP:
                    self._emit_diagnostic(Diagnostic(
                        diagnostic_type=DiagnosticType.SEQUENCE_GAP,
                        message=f"sequence gap: got {eff_seq}",
                        timestamp_ns=ingest_ts,
                        node_id=self.node.node_id,
                        can_message_id=frame.can_id,
                        sequence=eff_seq,
                        detail={"anomaly": anomaly.value},
                    ))
                elif anomaly == SequenceAnomaly.DUPLICATE:
                    self._emit_diagnostic(Diagnostic(
                        diagnostic_type=DiagnosticType.SEQUENCE_DUPLICATE,
                        message=f"duplicate sequence: {eff_seq}",
                        timestamp_ns=ingest_ts,
                        node_id=self.node.node_id,
                        can_message_id=frame.can_id,
                        sequence=eff_seq,
                        detail={"anomaly": anomaly.value},
                    ))
                elif anomaly == SequenceAnomaly.ROLLBACK:
                    self._emit_diagnostic(Diagnostic(
                        diagnostic_type=DiagnosticType.SEQUENCE_ROLLBACK,
                        message=f"sequence rollback/reset: {eff_seq}",
                        timestamp_ns=ingest_ts,
                        node_id=self.node.node_id,
                        can_message_id=frame.can_id,
                        sequence=eff_seq,
                        detail={"anomaly": anomaly.value},
                    ))

        validated: list[Observation] = []
        for obs in observations:
            sig_def = None
            if msg_def is not None:
                for s in msg_def.signals:
                    if s.signal_id == obs.signal_id:
                        sig_def = s
                        break
            obs = validate_observation(obs, sig_def)

            if obs.quality == Quality.DECODE_ERROR:
                self._emit_diagnostic(Diagnostic(
                    diagnostic_type=DiagnosticType.DECODE_ERROR,
                    message=f"decode error on {obs.signal_id}",
                    timestamp_ns=ingest_ts,
                    node_id=obs.node_id,
                    can_message_id=obs.message_id,
                    signal_id=obs.signal_id,
                    sequence=obs.sequence,
                    provenance=obs.provenance,
                    detail=dict(obs.extra),
                ))
            elif obs.quality == Quality.OUT_OF_RANGE:
                self._emit_diagnostic(Diagnostic(
                    diagnostic_type=DiagnosticType.INVALID_VALUE,
                    message=f"out-of-range value {obs.value} for {obs.signal_id}",
                    timestamp_ns=ingest_ts,
                    node_id=obs.node_id,
                    can_message_id=obs.message_id,
                    signal_id=obs.signal_id,
                    sequence=obs.sequence,
                    provenance=obs.provenance,
                    detail={"value": obs.value, "unit": obs.unit},
                ))

            validated.append(obs)
            self.sink.emit(obs)
            if self.recorder is not None:
                self.recorder.record_observation(obs)
            for h in self._hooks:
                h(obs)
        return validated

    def check_liveness(self, now_ns: Optional[int] = None) -> LivenessState:
        ts = now_ns if now_ns is not None else self.clock.now_ns()
        state = self._liveness.state(ts)
        if state == LivenessState.TIMEOUT:
            already = any(
                d.diagnostic_type == DiagnosticType.NODE_TIMEOUT
                and d.timestamp_ns == ts
                for d in self.diagnostics
            )
            if not already:
                self._emit_diagnostic(Diagnostic(
                    diagnostic_type=DiagnosticType.NODE_TIMEOUT,
                    message=f"node {self.node.node_id} timed out",
                    timestamp_ns=ts,
                    node_id=self.node.node_id,
                    detail={
                        "last_seen_ns": self._liveness.last_seen_ns,
                        "timeout_threshold_ns": self._liveness.timeout_threshold_ns,
                    },
                ))
            self.node.health = "TIMEOUT"
        elif state == LivenessState.STALE:
            self.node.health = "STALE"
            self._emit_diagnostic(Diagnostic(
                diagnostic_type=DiagnosticType.STALE_OBSERVATION,
                message=f"node {self.node.node_id} is stale",
                timestamp_ns=ts,
                node_id=self.node.node_id,
                detail={"last_seen_ns": self._liveness.last_seen_ns},
            ))
        elif state == LivenessState.ALIVE:
            self.node.health = "OK"
        return state

    @property
    def liveness_state(self) -> LivenessState:
        return self._liveness.state(self.clock.now_ns())
