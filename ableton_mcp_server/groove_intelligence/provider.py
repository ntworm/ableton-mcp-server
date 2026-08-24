"""Contracts for the optional, isolated groove provider boundary.

This module deliberately contains no model loader and no process or network
code.  The deterministic generator remains the complete default runtime.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from enum import Enum
from hashlib import sha256
from typing import Any, Protocol

from pydantic import Field, field_validator

from .canonical import canonical_json
from .cards import ArtifactCardV1, ConditionCardV1
from .schema import GrooveModel, MidiArtifactV1

_DIGEST_RE = r"^sha256:[0-9a-f]{64}$"
_HEX_DIGEST_RE = r"^[0-9a-f]{16,64}$"
_FORBIDDEN_KEYS = frozenset(
    {"blob", "notes", "payload", "path", "private_path", "source_path", "sql", "sqlite"}
)


class ProviderIdentityInvalid(ValueError):
    """A neural result does not contain the identity required for promotion."""


class ProviderProtocolError(ValueError):
    """A provider request or response violates the closed provider contract."""


class ProviderFailureCode(str, Enum):
    not_installed = "not_installed"
    launch_denied = "launch_denied"
    offline_policy = "offline_policy"
    protocol_violation = "protocol_violation"
    timeout = "timeout"
    exit_nonzero = "exit_nonzero"
    output_too_large = "output_too_large"
    output_invalid = "output_invalid"
    resource_limit = "resource_limit"
    internal = "internal"


class ProviderLimitsV1(GrooveModel):
    startup_seconds: float = Field(default=2.0, gt=0.0, le=2.0)
    generation_seconds: float = Field(default=5.0, gt=0.0, le=5.0)
    shutdown_seconds: float = Field(default=1.0, gt=0.0, le=1.0)
    cpu_seconds: float = Field(default=2.0, gt=0.0, le=2.0)
    memory_mib: int = Field(default=512, gt=0, le=512)
    max_frame_bytes: int = Field(default=256 * 1024, gt=0, le=256 * 1024)
    max_response_bytes: int = Field(default=256 * 1024, gt=0, le=256 * 1024)
    max_stderr_bytes: int = Field(default=16 * 1024, gt=0, le=16 * 1024)
    max_depth: int = Field(default=8, gt=0, le=8)
    max_events: int = Field(default=2048, gt=0, le=2048)


def make_provider_limits(**overrides: object) -> ProviderLimitsV1:
    """Return the published provider limits, with test-only bounded overrides."""

    return ProviderLimitsV1.model_validate(overrides)


class ProviderIdentityV1(GrooveModel):
    model_digest: str | None = Field(default=None, pattern=_DIGEST_RE)
    runtime: str = Field(min_length=1, max_length=128)
    sampling_config: dict[str, Any] = Field(default_factory=dict)
    provider_version: str = Field(min_length=1, max_length=64)
    seed: int = Field(ge=0)
    parent_artifact_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=8)

    @field_validator("sampling_config")
    @classmethod
    def _bounded_sampling(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(value) > 16:
            raise ValueError("sampling_config has too many fields")
        if any(key in _FORBIDDEN_KEYS for key in value):
            raise ValueError("sampling_config contains a private field")
        return value

    def require_production_complete(self) -> None:
        if (
            self.model_digest is None
            or re.fullmatch(_DIGEST_RE, self.model_digest) is None
            or not self.runtime
            or not self.provider_version
            or not self.parent_artifact_ids
        ):
            raise ProviderIdentityInvalid("provider identity is incomplete")


class ProviderFailure(GrooveModel):
    code: ProviderFailureCode
    provider_id: str = Field(min_length=1, max_length=64)
    diagnostic_digest: str = Field(pattern=_HEX_DIGEST_RE)
    diagnostic: str = Field(default="", max_length=256)

    @field_validator("diagnostic")
    @classmethod
    def _sanitize_diagnostic(cls, value: str) -> str:
        return sanitize_provider_diagnostic(value)


class ProviderArtifactCandidate(GrooveModel):
    provider_id: str = Field(min_length=1, max_length=64)
    identity: ProviderIdentityV1
    artifact: MidiArtifactV1
    payload_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    quality: dict[str, float] = Field(default_factory=dict)
    rights: dict[str, Any] = Field(default_factory=dict)

    @field_validator("quality")
    @classmethod
    def _bounded_quality(cls, value: dict[str, float]) -> dict[str, float]:
        if len(value) > 16:
            raise ValueError("quality has too many fields")
        return value

    @field_validator("rights")
    @classmethod
    def _bounded_rights(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(value) > 16 or _FORBIDDEN_KEYS.intersection(value):
            raise ValueError("rights contains a private field")
        return value


class ProviderConditionCardV1(ConditionCardV1):
    """The only payload permitted across the provider process boundary."""

    identity: ProviderIdentityV1
    parent_artifact_ids: tuple[str, ...] = Field(max_length=8)
    seed: int = Field(ge=0)
    limits: ProviderLimitsV1


class GrooveProvider(Protocol):
    def generate(
        self,
        condition_card: ProviderConditionCardV1,
        parent_artifact_ids: tuple[str, ...],
        seed: int,
        limits: ProviderLimitsV1,
    ) -> ProviderArtifactCandidate | ProviderFailure:
        """Generate one bounded candidate or one stable failure."""


def _public_value(value: object, *, depth: int = 0) -> object:
    if depth > 4:
        return None
    if isinstance(value, Mapping):
        return {
            str(key): _public_value(item, depth=depth + 1)
            for key, item in value.items()
            if str(key).lower() not in _FORBIDDEN_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_public_value(item, depth=depth + 1) for item in value[:32]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)[:128]


def build_condition_card(
    card: ArtifactCardV1 | ConditionCardV1,
    *,
    parent_artifact_ids: tuple[str, ...],
    seed: int,
    limits: ProviderLimitsV1,
) -> ProviderConditionCardV1:
    """Project a public artifact card into the bounded provider request."""

    if len(parent_artifact_ids) == 0 or len(parent_artifact_ids) > 8:
        raise ProviderProtocolError("provider requires one to eight parent artifacts")
    identity = ProviderIdentityV1(
        model_digest="sha256:" + "a" * 64,
        runtime="optional-provider-v1",
        sampling_config={"temperature": 0.0},
        provider_version="contract-v1",
        seed=seed,
        parent_artifact_ids=parent_artifact_ids,
    )
    summary_value = _public_value(card.summary) if isinstance(card.summary, Mapping) else {}
    summary = dict(summary_value) if isinstance(summary_value, Mapping) else {}
    return ProviderConditionCardV1(
        summary=summary,
        facets={
            str(key): [str(item) for item in values[:32]] for key, values in card.facets.items()
        },
        features={
            str(key): item
            for key, item in list(card.features.items())[:64]
            if isinstance(item, (str, int, float)) or item is None
        },
        projections=dict(list(card.projections.items())[:3]),
        warnings=[str(item)[:128] for item in getattr(card, "warnings", [])[:32]],
        identity=identity,
        parent_artifact_ids=parent_artifact_ids,
        seed=seed,
        limits=limits,
    )


def sanitize_provider_diagnostic(text: str) -> str:
    """Remove local paths, command details, and secret assignments."""

    value = str(text).replace("\r", " ").replace("\n", " ")
    value = re.sub(
        r"(?i)[A-Za-z]:[\\/][^\s]*?[\\/](token|key|secret|password|proxy)=[^\s]+",
        lambda match: "<path> " + match.group(1).lower() + "=<redacted>",
        value,
    )
    value = re.sub(
        r"(?i)\b(token|key|secret|password|proxy|authorization)\s*[=:]\s*[^\s]+",
        lambda match: match.group(1).lower() + "=<redacted>",
        value,
    )
    value = re.sub(r"(?:[A-Za-z]:[\\/]|/|\\\\)[^\s]+", "<path>", value)
    value = re.sub(r"(?i)(?:python|node|\.exe|\.cmd)\s+[^\s]+(?:\s+[^\s]+)*", "<command>", value)
    return value[:256].strip()


def diagnostic_digest(text: str) -> str:
    digest_input = canonical_json({"diagnostic": sanitize_provider_diagnostic(text)})
    return sha256(digest_input).hexdigest()[:16]


__all__ = [
    "GrooveProvider",
    "ProviderArtifactCandidate",
    "ProviderConditionCardV1",
    "ProviderFailure",
    "ProviderFailureCode",
    "ProviderIdentityInvalid",
    "ProviderIdentityV1",
    "ProviderLimitsV1",
    "ProviderProtocolError",
    "build_condition_card",
    "diagnostic_digest",
    "make_provider_limits",
    "sanitize_provider_diagnostic",
]
