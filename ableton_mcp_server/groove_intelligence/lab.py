"""Provider laboratory gates and sanitized canonical reports."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import Field

from .canonical import canonical_json
from .fallback import ProviderOutputInvalid, validate_provider_candidate
from .gates import GateThresholdsV1
from .promotion import HmacPromotionSigner, report_digest
from .provider import ProviderArtifactCandidate, ProviderIdentityInvalid, ProviderLimitsV1
from .schema import GrooveModel

_GATE_NAMES = (
    "contract",
    "fallback",
    "reproducibility",
    "quality",
    "privacy_license",
    "cost_latency",
)


class GateResultV1(GrooveModel):
    status: Literal["passed", "failed"]
    details: dict[str, object] = Field(default_factory=dict, max_length=16)


@dataclass(frozen=True)
class ProviderFixtureSet:
    fallback_pass_rate: float = 1.0
    reproducibility_match_rate: float = 1.0
    p95_latency_seconds: float = 0.1
    peak_memory_mib: float = 64.0
    response_bytes: float = 1024.0
    privacy_path_leaks: int = 0
    blocked_lineage: int = 0
    registry_opt_in: bool = True


class ProviderGateReportV1(GrooveModel):
    schema_version: Literal["groove.provider-gate.v1"] = "groove.provider-gate.v1"
    thresholds: GateThresholdsV1
    measurements: dict[str, float] = Field(default_factory=dict, max_length=32)
    gates: dict[str, GateResultV1] = Field(default_factory=dict, max_length=6)
    registry_opt_in: bool
    promotion_allowed: bool
    failed_gates: tuple[str, ...] = Field(default_factory=tuple, max_length=6)
    payload_digest: str = Field(default="", pattern=r"^(|[0-9a-f]{64})$")
    signature: str = Field(default="", pattern=r"^(|[0-9a-f]{64})$")
    signing_key_id: str = Field(min_length=1, max_length=64)


def _passed(value: bool, *, detail: str, measured: float | int | None = None) -> GateResultV1:
    values: dict[str, object] = {"detail": detail}
    if measured is not None:
        values["value"] = measured
    return GateResultV1(status="passed" if value else "failed", details=values)


def _identity_complete(candidate: ProviderArtifactCandidate) -> bool:
    try:
        candidate.identity.require_production_complete()
    except ProviderIdentityInvalid:
        return False
    return bool(candidate.identity.sampling_config)


def _private_content(candidate: ProviderArtifactCandidate) -> bool:
    forbidden = {"source_path", "path", "payload", "raw_payload", "blob", "notes", "sql", "sqlite"}
    stack: list[object] = [candidate.artifact.provenance, candidate.artifact.lineage]
    while stack:
        value = stack.pop()
        if isinstance(value, Mapping):
            if forbidden.intersection(str(key) for key in value):
                return True
            stack.extend(value.values())
        elif isinstance(value, (list, tuple)):
            stack.extend(value)
    return False


def measurements_for(gates: Mapping[str, GateResultV1]) -> dict[str, float]:
    values: dict[str, float] = {}
    for name, gate in gates.items():
        value = gate.details.get("value")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            values[name] = float(value)
        else:
            values[name] = 0.0 if gate.status == "passed" else 1.0
    return values


def build_gate_report(
    gates: Mapping[str, GateResultV1],
    *,
    thresholds: GateThresholdsV1,
    registry_opt_in: bool,
    signer: HmacPromotionSigner,
) -> ProviderGateReportV1:
    normalized = {name: gates[name] for name in _GATE_NAMES if name in gates}
    failed = tuple(sorted(name for name, gate in normalized.items() if gate.status != "passed"))
    report = ProviderGateReportV1(
        thresholds=thresholds,
        measurements=measurements_for(normalized),
        gates=normalized,
        registry_opt_in=registry_opt_in,
        promotion_allowed=not failed and registry_opt_in,
        failed_gates=failed,
        signing_key_id=signer.key_id,
    )
    digest = report_digest(report)
    return report.model_copy(
        update={"payload_digest": digest, "signature": signer.sign(digest)}
    )


def run_provider_gates(
    candidate: ProviderArtifactCandidate,
    fixture_set: ProviderFixtureSet,
    *,
    signer: HmacPromotionSigner | None = None,
) -> ProviderGateReportV1:
    signer = signer or HmacPromotionSigner(b"groove-provider-lab-key-v1")
    thresholds = GateThresholdsV1()
    try:
        validate_provider_candidate(candidate, ProviderLimitsV1())
        contract = _passed(True, detail="candidate contract accepted", measured=0)
    except (ProviderOutputInvalid, ProviderIdentityInvalid, ValueError, TypeError) as error:
        contract = _passed(False, detail=type(error).__name__, measured=1)
    contract_ok = contract.status == "passed"

    fallback = _passed(
        fixture_set.fallback_pass_rate >= thresholds.fallback_pass_rate_min,
        detail="deterministic fallback pass rate",
        measured=fixture_set.fallback_pass_rate,
    )
    reproducibility = _passed(
        contract_ok
        and _identity_complete(candidate)
        and fixture_set.reproducibility_match_rate
        >= thresholds.reproducibility_match_rate_min,
        detail="identity and seeded reproducibility",
        measured=fixture_set.reproducibility_match_rate,
    )
    quality_hvo = float(candidate.quality.get("hvo_f1", 0.0))
    quality_mae = float(candidate.quality.get("feature_mae", float("inf")))
    quality_ok = (
        contract_ok
        and quality_hvo >= thresholds.quality_hvo_f1_min
        and quality_mae <= thresholds.quality_feature_mae_max
    )
    quality = _passed(quality_ok, detail="published quality metrics", measured=quality_hvo)
    privacy_ok = (
        contract_ok
        and not _private_content(candidate)
        and str(candidate.rights.get("redistribution", "derived_only")) != "blocked"
        and int(candidate.rights.get("blocked_lineage", fixture_set.blocked_lineage))
        <= thresholds.blocked_lineage_max
        and fixture_set.privacy_path_leaks <= thresholds.privacy_path_leaks_max
    )
    privacy = _passed(
        privacy_ok,
        detail="privacy and rights checks",
        measured=fixture_set.privacy_path_leaks,
    )
    cost_ok = (
        fixture_set.p95_latency_seconds <= thresholds.p95_latency_seconds_max
        and fixture_set.peak_memory_mib <= thresholds.peak_memory_mib_max
        and fixture_set.response_bytes <= thresholds.response_bytes_max
        and sum(track.event_count for track in candidate.artifact.tracks)
        <= thresholds.candidate_events_max
    )
    cost = _passed(
        cost_ok,
        detail="bounded provider resources",
        measured=fixture_set.p95_latency_seconds,
    )
    return build_gate_report(
        {
            "contract": contract,
            "fallback": fallback,
            "reproducibility": reproducibility,
            "quality": quality,
            "privacy_license": privacy,
            "cost_latency": cost,
        },
        thresholds=thresholds,
        registry_opt_in=fixture_set.registry_opt_in,
        signer=signer,
    )


def write_lab_report(report: ProviderGateReportV1, path: Path) -> None:
    """Write only bounded canonical gate metadata, never candidate content."""

    payload = canonical_json(report.model_dump(mode="json"))
    if len(payload) > 32 * 1024:
        raise ValueError("provider lab report exceeds 32 KiB")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload + b"\n")


__all__ = [
    "GateResultV1",
    "ProviderFixtureSet",
    "ProviderGateReportV1",
    "build_gate_report",
    "measurements_for",
    "run_provider_gates",
    "write_lab_report",
]
