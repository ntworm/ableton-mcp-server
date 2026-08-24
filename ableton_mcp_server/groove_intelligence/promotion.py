"""Canonical, lab-only signatures for provider promotion decisions."""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Mapping
from typing import Any

from .canonical import canonical_json
from .gates import GateThresholdsV1


class HmacPromotionSigner:
    """A caller-supplied lab key; no key material is serialized into reports."""

    def __init__(self, key: bytes, *, key_id: str = "lab-fixture-v1") -> None:
        if not key or len(key) < 16:
            raise ValueError("promotion key is too short")
        if not key_id or len(key_id) > 64:
            raise ValueError("promotion key id is invalid")
        self._key = bytes(key)
        self.key_id = key_id

    def sign(self, digest: str) -> str:
        return hmac.new(self._key, digest.encode("ascii"), hashlib.sha256).hexdigest()

    def verify(self, digest: str, signature: str, key_id: str) -> bool:
        if key_id != self.key_id or len(signature) != 64:
            return False
        try:
            expected = self.sign(digest)
        except (UnicodeEncodeError, ValueError):
            return False
        return hmac.compare_digest(expected, signature)


def canonical_promotion_payload(report: object) -> bytes:
    """Serialize report identity while excluding mutable digest/signature fields."""

    if hasattr(report, "model_dump"):
        model: Any = report
        value = model.model_dump(mode="json")
    elif isinstance(report, Mapping):
        value = dict(report)
    else:
        raise TypeError("report must be a model or mapping")
    value.pop("payload_digest", None)
    value.pop("signature", None)
    return canonical_json(value)


def report_digest(report: object) -> str:
    return hashlib.sha256(
        b"ABLETON-GROOVE-PROMOTION-V1\x00" + canonical_promotion_payload(report)
    ).hexdigest()


def promotion_allowed(report: object, signer: HmacPromotionSigner) -> bool:
    """Verify every stored promotion fact before enabling a provider."""

    try:
        model: Any = report
        if model.schema_version != "groove.provider-gate.v1":
            return False
        if not bool(model.registry_opt_in):
            return False
        if model.thresholds != GateThresholdsV1():
            return False
        gates = model.gates
        if not isinstance(gates, Mapping) or set(gates) != {
            "contract",
            "fallback",
            "reproducibility",
            "quality",
            "privacy_license",
            "cost_latency",
        }:
            return False
        failed = tuple(
            sorted(name for name, gate in gates.items() if gate.status != "passed")
        )
        if tuple(model.failed_gates) != failed:
            return False
        if bool(model.promotion_allowed) != (not failed):
            return False
        digest = model.payload_digest
        signature = model.signature
        if digest != report_digest(report):
            return False
        if not signer.verify(digest, signature, model.signing_key_id):
            return False
        return not failed
    except (AttributeError, TypeError, ValueError, KeyError):
        return False


__all__ = [
    "HmacPromotionSigner",
    "canonical_promotion_payload",
    "promotion_allowed",
    "report_digest",
]
