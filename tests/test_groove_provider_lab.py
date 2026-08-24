from __future__ import annotations

from pathlib import Path

from ableton_mcp_server.groove_intelligence.deterministic import deterministic_generate
from ableton_mcp_server.groove_intelligence.gates import GateThresholdsV1
from ableton_mcp_server.groove_intelligence.lab import (
    run_provider_gates,
    write_lab_report,
)
from ableton_mcp_server.groove_intelligence.promotion import promotion_allowed
from tests.fixtures.groove_provider_payloads import (
    make_candidate,
    make_deterministic_request,
    make_fixture_set,
    make_promotion_signer,
    make_provider_runtime,
)


def test_failed_gate_keeps_provider_disabled_and_deterministic_runtime_green(
    tmp_path: Path,
) -> None:
    report = run_provider_gates(
        make_candidate(tmp_path / "candidate", valid=False), make_fixture_set(tmp_path / "fixtures")
    )
    assert report.promotion_allowed is False
    assert set(report.failed_gates) >= {"contract", "privacy_license"}
    assert promotion_allowed(report, make_promotion_signer()) is False
    runtime = make_provider_runtime(tmp_path / "runtime")
    result = deterministic_generate(
        runtime, make_deterministic_request(provider="deterministic")
    )
    assert str(result.artifact.artifact_id).startswith("ga1_")


def test_reproducibility_gate_requires_complete_identity(tmp_path: Path) -> None:
    report = run_provider_gates(
        make_candidate(tmp_path / "candidate", complete_identity=False),
        make_fixture_set(tmp_path / "fixtures"),
    )
    assert report.gates["reproducibility"].status == "failed"
    assert report.promotion_allowed is False


def test_lab_report_contains_no_path_raw_payload_or_secret(tmp_path: Path) -> None:
    path = tmp_path / "report.json"
    report = run_provider_gates(
        make_candidate(tmp_path / "candidate"), make_fixture_set(tmp_path / "fixtures")
    )
    write_lab_report(report, path)
    text = path.read_text(encoding="utf-8")
    assert "source_path" not in text
    assert "raw_payload" not in text and "TOKEN" not in text


def test_promotion_requires_canonical_identity_signature_and_thresholds(tmp_path: Path) -> None:
    signer = make_promotion_signer()
    report = run_provider_gates(
        make_candidate(tmp_path / "candidate"),
        make_fixture_set(tmp_path / "fixtures"),
        signer=signer,
    )
    assert promotion_allowed(report, signer) is True
    tampered = report.model_copy(
        update={
            "thresholds": report.thresholds.model_copy(
                update={"quality_hvo_f1_min": 0.91}
            )
        }
    )
    assert promotion_allowed(tampered, signer) is False
    assert promotion_allowed(report.model_copy(update={"signature": "00" * 32}), signer) is False


def test_threshold_defaults_are_published_and_stable() -> None:
    thresholds = GateThresholdsV1()
    assert thresholds.contract_invalid_max == 0
    assert thresholds.fallback_pass_rate_min == 1.0
    assert thresholds.reproducibility_match_rate_min == 1.0
    assert thresholds.quality_hvo_f1_min == 0.90
    assert thresholds.quality_feature_mae_max == 0.05
    assert thresholds.privacy_path_leaks_max == 0
    assert thresholds.blocked_lineage_max == 0
    assert thresholds.p95_latency_seconds_max == 5.0
    assert thresholds.peak_memory_mib_max == 512
    assert thresholds.response_bytes_max == 262144
    assert thresholds.candidate_events_max == 2048
