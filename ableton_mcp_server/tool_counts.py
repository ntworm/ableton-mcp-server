"""Single runtime-derived inventory for tool and acceptance surfaces."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .acceptance.probes import ACCEPTANCE_REGISTRY, AcceptanceRowV1
from .catalog import TOOL_CATALOG, ToolSpec


@dataclass(frozen=True, slots=True)
class ToolCountSnapshotV1:
    active_total: int
    headless_total: int
    live_required_total: int
    certified_total: int
    acceptance_total: int
    route_counts: Mapping[str, int]


def build_tool_count_snapshot(
    catalog: Sequence[ToolSpec] = TOOL_CATALOG,
    acceptance_registry: Sequence[AcceptanceRowV1] = ACCEPTANCE_REGISTRY,
) -> ToolCountSnapshotV1:
    catalog_names = [item.name for item in catalog]
    catalog_set = set(catalog_names)
    acceptance_names = [row.tool_name for row in acceptance_registry]
    if len(catalog_names) != len(catalog_set):
        raise ValueError("catalog must contain unique tool names")
    if len(acceptance_names) != len(set(acceptance_names)):
        raise ValueError("acceptance registry must contain unique tool names")
    if not set(acceptance_names) <= catalog_set:
        raise ValueError("acceptance registry must contain catalog tools")
    route_counts = Counter(item.route.value for item in catalog)
    headless = route_counts.get("local", 0)
    return ToolCountSnapshotV1(
        active_total=len(catalog),
        headless_total=headless,
        live_required_total=len(catalog) - headless,
        certified_total=sum(1 for row in acceptance_registry if row.certified),
        acceptance_total=len(acceptance_registry),
        route_counts=dict(sorted(route_counts.items())),
    )


__all__ = ["ToolCountSnapshotV1", "build_tool_count_snapshot"]
