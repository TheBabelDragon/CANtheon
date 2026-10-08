"""CANtheon — Classical CAN and CAN-FD → canonical physical state for the MetaField ecosystem.

CANtheon owns CAN ingestion, decoding, normalization, validation, timestamps,
sequence, identity, quality, provenance, diagnostics, liveness, and replay.

CANgate is the explicit MetaField-facing boundary.
MetaField owns field semantics.
TensorGate owns numerical/tensor semantics.

This package does not implement MetaField or TensorGate.
"""

from .frame import CanFrame, FrameFormat, IdentifierFormat, fd_dlc_to_length, fd_length_to_dlc, FD_VALID_LENGTHS
from .signal import SignalDef, MessageDef, extract_signal
from .node import Node
from .observation import Quality, Observation, RawFrameRecord
from .schema import SchemaRegistry, load_schema
from .normalize import normalize_frame
from .validate import validate_observation
from .provenance import Provenance
from .runtime import Runtime, InMemorySink
from .cangate import CANgate, MetaFieldEvent, GateState
from .clock import Clock, SystemClock, FixedClock
from .diagnostics import Diagnostic, DiagnosticType
from .sequence import SequenceTracker, SequenceAnomaly
from .liveness import LivenessTracker, LivenessState
from .capability import NodeCapability, MessageCapability, SignalCapability
from .schema_compat import SchemaIdentity, Compatibility, check_compatibility
from .record import Recorder, Replay, RecordedEvent

# Spatial / ToF observations (v0.3) — sensor-neutral
from .spatial import (
    ObservationKind as SpatialObservationKind,
    ValidityStatus as SpatialValidityStatus,
    GeometryType,
    AccelUnit,
    GyroUnit,
    SPATIAL_SCHEMA_ID,
    SPATIAL_SCHEMA_VERSION,
    RangeObservation,
    TofZoneObservation,
    Point3DObservation,
    ImuObservation,
    GeometryObservation,
    ReferenceFrame,
    ZoneCalibration,
    zone_to_point3d,
    encode_observation as encode_spatial_observation,
    decode_observation as decode_spatial_observation,
    encode_frame as encode_spatial_frame,
    decode_frame as decode_spatial_frame,
)

__version__ = "0.3.0"

__all__ = [
    "CanFrame",
    "FrameFormat",
    "IdentifierFormat",
    "fd_dlc_to_length",
    "fd_length_to_dlc",
    "FD_VALID_LENGTHS",
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
    "GateState",
    "Clock",
    "SystemClock",
    "FixedClock",
    "Diagnostic",
    "DiagnosticType",
    "SequenceTracker",
    "SequenceAnomaly",
    "LivenessTracker",
    "LivenessState",
    "NodeCapability",
    "MessageCapability",
    "SignalCapability",
    "SchemaIdentity",
    "Compatibility",
    "check_compatibility",
    "Recorder",
    "Replay",
    "RecordedEvent",
    "SpatialObservationKind",
    "SpatialValidityStatus",
    "GeometryType",
    "AccelUnit",
    "GyroUnit",
    "SPATIAL_SCHEMA_ID",
    "SPATIAL_SCHEMA_VERSION",
    "RangeObservation",
    "TofZoneObservation",
    "Point3DObservation",
    "ImuObservation",
    "GeometryObservation",
    "ReferenceFrame",
    "ZoneCalibration",
    "zone_to_point3d",
    "encode_spatial_observation",
    "decode_spatial_observation",
    "encode_spatial_frame",
    "decode_spatial_frame",
    "__version__",
]
