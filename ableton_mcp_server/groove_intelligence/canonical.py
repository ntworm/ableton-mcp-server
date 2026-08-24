"""Canonical JSON and domain-separated content identities."""

from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from collections.abc import Mapping, Sequence
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation

from .schema import ArtifactId

_QUANTUM = Decimal("0.000000001")


def _number_text(value: int | float | Decimal) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("canonical numbers must be finite")
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError("canonical numbers must be finite") from error
    if not decimal.is_finite():
        raise ValueError("canonical numbers must be finite")
    decimal = decimal.quantize(_QUANTUM, rounding=ROUND_HALF_EVEN)
    if decimal == 0:
        return "0"
    text = format(decimal, "f").rstrip("0").rstrip(".")
    return text or "0"


def _normalize(value: object, *, key: str | None = None) -> object:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, (bool, int)):
        return value
    if isinstance(value, (float, Decimal)):
        # Validation and quantization happen in ``_encode`` so the value keeps
        # its JSON number type rather than becoming a quoted string.
        _number_text(value)
        return value
    if value is None:
        return None
    if isinstance(value, Mapping):
        normalized: dict[str, object] = {}
        for raw_key, raw_value in value.items():
            if not isinstance(raw_key, str):
                raise TypeError("canonical object keys must be strings")
            normalized_key = unicodedata.normalize("NFC", raw_key)
            if normalized_key in normalized:
                raise ValueError("canonical object has duplicate normalized keys")
            normalized[normalized_key] = _normalize(raw_value, key=normalized_key)
        for set_key in ("facets", "required_projection_ids"):
            set_values = normalized.get(set_key)
            if isinstance(set_values, list):
                serialized_set = sorted(
                    {
                        json.dumps(item, ensure_ascii=False, separators=(",", ":"))
                        for item in set_values
                    }
                )
                normalized[set_key] = [json.loads(item) for item in serialized_set]
        if "feature_constraints" in normalized and isinstance(
            normalized["feature_constraints"], list
        ):
            normalized["feature_constraints"] = sorted(
                normalized["feature_constraints"],
                key=lambda item: _encode(item),
            )
        return normalized
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [_normalize(item) for item in value]
    raise TypeError(f"unsupported canonical value: {type(value).__name__}")


def _encode(value: object) -> bytes:
    if value is None:
        return b"null"
    if value is True:
        return b"true"
    if value is False:
        return b"false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        return _number_text(value).encode("ascii")
    if isinstance(value, list):
        return b"[" + b",".join(_encode(item) for item in value) + b"]"
    if isinstance(value, dict):
        ordered = sorted(value.items(), key=lambda item: item[0])
        return b"{" + b",".join(
            _encode(key) + b":" + _encode(item) for key, item in ordered
        ) + b"}"
    raise TypeError(f"unsupported normalized value: {type(value).__name__}")


def canonical_json(value: object) -> bytes:
    """Return compact UTF-8 JSON with stable Unicode, numbers, and ordering."""

    return _encode(_normalize(value))


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def manifest_digest(manifest: Mapping[str, object]) -> str:
    """Digest manifest content without derived digest/checksum fields."""

    excluded = {
        "manifest_digest",
        "bundle_manifest_digest",
        "logical_index_digest",
        "file_checksums",
    }
    body = {key: value for key, value in manifest.items() if key not in excluded}
    return sha256_hex(canonical_json(body))


def bundle_manifest_digest(manifest: Mapping[str, object]) -> str:
    """Digest the bundle manifest, excluding only self/checksum fields."""

    excluded = {"bundle_manifest_digest", "file_checksums"}
    body = {key: value for key, value in manifest.items() if key not in excluded}
    return sha256_hex(canonical_json(body))


def artifact_id_from_identity(identity: Mapping[str, object]) -> ArtifactId:
    body = b"ABLETON-GROOVE-ARTIFACT-V1\x00" + canonical_json(
        {key: value for key, value in identity.items() if key != "artifact_id"}
    )
    return ArtifactId("ga1_" + sha256_hex(body))


def request_hash(request_for_hash: Mapping[str, object]) -> str:
    body = {key: value for key, value in request_for_hash.items() if key != "cursor"}
    return sha256_hex(b"ABLETON-GROOVE-REQUEST-V1\x00" + canonical_json(body))


def reproducibility_key(
    *,
    schema_versions: Mapping[str, str],
    seed_bundle_id: str,
    algorithm_versions: Mapping[str, str],
    canonical_request: Mapping[str, object],
    parent_artifact_ids: Sequence[str],
    provider_identity: Mapping[str, object],
) -> str:
    body = {
        "schema_versions": schema_versions,
        "seed_bundle_id": seed_bundle_id,
        "algorithm_versions": algorithm_versions,
        "canonical_request": canonical_request,
        "parent_artifact_ids": list(parent_artifact_ids),
        "provider_identity": provider_identity,
    }
    return sha256_hex(b"ABLETON-GROOVE-REPRODUCIBILITY-V1\x00" + canonical_json(body))
