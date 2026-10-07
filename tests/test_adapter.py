"""Adapter boundary — protocol only."""

from cantheon.adapters.metafield import MetaFieldAdapter
from cantheon import Observation, Diagnostic, MetaFieldEvent, Quality, Provenance
from cantheon.diagnostics import DiagnosticType


def test_protocol_is_runtime_checkable():
    class Stub:
        def on_observation(self, observation):
            pass
        def on_diagnostic(self, diagnostic):
            pass
        def on_event(self, event):
            pass
        def health(self):
            return {"ok": True}

    stub = Stub()
    assert isinstance(stub, MetaFieldAdapter)


def test_incomplete_not_adapter():
    class Incomplete:
        def on_observation(self, observation):
            pass

    assert not isinstance(Incomplete(), MetaFieldAdapter)
