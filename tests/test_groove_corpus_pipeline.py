from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ableton_mcp_server.groove_intelligence.artifacts import (
    FileArtifactStore,
    SeedBackedArtifactStore,
)
from ableton_mcp_server.groove_intelligence.corpus import (
    CorpusCatalog,
    InventoryRow,
    build_curated_bundle,
    curate_representatives,
)
from ableton_mcp_server.groove_intelligence.index import open_readonly_index
from tests.fixtures.groove_apply import make_drum_artifact
from tests.fixtures.groove_bundle import build_pilot_bundle
from tests.fixtures.groove_smf import MINIMAL_TYPE1_SMF, MULTI_TRACK_SMF


def test_inventory_is_relative_streaming_and_restartable(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "a.mid").write_bytes(MINIMAL_TYPE1_SMF)
    (root / "nested").mkdir()
    (root / "nested" / "b.mid").write_bytes(MULTI_TRACK_SMF)
    (root / "broken.mid").write_bytes(b"not-midi")
    catalog = CorpusCatalog(tmp_path / "catalog.sqlite", root)
    first = catalog.scan()
    second = catalog.scan()
    assert first.discovered == 3
    assert first.valid == 2 and first.failed == 1
    assert second.reused == 3 and second.processed == 0
    rows = catalog.rows()
    assert all(not Path(row.relative_path).is_absolute() for row in rows)
    assert {row.error_code for row in rows if row.status == "error"} == {"groove_midi_error"}
    with sqlite3.connect(tmp_path / "catalog.sqlite") as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE name='notes'"
        ).fetchone() == (0,)


def test_inventory_rejects_root_escape_and_retries_changed_file(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    root.mkdir()
    path = root / "take.mid"
    path.write_bytes(MINIMAL_TYPE1_SMF)
    catalog = CorpusCatalog(tmp_path / "catalog.sqlite", root)
    catalog.scan()
    path.write_bytes(MULTI_TRACK_SMF)
    result = catalog.scan()
    assert result.processed == 1 and result.reused == 0
    assert catalog.rows()[0].event_count > 0


def test_catalog_invalidates_rows_when_derivation_versions_change(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "take.mid").write_bytes(MINIMAL_TYPE1_SMF)
    db_path = tmp_path / "catalog.sqlite"
    with CorpusCatalog(db_path, root) as catalog:
        first = catalog.scan()
        assert first.processed == 1

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE meta SET value='legacy' WHERE key IN "
            "('derivation_fingerprint','projection_versions','taxonomy_version')"
        )
        connection.commit()

    with CorpusCatalog(db_path, root) as catalog:
        second = catalog.scan()
        assert second.processed == 1
        assert second.reused == 0

    with sqlite3.connect(db_path) as connection:
        keys = {row[0] for row in connection.execute("SELECT key FROM meta")}
    assert {"parser_id", "normalizer_id", "projection_versions", "taxonomy_version"} <= keys


def test_catalog_scan_publishes_current_only_after_complete_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "take.mid").write_bytes(MINIMAL_TYPE1_SMF)
    db_path = tmp_path / "catalog.sqlite"
    catalog = CorpusCatalog(db_path, root)
    original_iter_paths = catalog._iter_paths

    def interrupted_iter_paths():
        yield from original_iter_paths()
        raise RuntimeError("interrupted scan")

    monkeypatch.setattr(catalog, "_iter_paths", interrupted_iter_paths)
    with pytest.raises(RuntimeError, match="interrupted scan"):
        catalog.scan()
    with sqlite3.connect(db_path) as connection:
        metadata = dict(connection.execute("SELECT key,value FROM meta"))
    assert metadata["scan_state"] == "in_progress"
    with pytest.raises(ValueError, match="incomplete"):
        catalog.rows()
    monkeypatch.setattr(catalog, "_iter_paths", original_iter_paths)
    assert catalog.scan().processed == 1
    assert catalog.rows()[0].relative_path == "take.mid"


def test_catalog_rejects_stale_rows_and_reconciles_removed_files(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    root.mkdir()
    first_path = root / "first.mid"
    removed_path = root / "removed.mid"
    first_path.write_bytes(MINIMAL_TYPE1_SMF)
    removed_path.write_bytes(MULTI_TRACK_SMF)
    db_path = tmp_path / "catalog.sqlite"
    with CorpusCatalog(db_path, root) as catalog:
        catalog.scan()

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE meta SET value='legacy' WHERE key='derivation_fingerprint'"
        )
        connection.commit()
    with CorpusCatalog(db_path, root) as stale_catalog:
        with pytest.raises(ValueError, match="stale; scan required"):
            stale_catalog.rows()
        removed_path.unlink()
        stats = stale_catalog.scan()
        assert stats.discovered == 1
        assert [row.relative_path for row in stale_catalog.rows()] == ["first.mid"]


def test_curator_is_deterministic_diverse_and_bounded(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    root.mkdir()
    for index in range(6):
        folder = root / ("kit-a" if index % 2 else "kit-b") / f"style-{index}"
        folder.mkdir(parents=True)
        (folder / f"{index}.mid").write_bytes(
            MINIMAL_TYPE1_SMF if index % 2 else MULTI_TRACK_SMF
        )
    catalog = CorpusCatalog(tmp_path / "catalog.sqlite", root)
    catalog.scan()
    first = curate_representatives(catalog, max_files=4, max_source_bytes=10_000)
    second = curate_representatives(catalog, max_files=4, max_source_bytes=10_000)
    assert first == second
    assert len(first) == 2
    assert len({item.stratum for item in first}) >= 2


def test_curator_advances_past_oversized_candidate_within_stratum() -> None:
    def row(path: str, *, size: int, fingerprint: str, digest: str) -> InventoryRow:
        return InventoryRow(
            relative_path=path,
            file_size=size,
            mtime_ns=0,
            source_digest=digest,
            status="ok",
            error_code=None,
            error_detail=None,
            event_count=1,
            note_count=1,
            bars=1,
            stratum=path.split("/", 2)[0] + "/style",
            fingerprint=fingerprint,
            facets={},
            features={},
            hvo_digest="hvo-" + digest,
            grammar_digest="grammar-" + digest,
        )

    candidates = (
        row("kit-a/style/large.mid", size=90, fingerprint="00", digest="a" * 64),
        row("kit-a/style/small.mid", size=10, fingerprint="01", digest="b" * 64),
    )

    class StubCatalog:
        def rows(self, *, status: str | None = None) -> tuple[InventoryRow, ...]:
            assert status == "ok"
            return candidates

    selected = curate_representatives(StubCatalog(), max_files=1, max_source_bytes=25)  # type: ignore[arg-type]
    assert [item.relative_path for item in selected] == ["kit-a/style/small.mid"]
    assert sum(item.file_size for item in selected) <= 25


def test_catalog_requires_existing_directory(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="authorized corpus root"):
        CorpusCatalog(tmp_path / "catalog.sqlite", tmp_path / "missing")


def test_curated_bundle_builds_twice_without_private_paths(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "a.mid").write_bytes(MINIMAL_TYPE1_SMF)
    (root / "b.mid").write_bytes(MULTI_TRACK_SMF)
    catalog = CorpusCatalog(tmp_path / "catalog.sqlite", root)
    catalog.scan()
    result = build_curated_bundle(
        catalog,
        tmp_path / "seed",
        max_files=2,
        max_bundle_bytes=2 * 1024 * 1024,
    )
    assert result.selected_count == 2
    assert result.first_digest == result.second_digest
    assert str(root) not in (tmp_path / "seed" / "manifest.json").read_text()


def test_seed_backed_store_loads_sources_lazily_and_writes_only_derivatives(
    tmp_path: Path,
) -> None:
    bundle = build_pilot_bundle(tmp_path)
    index = open_readonly_index(bundle)
    try:
        derived = tmp_path / "derived"
        store = SeedBackedArtifactStore(index, derived)
        artifact_id = str(index.manifest.artifact_ids[0])
        assert store.contains(artifact_id)
        store.get(artifact_id)
        assert list(derived.iterdir()) == []
    finally:
        index.close()


def test_file_artifact_store_round_trips_binary_midi_payload(tmp_path: Path) -> None:
    artifact = make_drum_artifact(channels=(0,))
    store = FileArtifactStore(tmp_path / "derived")

    artifact_id = store.put(artifact)

    assert store.get(str(artifact_id)) == artifact
