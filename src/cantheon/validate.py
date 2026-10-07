"""Observation validation.

Does not discard invalid input. Makes quality/state observable.
"""

from __future__ import annotations

from typing import Optional

from .observation import Observation, Quality
from .signal import SignalDef


def validate_observation(
    obs: Observation,
    signal_def: Optional[SignalDef] = None,
) -> Observation:
    """Re-evaluate quality flags. Returns a new Observation if quality changes.

    Rules:
      - already DECODE_ERROR / INVALID stays
      - OUT_OF_RANGE if value outside signal min/max
      - otherwise VALID
    """
    if obs.quality in (Quality.DECODE_ERROR, Quality.INVALID):
        return obs

    quality = obs.quality
    if signal_def is not None:
        if signal_def.min_value is not None and obs.value < signal_def.min_value:
            quality = Quality.OUT_OF_RANGE
        if signal_def.max_value is not None and obs.value > signal_def.max_value:
            quality = Quality.OUT_OF_RANGE

    if quality == obs.quality:
        return obs

    # produce a new frozen observation with updated quality
    return Observation(
        node_id=obs.node_id,
        message_id=obs.message_id,
        signal_id=obs.signal_id,
        value=obs.value,
        unit=obs.unit,
        timestamp_ns=obs.timestamp_ns,
        sequence=obs.sequence,
        quality=quality,
        source=obs.source,
        provenance=obs.provenance,
        raw_value=obs.raw_value,
        message_name=obs.message_name,
        signal_name=obs.signal_name,
        schema_version=obs.schema_version,
        extra=dict(obs.extra),
    )
