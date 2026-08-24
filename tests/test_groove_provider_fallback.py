from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from ableton_mcp_server.groove_intelligence.canonical import canonical_json
from ableton_mcp_server.groove_intelligence.deterministic import deterministic_generate
from ableton_mcp_server.groove_intelligence.fallback import (
    ProviderOutputInvalid,
    generate_with_provider,
    validate_provider_candidate,
)
from ableton_mcp_server.groove_intelligence.provider import (
    ProviderArtifactCandidate,
    ProviderFailure,
    ProviderFailureCode,
    ProviderIdentityInvalid,
    ProviderIdentityV1,
    ProviderLimitsV1,
)
from tests.fixtures.groove_provider_payloads import (
    make_candidate,
    make_deterministic_request,
    make_provider_failure,
    make_provider_runtime,
    model_identity_missing_digest,
)


def _valid_candidate(tmp_path: Path) -> ProviderArtifactCandidate:
    runtime = make_provider_runtime(tmp_path / "generated")
    generated = deterministic_generate(
        runtime,
        make_deterministic_request(provider="deterministic"),
    )
    artifact = runtime.store.get(str(generated.artifact.artifact_id))
    base = make_candidate(tmp_path / "candidate", valid=True)
    return base.model_copy(
        update={
            "artifact": artifact,
            "payload_digest": artifact.payload.sha256,
            "rights": {
                "redistribution": str(artifact.provenance.get("redistribution", "derived_only")),
                "blocked_lineage": 0,
            },
        }
    )


@pytest.mark.parametrize("failure", list(ProviderFailureCode))
def test_every_neural_failure_returns_same_deterministic_artifact(
    tmp_path: Path, failure: ProviderFailureCode
) -> None:
    runtime = make_provider_runtime(tmp_path / "neural", failure=make_provider_failure(failure))
    request = make_deterministic_request(provider="neural", seed=7)
    result = generate_with_provider(runtime, request)

    expected_runtime = make_provider_runtime(tmp_path / "deterministic")
    expected = generate_with_provider(
        expected_runtime, make_deterministic_request(provider="deterministic", seed=7)
    )

    assert result.artifact.artifact_id == expected.artifact.artifact_id
    assert result.card.provider_resolved == "deterministic"
    assert isinstance(result.card.fallback, dict)
    assert result.card.fallback["reason"] == failure.value


def test_invalid_neural_candidate_is_not_stored_or_reported_as_success(
    tmp_path: Path,
) -> None:
    runtime = make_provider_runtime(
        tmp_path,
        candidate=make_candidate(tmp_path / "candidate", valid=False),
    )
    result = generate_with_provider(
        runtime, make_deterministic_request(provider="neural", seed=3)
    )

    assert isinstance(result.card.fallback, dict)
    assert result.card.fallback["reason"] == ProviderFailureCode.output_invalid.value
    assert getattr(runtime.store, "contains_provider_artifact", False) is False


def test_missing_model_identity_is_rejected_for_neural_production(tmp_path: Path) -> None:
    with pytest.raises(ProviderIdentityInvalid):
        generate_with_provider(
            make_provider_runtime(tmp_path, identity=model_identity_missing_digest()),
            make_deterministic_request(provider="neural", seed=1),
        )


def test_provider_candidate_validation_checks_payload_hash_and_limits(tmp_path: Path) -> None:
    candidate = _valid_candidate(tmp_path)
    assert validate_provider_candidate(candidate, ProviderLimitsV1()) == candidate.artifact

    invalid = candidate.model_copy(update={"payload_digest": "0" * 64})
    with pytest.raises(ProviderOutputInvalid):
        validate_provider_candidate(invalid, ProviderLimitsV1())


def test_provider_candidate_cannot_elevate_parent_rights(tmp_path: Path) -> None:
    candidate = _valid_candidate(tmp_path).model_copy(
        update={"rights": {"redistribution": "full", "blocked_lineage": 0}}
    )
    with pytest.raises(ProviderOutputInvalid):
        validate_provider_candidate(candidate, ProviderLimitsV1())


def test_provider_rights_use_real_parent_meet_and_reject_unknown_values(
    tmp_path: Path,
) -> None:
    base = _valid_candidate(tmp_path)
    provenance = {
        **base.artifact.provenance,
        "redistribution": "full",
        "rights_level": 2,
    }
    provenance["provenance_digest"] = sha256(
        canonical_json(
            {key: value for key, value in provenance.items() if key != "provenance_digest"}
        )
    ).hexdigest()
    elevated = base.model_copy(
        update={
            "artifact": base.artifact.model_copy(update={"provenance": provenance}),
            "rights": {"redistribution": "full", "blocked_lineage": 0},
        }
    )
    with pytest.raises(ProviderOutputInvalid):
        validate_provider_candidate(
            elevated,
            ProviderLimitsV1(),
            effective_redistribution="derived_only",
            effective_rights_level=1,
        )

    bogus = base.model_copy(
        update={"rights": {"redistribution": "bogus", "blocked_lineage": 0}}
    )
    with pytest.raises(ProviderOutputInvalid):
        validate_provider_candidate(bogus, ProviderLimitsV1())


def test_provider_provenance_digest_is_verified(tmp_path: Path) -> None:
    candidate = _valid_candidate(tmp_path)
    artifact = candidate.artifact.model_copy(
        update={
            "provenance": {
                **candidate.artifact.provenance,
                "summary": {"tampered": True},
            }
        }
    )
    tampered = candidate.model_copy(update={"artifact": artifact})
    with pytest.raises(ProviderOutputInvalid):
        validate_provider_candidate(tampered, ProviderLimitsV1())


def test_invalid_provider_blob_falls_back_before_store(tmp_path: Path) -> None:
    runtime = make_provider_runtime(tmp_path / "invalid-blob")
    source_id = str(runtime.index.manifest.artifact_ids[0])
    request = make_deterministic_request(provider="deterministic", seed=11)
    request.source = request.source.model_copy(update={"artifact_id": source_id})
    generated = deterministic_generate(
        runtime,
        request,
    )
    valid_artifact = runtime.store.get(str(generated.artifact.artifact_id))
    base = _valid_candidate(tmp_path / "candidate")
    candidate = base.model_copy(
        update={
            "artifact": valid_artifact.model_copy(
                update={
                    "payload": valid_artifact.payload.model_copy(
                        update={"blob": b"not-midi", "compressed_size": 8}
                    )
                }
            ),
            "payload_digest": valid_artifact.payload.sha256,
            "identity": base.identity.model_copy(
                update={"parent_artifact_ids": (source_id,)}
            ),
        }
    )

    class InvalidBlobProvider:
        provider_id = "invalid-blob"
        identity = candidate.identity

        def generate(
            self,
            condition_card: object,
            parent_artifact_ids: tuple[str, ...],
            seed: int,
            limits: ProviderLimitsV1,
        ) -> ProviderArtifactCandidate:
            del condition_card, parent_artifact_ids, seed, limits
            return candidate

    runtime.provider = InvalidBlobProvider()
    neural_request = make_deterministic_request(provider="neural")
    neural_request.source = neural_request.source.model_copy(update={"artifact_id": source_id})
    result = generate_with_provider(runtime, neural_request)

    assert result.card.provider_resolved == "deterministic"
    assert result.card.fallback["reason"] == ProviderFailureCode.output_invalid.value  # type: ignore[index]


def test_provider_summary_and_lineage_are_recursively_public(tmp_path: Path) -> None:
    runtime = make_provider_runtime(tmp_path / "leak")
    source_id = str(runtime.index.manifest.artifact_ids[0])
    request = make_deterministic_request(provider="deterministic", seed=12)
    request.source = request.source.model_copy(update={"artifact_id": source_id})
    generated = deterministic_generate(
        runtime,
        request,
    )
    valid_artifact = runtime.store.get(str(generated.artifact.artifact_id))
    malicious_artifact = valid_artifact.model_copy(
        update={
            "provenance": {
                **valid_artifact.provenance,
                "summary": {
                    "meter": "4/4",
                    "source_path": "C:/private/source.mid",
                    "nested": {"notes": ["do-not-expose"], "safe": "drop"},
                },
            },
            "lineage": {
                **valid_artifact.lineage,
                "private_path": "C:/private/lineage",
                "nested": {"payload": "do-not-expose"},
            },
        }
    )
    base = make_candidate(tmp_path / "candidate", valid=True)
    candidate = base.model_copy(
        update={
            "artifact": malicious_artifact,
            "payload_digest": malicious_artifact.payload.sha256,
            "identity": base.identity.model_copy(
                update={"parent_artifact_ids": (source_id,)}
            ),
        }
    )

    class MaliciousProvider:
        provider_id = "malicious"
        identity = candidate.identity

        def generate(
            self,
            condition_card: object,
            parent_artifact_ids: tuple[str, ...],
            seed: int,
            limits: ProviderLimitsV1,
        ) -> ProviderArtifactCandidate:
            del condition_card, parent_artifact_ids, seed, limits
            return candidate

    runtime.provider = MaliciousProvider()
    neural_request = make_deterministic_request(provider="neural")
    neural_request.source = neural_request.source.model_copy(update={"artifact_id": source_id})
    result = generate_with_provider(runtime, neural_request)
    serialized = result.model_dump_json()

    assert "source_path" not in serialized
    assert "private_path" not in serialized
    assert "do-not-expose" not in serialized
    assert result.artifact.summary["meter"] == "4/4"
    assert result.artifact.summary["bars"] == 4
    assert "private_path" not in result.artifact.lineage
    stored = runtime.store.get(str(result.artifact.artifact_id))
    stored_json = canonical_json(
        {"provenance": stored.provenance, "lineage": stored.lineage}
    ).decode("utf-8")
    assert "source_path" not in stored_json
    assert "private_path" not in stored_json
    assert "do-not-expose" not in stored_json


def test_provider_id_mismatch_fails_closed_to_deterministic(
    tmp_path: Path,
) -> None:
    runtime = make_provider_runtime(tmp_path / "provider-id")
    candidate = _valid_candidate(tmp_path / "candidate").model_copy(
        update={"provider_id": "untrusted-returned-id"}
    )

    class MismatchProvider:
        provider_id = "authoritative-provider"
        identity = candidate.identity

        def generate(
            self,
            condition_card: object,
            parent_artifact_ids: tuple[str, ...],
            seed: int,
            limits: ProviderLimitsV1,
        ) -> ProviderArtifactCandidate:
            del condition_card, parent_artifact_ids, seed, limits
            return candidate

    runtime.provider = MismatchProvider()
    result = generate_with_provider(
        runtime, make_deterministic_request(provider="neural", seed=13)
    )
    assert result.card.provider_resolved == "deterministic"
    assert result.card.fallback["reason"] == ProviderFailureCode.output_invalid.value  # type: ignore[index]


def test_neural_provider_receives_all_multi_parent_ids_and_fallback_lineage(
    tmp_path: Path,
) -> None:
    runtime = make_provider_runtime(tmp_path)
    primary_id = str(runtime.index.manifest.artifact_ids[0])
    reference_id = str(runtime.index.manifest.artifact_ids[1])

    class CapturingProvider:
        provider_id = "capture"

        def __init__(self) -> None:
            self.condition_parent_ids: tuple[str, ...] = ()
            self.call_parent_ids: tuple[str, ...] = ()
            self.identity = ProviderIdentityV1(
                model_digest="sha256:" + "c" * 64,
                runtime="capture-runtime",
                sampling_config={"temperature": 0.0},
                provider_version="capture-v1",
                seed=7,
                parent_artifact_ids=(primary_id, reference_id),
            )

        def generate(
            self,
            condition_card: object,
            parent_artifact_ids: tuple[str, ...],
            seed: int,
            limits: ProviderLimitsV1,
        ) -> ProviderFailure:
            del seed, limits
            self.condition_parent_ids = tuple(condition_card.parent_artifact_ids)  # type: ignore[attr-defined]
            self.call_parent_ids = parent_artifact_ids
            return ProviderFailure(
                code=ProviderFailureCode.offline_policy,
                provider_id=self.provider_id,
                diagnostic_digest="c" * 16,
            )

    provider = CapturingProvider()
    runtime.provider = provider
    request = make_deterministic_request(provider="neural").model_copy(
        update={"reference_artifact_ids": [reference_id]}
    )
    result = generate_with_provider(runtime, request)
    expected = (primary_id, reference_id)
    assert provider.condition_parent_ids == expected
    assert provider.call_parent_ids == expected
    assert result.card.parent_artifact_ids == expected
    assert result.card.lineage["parent_artifact_ids"] == list(expected)


def test_neural_provider_success_records_all_multi_parent_lineage(
    tmp_path: Path,
) -> None:
    runtime = make_provider_runtime(tmp_path / "success")
    primary_id = str(runtime.index.manifest.artifact_ids[0])
    reference_id = str(runtime.index.manifest.artifact_ids[1])
    parent_ids = (primary_id, reference_id)
    base = _valid_candidate(tmp_path / "candidate")
    artifact = base.artifact.model_copy(
        update={
            "lineage": {
                "parent_artifact_ids": list(parent_ids),
                "relations": ["provider_recombination", "provider_recombination"],
                "ordinals": [0, 1],
            }
        }
    )
    candidate = base.model_copy(
        update={
            "provider_id": "success",
            "identity": base.identity.model_copy(update={"parent_artifact_ids": parent_ids}),
            "artifact": artifact,
        }
    )

    class SuccessProvider:
        provider_id = "success"
        identity = candidate.identity

        def generate(
            self,
            condition_card: object,
            parent_artifact_ids: tuple[str, ...],
            seed: int,
            limits: ProviderLimitsV1,
        ) -> ProviderArtifactCandidate:
            del condition_card, seed, limits
            assert parent_artifact_ids == parent_ids
            return candidate

    runtime.provider = SuccessProvider()
    request = make_deterministic_request(provider="neural").model_copy(
        update={"reference_artifact_ids": [reference_id]}
    )
    result = generate_with_provider(runtime, request)

    assert result.card.provider_resolved == "success"
    assert result.card.parent_artifact_ids == parent_ids
    assert result.card.lineage["parent_artifact_ids"] == list(parent_ids)
    assert result.artifact.lineage["parent_artifact_ids"] == list(parent_ids)
