"""CANtheon — CAN 2.0 → canonical physical state for the MetaField ecosystem.

CANtheon owns CAN ingestion, decoding, normalization, validation, timestamps,
sequence, identity, quality, and provenance.

CANgate is the explicit MetaField-facing boundary.
MetaField owns field semantics.
TensorGate owns numerical/tensor semantics.

This package does not implement MetaField or TensorGate.
"""

from .frame import CanFrame
from .signal import SignalDef, MessageDef, extract_signal
from .node import Node
from .observation import Quality, Observation, RawFrameRecord
from .schema import SchemaRegistry, load_schema
from .normalize import normalize_frame
from .validate import validate_observation
from .provenance import Provenance
from .runtime import Runtime, InMemorySink
from .cangate import CANgate, MetaFieldEvent

__version__ = "0.1.0"

__all__ = [
    "CanFrame",
    "SignalDef",
    "MessageDef",
    "extract_signal",
    "Node",
    "Quality",
    "Observation",
    "RawFrameRecord",
    "SchemaRegistry",
    "load_schema",
    "normalize_frame",
    "validate_observation",
    "Provenance",
    "Runtime",
    "InMemorySink",
    "CANgate",
    "MetaFieldEvent",
    "__version__",
]
