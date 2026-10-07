"""MetaField adapter interface — protocol only, no MetaField import.

Path:
  CANtheon → adapters.metafield → MetaField → TensorGate

No network calls. No external dependencies. No fake MetaField implementation.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from ..cangate import MetaFieldEvent
from ..diagnostics import Diagnostic
from ..observation import Observation


@runtime_checkable
class MetaFieldAdapter(Protocol):
    """Protocol-style boundary for a future MetaField consumer.

    Implementations live outside CANtheon core and map these
    objects into whatever MetaField expects.
    """

    def on_observation(self, observation: Observation) -> None:
        """Receive a canonical observation."""
        ...

    def on_diagnostic(self, diagnostic: Diagnostic) -> None:
        """Receive a diagnostic event."""
        ...

    def on_event(self, event: MetaFieldEvent) -> None:
        """Receive a MetaField-facing boundary event."""
        ...

    def health(self) -> dict[str, Any]:
        """Return adapter health as a machine-readable dict."""
        ...
