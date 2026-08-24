"""Per-test bounded payload factories for the optional provider contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from ableton_mcp_server.groove_intelligence.cards import ArtifactCardV1, ConditionCardV1
from ableton_mcp_server.groove_intelligence.lab import ProviderFixtureSet
from ableton_mcp_server.groove_intelligence.mcp_models import GenerateRequestV1
from ableton_mcp_server.groove_intelligence.promotion import HmacPromotionSigner
from ableton_mcp_server.groove_intelligence.provider import (
    ProviderArtifactCandidate,
    ProviderFailure,
    ProviderFailureCode,
    ProviderIdentityV1,
    ProviderLimitsV1,
    build_condition_card,
)
from ableton_mcp_server.groove_intelligence.provider_registry import (
    ProviderRegistry,
    load_provider_registry,
)
from ableton_mcp_server.groove_intelligence.runtime import GrooveRuntime
from tests.fixtures.groove_runtime import make_pilot_runtime

_PILOT_ARTIFACT_ID = "ga1_d0c40714f38991e35f37b87826e9f5a0ec18c216cf5f0123cc38ceccfdac6cbb"


class _FixtureProvider:
    provider_id = "fixture"

    def __init__(
        self,
        *,
        failure: ProviderFailure | None,
        candidate: ProviderArtifactCandidate | None,
        identity: ProviderIdentityV1,
    ) -> None:
        self.failure = failure
        self.candidate = candidate
        self.identity = identity

    def generate(
        self,
        condition_card: object,
        parent_artifact_ids: tuple[str, ...],
        seed: int,
        limits: ProviderLimitsV1,
    ) -> ProviderArtifactCandidate | ProviderFailure:
        del condition_card, parent_artifact_ids, seed, limits
        if self.failure is not None:
            return self.failure
        if self.candidate is not None:
            return self.candidate
        return make_provider_failure(ProviderFailureCode.offline_policy)


def make_pilot_card_and_id(tmp_path: Path) -> tuple[ArtifactCardV1, str]:
    runtime = make_pilot_runtime(tmp_path)
    artifact_id = str(runtime.index.manifest.artifact_ids[0])
    return runtime.card(artifact_id), artifact_id


def make_condition_card(tmp_path: Path, *, seed: int = 7) -> ConditionCardV1:
    card, artifact_id = make_pilot_card_and_id(tmp_path)
    return build_condition_card(
        card,
        parent_artifact_ids=(artifact_id,),
        seed=seed,
        limits=make_provider_limits(),
    )


def make_provider_limits(**overrides: object) -> ProviderLimitsV1:
    values: dict[str, object] = {}
    values.update(overrides)
    return ProviderLimitsV1(**values)


def make_provider_registry(tmp_path: Path) -> ProviderRegistry:
    path = tmp_path / "providers.json"
    path.write_text(
        json.dumps(
            {
                "providers": [
                    {
                        "provider_id": "fixture",
                        "executable": "echo_provider.py",
                        "executable_digest": "sha256:" + "a" * 64,
                        "version": "fixture-v1",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return load_provider_registry(path)


def make_provider_failure(
    code: ProviderFailureCode = ProviderFailureCode.internal,
) -> ProviderFailure:
    return ProviderFailure(
        code=code,
        provider_id="fixture",
        diagnostic_digest="a" * 16,
    )


def model_identity_missing_digest() -> ProviderIdentityV1:
    return ProviderIdentityV1(
        runtime="fixture-runtime",
        sampling_config={"temperature": 0.0},
        provider_version="fixture-v1",
        seed=7,
        parent_artifact_ids=("ga1_" + "a" * 64,),
    )


def make_candidate(
    tmp_path: Path,
    *,
    valid: bool = True,
    complete_identity: bool = True,
) -> ProviderArtifactCandidate:
    runtime = make_pilot_runtime(tmp_path)
    artifact_id = str(runtime.index.manifest.artifact_ids[0])
    # The first pilot row is a derived-only no-payload artifact; provider
    # candidates must carry a bounded raw MIDI payload for validation.
    candidate_artifact_id = str(runtime.index.manifest.artifact_ids[1])
    identity = (
        ProviderIdentityV1(
            model_digest="sha256:" + "b" * 64,
            runtime="fixture-runtime",
            sampling_config={"temperature": 0.0},
            provider_version="fixture-v1",
            seed=7,
            parent_artifact_ids=(artifact_id,),
        )
        if complete_identity
        else model_identity_missing_digest()
    )
    artifact = runtime.store.get(candidate_artifact_id)
    if not valid:
        identity = identity.model_copy(update={"model_digest": "not-a-digest"})
    payload_digest = artifact.payload.sha256 if valid else "0" * 64
    return ProviderArtifactCandidate(
        provider_id="fixture",
        identity=identity,
        artifact=artifact,
        payload_digest=payload_digest,
        quality={"hvo_f1": 0.95, "feature_mae": 0.01},
        rights={
            "redistribution": str(artifact.provenance.get("redistribution", "derived_only")),
            "blocked_lineage": 0,
        },
    )


def make_provider_runtime(
    tmp_path: Path,
    *,
    failure: ProviderFailure | None = None,
    candidate: ProviderArtifactCandidate | None = None,
    identity: ProviderIdentityV1 | None = None,
) -> GrooveRuntime:
    runtime = make_pilot_runtime(tmp_path)
    selected_identity = identity or ProviderIdentityV1(
        model_digest="sha256:" + "a" * 64,
        runtime="fixture-runtime",
        sampling_config={"temperature": 0.0},
        provider_version="fixture-v1",
        seed=7,
        parent_artifact_ids=(_PILOT_ARTIFACT_ID,),
    )
    runtime.provider = _FixtureProvider(
        failure=failure,
        candidate=candidate,
        identity=selected_identity,
    )
    return runtime


def make_deterministic_request(
    provider: Literal["deterministic", "neural"] = "neural",
    seed: int = 7,
) -> GenerateRequestV1:
    return GenerateRequestV1(
        schema_version="groove.generate.request.v1",
        source={"artifact_id": _PILOT_ARTIFACT_ID},
        transforms={"density": 0.2},
        bars=4,
        seed=seed,
        provider=provider,
    )


def make_fixture_set(tmp_path: Path) -> ProviderFixtureSet:
    del tmp_path
    return ProviderFixtureSet()


def make_promotion_signer() -> HmacPromotionSigner:
    return HmacPromotionSigner(b"groove-provider-lab-key-v1")


__all__ = [
    "make_candidate",
    "make_condition_card",
    "make_deterministic_request",
    "make_pilot_card_and_id",
    "make_provider_failure",
    "make_provider_limits",
    "make_provider_registry",
    "make_provider_runtime",
    "make_fixture_set",
    "make_promotion_signer",
    "model_identity_missing_digest",
]
