"""Adapter boundary for future ecosystem integrations.

CANtheon core stays free of MetaField / TensorGate dependencies.
Adapters live here and consume Observation / Diagnostic / MetaFieldEvent.
"""

from .metafield import MetaFieldAdapter

__all__ = ["MetaFieldAdapter"]
