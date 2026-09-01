"""Family clusters as the transitive closure over the discrete dedupe layers.

Specification section 12.1 defines five layers.  Layers 1, 2, 3 and 5 are
discrete equality relations and safely form edges.  Layer 4, near-duplicate
distance, is a continuous metric: single linkage over it collapses the corpus
into one component and makes an 80/10/10 split by whole clusters impossible, so
it is a sampling filter and a published metric, never an edge.

Hierarchy alone is not enough either.  346 onset patterns and 1,030 kick/snare
skeletons were measured crossing collection boundaries, which is why the rhythm
hash is an edge in its own right.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping


class GiantComponentError(RuntimeError):
    """Clustering produced a component too large to split around."""


class _UnionFind:
    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def add(self, item: str) -> None:
        self._parent.setdefault(item, item)

    def find(self, item: str) -> str:
        root = item
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[item] != root:
            self._parent[item], item = root, self._parent[item]
        return root

    def union(self, left: str, right: str) -> None:
        left_root, right_root = self.find(left), self.find(right)
        if left_root != right_root:
            self._parent[max(left_root, right_root)] = min(left_root, right_root)


def build_clusters(
    records: Iterable[Mapping[str, str]], max_share: float
) -> dict[str, str]:
    """Map every ``source_id`` to a cluster id, refusing a giant component."""

    items = list(records)
    union = _UnionFind()
    for record in items:
        union.add(record["source_id"])

    # Layers 1, 2 and 3: identical bytes, identical canonical form, identical
    # rhythm. Layer 5, the collection, is intentionally not an edge on its own:
    # it would merge whole libraries into one component while adding nothing the
    # content hashes have not already caught.
    for key in ("byte_hash", "canonical_hash", "rhythm_hash"):
        groups: dict[str, list[str]] = defaultdict(list)
        for record in items:
            groups[record[key]].append(record["source_id"])
        for members in groups.values():
            first = members[0]
            for other in members[1:]:
                union.union(first, other)

    clusters = {record["source_id"]: union.find(record["source_id"]) for record in items}

    sizes = Counter(clusters.values())
    if items:
        largest, count = sizes.most_common(1)[0]
        if count / len(items) > max_share:
            raise GiantComponentError(
                f"largest cluster {largest} holds {count} of {len(items)} examples, "
                f"above the {max_share:.0%} ceiling; reduce the near-duplicate "
                f"threshold and regroup rather than splitting a cluster"
            )
    return clusters


def component_sizes(clusters: Mapping[str, str]) -> dict[str, int]:
    return dict(Counter(clusters.values()))
