from __future__ import annotations

from groove_lab.dataset.build import DatasetManifest, manifest_digest
from groove_lab.dataset.config import BuildConfig


def _manifest(**overrides) -> DatasetManifest:
    base = {
        "config": BuildConfig().as_dict(),
        "config_digest": BuildConfig().digest(),
        "counts": {"train": 8, "validation": 1, "test": 1},
        "cluster_sizes": {"largest": 2, "count": 5},
        "representation_loss": 0.0,
        "notes_fused_share": 0.0351,
        "expression_mass_averaged": 0.0548,
        "unresolved_note_share": 0.0648,
        "excluded_collections": ["col-x"],
        "shard_digests": {"train": "a" * 64},
        "environment": {"python": "3.10.11"},
    }
    base.update(overrides)
    return DatasetManifest(**base)


def test_manifest_digest_is_stable() -> None:
    assert manifest_digest(_manifest()) == manifest_digest(_manifest())


def test_manifest_digest_changes_with_any_content() -> None:
    assert manifest_digest(_manifest()) != manifest_digest(
        _manifest(representation_loss=0.05)
    )


def test_manifest_digest_ignores_the_environment() -> None:
    # Two machines must be able to produce the same dataset. The environment is
    # recorded for lineage, not as part of the identity of the data.
    assert manifest_digest(_manifest()) == manifest_digest(
        _manifest(environment={"python": "3.10.99"})
    )
