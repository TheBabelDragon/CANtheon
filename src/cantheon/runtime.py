"""Minimal deterministic host runtime.

receive frame → decode → normalize → validate → timestamp → provenance → emit
"""

from __future__ import annotations

from typing import Callable, Optional, Protocol

from .frame import CanFrame
from .node import Node
from .normalize import normalize_frame
from .observation import Observation
from .schema import SchemaRegistry
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
    ) -> None:
        self.registry = registry
        self.node = node
        self.sink: ObservationSink = sink if sink is not None else InMemorySink()
        self.source = source
        self._sequence = 0
        self._hooks: list[Callable[[Observation], None]] = []

    @property
    def sequence(self) -> int:
        return self._sequence

    def on_observation(self, callback: Callable[[Observation], None]) -> None:
        self._hooks.append(callback)

    def process(
        self,
        frame: CanFrame,
        *,
        timestamp_ns: Optional[int] = None,
    ) -> list[Observation]:
        """Full pipeline for one frame. Returns the produced observations."""
        self._sequence += 1
        seq = self._sequence
        ts = timestamp_ns if timestamp_ns is not None else frame.timestamp_ns

        if ts is not None:
            self.node.touch(ts)

        observations = normalize_frame(
            frame,
            self.registry,
            node_id=self.node.node_id,
            sequence=seq,
            timestamp_ns=ts,
            source=self.source,
        )

        # attach signal defs for validation when available
        msg_def = self.registry.get(frame.can_id)
        validated: list[Observation] = []
        for obs in observations:
            sig_def = None
            if msg_def is not None:
                for s in msg_def.signals:
                    if s.signal_id == obs.signal_id:
                        sig_def = s
                        break
            obs = validate_observation(obs, sig_def)
            validated.append(obs)
            self.sink.emit(obs)
            for h in self._hooks:
                h(obs)
        return validated
