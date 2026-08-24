"""Deterministic bounded search, ranker, and signed pagination cursor."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
from collections.abc import Mapping
from functools import lru_cache
from typing import Any

from .canonical import canonical_json, request_hash
from .cards import ArtifactCardV1
from .constants import (
    CURSOR_DOMAIN,
    RANKER_ID,
    RANKER_MANIFEST_DIGEST,
    RANKER_NO_PROJECTION_WEIGHTS,
    RANKER_SCHEMA,
    RANKER_WEIGHTS,
)
from .mcp_models import (
    RankedCandidateV1,
    RankingV1,
    SearchCursorV1,
    SearchRequestV1,
    SearchResponseV1,
)
from .taxonomy import normalize_facet_value, search_tokens

_CURSOR_DOMAIN = CURSOR_DOMAIN
_WEIGHTS = RANKER_WEIGHTS
_NO_PROJECTION_WEIGHTS = RANKER_NO_PROJECTION_WEIGHTS


class GrooveCursorInvalid(ValueError):
    """A cursor failed canonical, checksum, or schema validation."""


class GrooveCursorQueryMismatch(GrooveCursorInvalid):
    """A cursor was used with a request other than its originating request."""


class GrooveCursorBundleMismatch(GrooveCursorInvalid):
    """A cursor belongs to a different immutable seed bundle."""


class GrooveCursorRankerMismatch(GrooveCursorInvalid):
    """A cursor belongs to a different ranker/schema."""


def _quantize_nine(value: float) -> float:
    return float(f"{value:.9f}")


@lru_cache(maxsize=4096)
def _cached_tokens(value: str) -> frozenset[str]:
    return frozenset(search_tokens(value))


def _tokens(value: object) -> frozenset[str]:
    return _cached_tokens(str(value))


def _card_tokens(card: ArtifactCardV1) -> set[str]:
    values: list[object] = [*card.facets.keys(), *card.projections.keys(), *card.features.keys()]
    values.extend(value for axis in card.facets.values() for value in axis)
    values.extend(
        card.summary.get("roles", []) if isinstance(card.summary.get("roles"), list) else []
    )
    values.append(card.summary.get("meter", ""))
    tokens: set[str] = set()
    for value in values:
        tokens.update(_tokens(value))
    return tokens


def _feature_map(card: ArtifactCardV1) -> dict[str, float | int | str | None]:
    return card.features


def _as_float(value: object) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        return float(value)
    raise TypeError("feature value is not numeric")


def _constraint_matches(features: Mapping[str, object], constraint: Mapping[str, object]) -> bool:
    name = str(constraint.get("name", ""))
    value = features.get(name)
    if value is None or isinstance(value, bool):
        return False
    try:
        observed = _as_float(value)
    except (TypeError, ValueError):
        return False
    operation = str(constraint.get("op", "eq"))
    requested = constraint.get("value")
    try:
        if operation in {"eq", "equals"}:
            return math.isclose(observed, _as_float(requested), rel_tol=0.0, abs_tol=1e-9)
        if operation == "gte":
            return observed >= _as_float(requested)
        if operation == "lte":
            return observed <= _as_float(requested)
        if operation == "gt":
            return observed > _as_float(requested)
        if operation == "lt":
            return observed < _as_float(requested)
        if operation == "between" and isinstance(requested, (list, tuple)) and len(requested) == 2:
            return _as_float(requested[0]) <= observed <= _as_float(requested[1])
    except (TypeError, ValueError):
        return False
    return False


def _matches(card: ArtifactCardV1, request: SearchRequestV1) -> bool:
    if request.facets:
        for axis, facet_values in request.facets.items():
            available = set(card.facets.get(axis, []))
            try:
                requested = {normalize_facet_value(axis, value) for value in facet_values}
            except ValueError:
                return False
            if not available.intersection(requested):
                return False
    if request.feature_constraints:
        features = _feature_map(card)
        if not all(
            _constraint_matches(features, constraint) for constraint in request.feature_constraints
        ):
            return False
    if request.bpm is not None:
        try:
            minimum = _as_float(card.features.get("tempo_min"))
            maximum = _as_float(card.features.get("tempo_max"))
        except (TypeError, ValueError):
            return False
        if maximum < request.bpm[0] or minimum > request.bpm[1]:
            return False
    if request.meter is not None and card.summary.get("meter") != request.meter:
        return False
    if request.required_projection_ids:
        available = set(card.projections.values()) | set(card.projections.keys())
        projection_wanted = set(request.required_projection_ids)
        if request.projection_operator == "all":
            if not projection_wanted.issubset(available):
                return False
        elif not projection_wanted.intersection(available):
            return False
    return True


def rank_candidate(card: ArtifactCardV1, request: SearchRequestV1) -> RankedCandidateV1:
    query_tokens = _tokens(request.query or "")
    card_tokens = _card_tokens(card)
    text_score = (
        len(query_tokens & card_tokens) / len(query_tokens | card_tokens)
        if query_tokens and card_tokens
        else 0.0
    )
    if request.facets:
        requested = sum(len(values) for values in request.facets.values())
        matched = 0
        for axis, values in request.facets.items():
            try:
                normalized_values = {normalize_facet_value(axis, value) for value in values}
            except ValueError:
                normalized_values = set()
            matched += len(set(card.facets.get(axis, [])) & normalized_values)
        facets_score = matched / requested if requested else 0.0
    else:
        facets_score = 0.0
    if request.feature_constraints:
        matches = sum(
            _constraint_matches(card.features, constraint)
            for constraint in request.feature_constraints
        )
        features_score = matches / len(request.feature_constraints)
    else:
        features_score = 0.0
    if request.required_projection_ids:
        available = set(card.projections.values()) | set(card.projections.keys())
        projection_score = len(available & set(request.required_projection_ids)) / len(
            request.required_projection_ids
        )
    else:
        projection_score = 0.0
    weights = _WEIGHTS if request.required_projection_ids else _NO_PROJECTION_WEIGHTS
    score = (
        weights.get("text", 0.0) * text_score
        + weights.get("facets", 0.0) * facets_score
        + weights.get("features", 0.0) * features_score
        + weights.get("projection_coverage", 0.0) * projection_score
    )
    return RankedCandidateV1(
        artifact_id=str(card.artifact_id),
        score=_quantize_nine(score),
        text_score=_quantize_nine(text_score),
        facets_score=_quantize_nine(facets_score),
        features_score=_quantize_nine(features_score),
        projection_score=_quantize_nine(projection_score),
    )


def encode_cursor(cursor: SearchCursorV1) -> str:
    payload = canonical_json(cursor.model_dump(exclude_none=True))
    checksum = hashlib.sha256(_CURSOR_DOMAIN + payload).digest()
    encoded = base64.urlsafe_b64encode(payload + checksum).decode("ascii").rstrip("=")
    if len(encoded) > 4096:
        raise GrooveCursorInvalid("cursor exceeds 4 KiB")
    return encoded


def decode_cursor(token: str) -> SearchCursorV1:
    if not isinstance(token, str) or not token or len(token) > 4096 or "=" in token:
        raise GrooveCursorInvalid("cursor encoding is not canonical")
    try:
        raw = base64.urlsafe_b64decode(token + "=" * ((4 - len(token) % 4) % 4))
        canonical_token = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
        if not hmac.compare_digest(token, canonical_token) or len(raw) <= 32:
            raise GrooveCursorInvalid("cursor encoding is invalid")
        payload, checksum = raw[:-32], raw[-32:]
        expected = hashlib.sha256(_CURSOR_DOMAIN + payload).digest()
        if not hmac.compare_digest(checksum, expected):
            raise GrooveCursorInvalid("cursor checksum mismatch")
        decoded = payload.decode("utf-8")
        parsed = json.loads(decoded)
        if not isinstance(parsed, dict) or canonical_json(parsed) != payload:
            raise GrooveCursorInvalid("cursor payload is not canonical")
        return SearchCursorV1.model_validate(parsed)
    except GrooveCursorInvalid:
        raise
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GrooveCursorInvalid("cursor is invalid") from error


def _request_hash(request: SearchRequestV1) -> str:
    return request_hash(request.model_dump(mode="json", exclude_none=True))


def search(runtime: Any, request: SearchRequestV1) -> SearchResponseV1:
    if (
        runtime.index.manifest.ranker_id != RANKER_ID
        or runtime.index.manifest.ranker_manifest_digest != RANKER_MANIFEST_DIGEST
    ):
        raise GrooveCursorRankerMismatch("runtime ranker does not match current contract")
    if (
        request.seed_bundle_id is not None
        and request.seed_bundle_id != runtime.index.manifest.seed_bundle_id
    ):
        raise GrooveCursorBundleMismatch("seed bundle does not match runtime")
    current_request_hash = _request_hash(request)
    cursor = decode_cursor(request.cursor) if request.cursor else None
    if cursor is not None:
        if cursor.request_hash != current_request_hash:
            raise GrooveCursorQueryMismatch("cursor query does not match request")
        if (
            cursor.seed_bundle_id != runtime.index.manifest.seed_bundle_id
            or cursor.logical_index_digest != runtime.index.manifest.logical_index_digest
        ):
            raise GrooveCursorBundleMismatch("cursor bundle does not match runtime")
        if (
            cursor.ranker_id != RANKER_ID
            or cursor.ranker_schema != RANKER_SCHEMA
            or cursor.ranker_manifest_digest != RANKER_MANIFEST_DIGEST
        ):
            raise GrooveCursorRankerMismatch("cursor ranker does not match runtime")
        if cursor.limit != request.limit:
            raise GrooveCursorQueryMismatch("cursor limit does not match request")
    candidates: list[RankedCandidateV1] = []
    for row in runtime.index.search_rows(request):
        artifact_id = str(row["artifact_id"])
        row_card = getattr(runtime, "card_from_search_row", None)
        card = row_card(row) if callable(row_card) else runtime.card(artifact_id)
        if _matches(card, request):
            candidates.append(rank_candidate(card, request))
    candidates.sort(key=lambda candidate: (-candidate.score, candidate.artifact_id))
    total_candidates = len(candidates)
    if cursor is not None:
        candidates = [
            candidate
            for candidate in candidates
            if candidate.score < cursor.last_score
            or (
                candidate.score == cursor.last_score
                and candidate.artifact_id > cursor.last_artifact_id
            )
        ]
    page = candidates[: request.limit]
    next_cursor: str | None = None
    if len(candidates) > len(page) and page:
        last = page[-1]
        next_cursor = encode_cursor(
            SearchCursorV1(
                seed_bundle_id=runtime.index.manifest.seed_bundle_id,
                logical_index_digest=runtime.index.manifest.logical_index_digest,
                ranker_id=RANKER_ID,
                ranker_manifest_digest=RANKER_MANIFEST_DIGEST,
                ranker_schema=RANKER_SCHEMA,
                request_hash=current_request_hash,
                limit=request.limit,
                last_score=last.score,
                last_artifact_id=last.artifact_id,
            )
        )
    cards = [runtime.card(candidate.artifact_id) for candidate in page]
    # The public ranker contract always declares all four named components.
    public_weights = dict(_WEIGHTS)
    if not request.required_projection_ids:
        public_weights = {
            "text": _NO_PROJECTION_WEIGHTS["text"],
            "facets": _NO_PROJECTION_WEIGHTS["facets"],
            "features": _NO_PROJECTION_WEIGHTS["features"],
        }
    return SearchResponseV1(
        items=cards,
        total_hint=total_candidates,
        returned_count=len(cards),
        omitted_count=max(0, len(candidates) - len(cards)),
        truncated=False,
        next_cursor=next_cursor,
        ranking=RankingV1(
            ranker_id=RANKER_ID,
            weights=public_weights,
            projection_coverage_active=bool(request.required_projection_ids),
        ),
        provenance={
            "seed_bundle_id": runtime.index.manifest.seed_bundle_id,
            "logical_index_digest": runtime.index.manifest.logical_index_digest,
        },
    )


__all__ = [
    "GrooveCursorBundleMismatch",
    "GrooveCursorInvalid",
    "GrooveCursorQueryMismatch",
    "GrooveCursorRankerMismatch",
    "decode_cursor",
    "encode_cursor",
    "rank_candidate",
    "search",
]
