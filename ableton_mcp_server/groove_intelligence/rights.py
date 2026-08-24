"""Conservative rights meet lattice for corpus-derived artifacts."""

from __future__ import annotations

from collections.abc import Sequence
from enum import Enum, IntEnum

from pydantic import BaseModel, ConfigDict


class RightsLevel(str, Enum):
    blocked = "blocked"
    derived_only = "derived_only"
    full = "full"


class OperationRights(IntEnum):
    blocked = 0
    derived_only = 1
    full = 2


class RightsRecordV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    level: RightsLevel = RightsLevel.blocked
    provenance_valid: bool = True


class RightsDecisionV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    level: RightsLevel
    reason: str | None = None
    capability_apply: bool = False
    capability_search: bool = False
    capability_evidence: bool = False
    capability_generate: bool = False


def _operation_level(operation: str | OperationRights) -> int:
    if isinstance(operation, OperationRights):
        return int(operation)
    return {
        "apply": int(OperationRights.full),
        "generate": int(OperationRights.derived_only),
        "search": int(OperationRights.derived_only),
        "evidence": int(OperationRights.derived_only),
        "compare": int(OperationRights.derived_only),
    }.get(operation, int(OperationRights.blocked))


def meet_rights(
    parents: Sequence[RightsRecordV1],
    operation: str | OperationRights,
    mapping_level: RightsLevel | str,
) -> RightsDecisionV1:
    if not parents or any(not parent.provenance_valid for parent in parents):
        return RightsDecisionV1(level=RightsLevel.blocked, reason="license_missing")
    levels = {RightsLevel.blocked: 0, RightsLevel.derived_only: 1, RightsLevel.full: 2}
    effective = min(
        [levels[parent.level] for parent in parents]
        + [_operation_level(operation), levels[RightsLevel(mapping_level)]]
    )
    level = [RightsLevel.blocked, RightsLevel.derived_only, RightsLevel.full][effective]
    reason = "rights_blocked" if level is RightsLevel.blocked else None
    return RightsDecisionV1(
        level=level,
        reason=reason,
        capability_apply=level is RightsLevel.full and operation == "apply",
        capability_search=level is not RightsLevel.blocked,
        capability_evidence=level is not RightsLevel.blocked,
        capability_generate=level is not RightsLevel.blocked and operation == "generate",
    )
