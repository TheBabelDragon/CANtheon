"""CANtheon boundary API discovery (no transport by default).

Exposes schema identity, compatibility helpers, and health for downstream
adapters (MetaField). Does not start HTTP/MQTT or import MetaField/TensorGate.
"""

from __future__ import annotations

from typing import Any

from .adapters.metafield_contract import (
    BOUNDARY_SCHEMA,
    BOUNDARY_SCHEMA_ID,
    BOUNDARY_SCHEMA_VERSION,
    assert_compatible,
)
from .schema_compat import SchemaIdentity

API_SCHEMA_ID = "cantheon.boundary_api"
API_SCHEMA_VERSION = "1.0.0"


def health() -> dict[str, Any]:
    return {
        "schema_id": API_SCHEMA_ID,
        "schema_version": API_SCHEMA_VERSION,
        "healthy": True,
        "boundary": {
            "schema_id": BOUNDARY_SCHEMA_ID,
            "schema_version": BOUNDARY_SCHEMA_VERSION,
        },
        "capabilities": [
            "observation_envelope",
            "diagnostic_envelope",
            "dual_timestamps",
            "quality_preservation",
            "schema_compatibility",
            "record_replay",
        ],
        "non_goals": [
            "http_server",
            "redis",
            "mqtt",
            "hardware_transmit_by_default",
            "remote_control_authority",
        ],
    }


def boundary_schema() -> SchemaIdentity:
    return BOUNDARY_SCHEMA


def check_consumer(expected_id: str, expected_version: str) -> dict[str, Any]:
    """Validate a consumer's expected boundary schema (fail-closed on major clash)."""
    expected = SchemaIdentity(expected_id, expected_version)
    try:
        result = assert_compatible(expected)
        return {
            "ok": True,
            "compatibility": getattr(result, "value", str(result)),
            "producer": {"schema_id": BOUNDARY_SCHEMA_ID, "schema_version": BOUNDARY_SCHEMA_VERSION},
        }
    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
            "producer": {"schema_id": BOUNDARY_SCHEMA_ID, "schema_version": BOUNDARY_SCHEMA_VERSION},
        }
