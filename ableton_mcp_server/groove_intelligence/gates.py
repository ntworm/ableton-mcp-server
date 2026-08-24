"""Pure, published thresholds for the optional provider laboratory."""

from __future__ import annotations

from pydantic import Field

from .schema import GrooveModel


class GateThresholdsV1(GrooveModel):
    contract_invalid_max: int = Field(default=0, ge=0)
    fallback_pass_rate_min: float = Field(default=1.0, ge=0.0, le=1.0)
    reproducibility_match_rate_min: float = Field(default=1.0, ge=0.0, le=1.0)
    quality_hvo_f1_min: float = Field(default=0.90, ge=0.0, le=1.0)
    quality_feature_mae_max: float = Field(default=0.05, ge=0.0)
    privacy_path_leaks_max: int = Field(default=0, ge=0)
    blocked_lineage_max: int = Field(default=0, ge=0)
    p95_latency_seconds_max: float = Field(default=5.0, gt=0.0, le=5.0)
    peak_memory_mib_max: int = Field(default=512, gt=0, le=512)
    response_bytes_max: int = Field(default=262144, gt=0, le=262144)
    candidate_events_max: int = Field(default=2048, gt=0, le=2048)


__all__ = ["GateThresholdsV1"]
