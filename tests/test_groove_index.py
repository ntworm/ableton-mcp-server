from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import zlib
from collections.abc import Callable
from pathlib import Path

import pytest

from ableton_mcp_server.groove_intelligence import (
    GrooveIndexInvalid,
    GrooveIndexReadOnlyError,
    GrooveSchemaUnsupported,
)
from ableton_mcp_server.groove_intelligence.build import (
    authorize_input,
    build_seed_bundle,
    compile_one,
)
from ableton_mcp_server.groove_intelligence.canonical import (
    bundle_manifest_digest,
    canonical_json,
    manifest_digest,
)
from ableton_mcp_server.groove_intelligence.constants import (
    FEATURES_SCHEMA_VERSION,
    GRAMMAR_SCHEMA_VERSION,
    HVO_SCHEMA_VERSION,
    INDEX_SCHEMA_VERSION,
    SQLITE_USER_VERSION,
)
from ableton_mcp_server.groove_intelligence.index import (
    logical_index_digest,
    open_readonly_index,
)
from ableton_mcp_server.groove_intelligence.schema import BuildInput
from tests.fixtures.groove_bundle import build_pilot_bundle
from tests.fixtures.groove_smf import MINIMAL_TYPE1_SMF


def _rewrite_projection_json(
    bundle: Path,
    *,
    artifact_id: str,
    projection_id: str,
    mutate: Callable[[object], object],
) -> None:
    if projection_id == HVO_SCHEMA_VERSION:
        name = "hvo"
    elif projection_id == FEATURES_SCHEMA_VERSION:
        name = "features"
    else:
        name = "grammar"
    with sqlite3.connect(bundle / "index.sqlite") as connection:
        row = connection.execute(
            "SELECT blob FROM projections WHERE artifact_id=? AND name=? AND version=?",
            (artifact_id, name, projection_id),
        ).fetchone()
        assert row is not None
        original = zlib.decompress(row[0], wbits=-15)
        value = mutate(json.loads(original))
        payload = canonical_json(value)
        compressor = zlib.compressobj(wbits=-15)
        blob = compressor.compress(payload) + compressor.flush()
        connection.execute(
            "UPDATE projections SET digest=?,blob=?,raw_size=?,compressed_size=? "
            "WHERE artifact_id=? AND name=? AND version=?",
            (
                hashlib.sha256(payload).hexdigest(),
                blob,
                len(payload),
                len(blob),
                artifact_id,
                name,
                projection_id,
            ),
        )
        connection.commit()
        digest = logical_index_digest(connection)
        connection.execute(
            "UPDATE index_meta SET value=? WHERE key='logical_index_digest'", (digest,)
        )
        connection.commit()

    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["logical_index_digest"] = digest
    manifest["manifest_digest"] = manifest_digest(manifest)
    with sqlite3.connect(bundle / "index.sqlite") as connection:
        connection.execute(
            "UPDATE index_meta SET value=? WHERE key='manifest_digest'",
            (manifest["manifest_digest"],),
        )
        connection.commit()
    manifest["bundle_manifest_digest"] = bundle_manifest_digest(manifest)
    manifest["file_checksums"]["index.sqlite"] = hashlib.sha256(
        (bundle / "index.sqlite").read_bytes()
    ).hexdigest()
    manifest_path.write_bytes(canonical_json(manifest))


@pytest.mark.parametrize(
    ("projection_id", "model_type"),
    [
        (HVO_SCHEMA_VERSION, "HvoProjectionV1"),
        (FEATURES_SCHEMA_VERSION, "FeaturesProjectionV1"),
        (GRAMMAR_SCHEMA_VERSION, "GrammarProjectionV1"),
    ],
)
def test_load_projection_returns_complete_typed_v2_model(
    tmp_path: Path, projection_id: str, model_type: str
) -> None:
    bundle = build_pilot_bundle(tmp_path)
    index = open_readonly_index(bundle)
    projection = index.load_projection(str(index.manifest.artifact_ids[0]), projection_id)
    assert type(projection).__name__ == model_type


@pytest.mark.parametrize(
    "projection_id",
    [HVO_SCHEMA_VERSION, FEATURES_SCHEMA_VERSION, GRAMMAR_SCHEMA_VERSION],
)
def test_open_readonly_index_rejects_projection_with_extra_fields(
    tmp_path: Path, projection_id: str
) -> None:
    bundle = build_pilot_bundle(tmp_path)
    artifact_id = str(json.loads((bundle / "manifest.json").read_text())["artifact_ids"][0])
    _rewrite_projection_json(
        bundle,
        artifact_id=artifact_id,
        projection_id=projection_id,
        mutate=lambda value: {**value, "unexpected": True},
    )
    with pytest.raises(GrooveIndexInvalid, match="projection"):
        open_readonly_index(bundle)


@pytest.mark.parametrize(
    "projection_id",
    [HVO_SCHEMA_VERSION, FEATURES_SCHEMA_VERSION, GRAMMAR_SCHEMA_VERSION],
)
def test_open_readonly_index_rejects_projection_with_missing_fields(
    tmp_path: Path, projection_id: str
) -> None:
    bundle = build_pilot_bundle(tmp_path)
    artifact_id = str(json.loads((bundle / "manifest.json").read_text())["artifact_ids"][0])
    _rewrite_projection_json(
        bundle,
        artifact_id=artifact_id,
        projection_id=projection_id,
        mutate=lambda value: {
            key: item for key, item in value.items() if key != "source_events_digest"
        },
    )
    with pytest.raises(GrooveIndexInvalid, match="projection"):
        open_readonly_index(bundle)


@pytest.mark.parametrize(
    "projection_id",
    [HVO_SCHEMA_VERSION, FEATURES_SCHEMA_VERSION, GRAMMAR_SCHEMA_VERSION],
)
def test_open_readonly_index_rejects_projection_source_digest_mismatch(
    tmp_path: Path, projection_id: str
) -> None:
    bundle = build_pilot_bundle(tmp_path)
    artifact_id = str(json.loads((bundle / "manifest.json").read_text())["artifact_ids"][0])
    _rewrite_projection_json(
        bundle,
        artifact_id=artifact_id,
        projection_id=projection_id,
        mutate=lambda value: {**value, "source_events_digest": "0" * 64},
    )
    with pytest.raises(GrooveIndexInvalid, match="source_events_digest"):
        open_readonly_index(bundle)


def _build_nondefault_ppq_bundle(tmp_path: Path) -> Path:
    root = tmp_path / "nondefault-corpus"
    root.mkdir()
    source = root / "source.mid"
    source.write_bytes(MINIMAL_TYPE1_SMF.replace(b"\x01\xe0", b"\x03\xc0", 1))
    declared = BuildInput(
        path=source,
        source_kind="author",
        license_id="private-full",
        redistribution="full",
    )
    manifest = build_seed_bundle(
        input_root=root,
        inputs=[declared],
        output_dir=tmp_path / "bundle",
        build_config={"test": "nondefault-ppq"},
    )
    authorized, token = authorize_input(
        root,
        source,
        source_kind=declared.source_kind,
        license_id=declared.license_id,
        redistribution=declared.redistribution,
    )
    compiled = compile_one(authorized, build_id=manifest.build_id, authorized_source=token)
    from ableton_mcp_server.groove_intelligence.index import write_index

    write_index(tmp_path / "bundle", [compiled], manifest)
    return tmp_path / "bundle"


def test_index_uses_immutable_query_only_connection_and_current_schema(tmp_path: Path) -> None:
    bundle = build_pilot_bundle(tmp_path)
    index = open_readonly_index(bundle)
    assert index.user_version == SQLITE_USER_VERSION
    assert index.meta["schema_version"] == INDEX_SCHEMA_VERSION
    with pytest.raises(GrooveIndexReadOnlyError):
        index.connection.execute("CREATE TABLE forbidden(name TEXT)")
    with pytest.raises(GrooveIndexReadOnlyError):
        index.connection.executemany(
            "INSERT INTO artifacts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [],
        )
    with pytest.raises(GrooveIndexReadOnlyError):
        index.connection.execute("PRAGMA query_only = OFF")


def test_seed_reopens_after_source_directory_is_removed(tmp_path: Path) -> None:
    bundle = build_pilot_bundle(tmp_path)
    shutil.rmtree(tmp_path / "corpus")
    index = open_readonly_index(bundle)
    assert index.card_row(index.manifest.artifact_ids[0])["artifact_id"].startswith("ga1_")


def test_logical_digest_is_stable_even_when_sqlite_file_bytes_differ(tmp_path: Path) -> None:
    first = build_pilot_bundle(tmp_path / "one")
    second = build_pilot_bundle(tmp_path / "two")
    assert json.loads((first / "manifest.json").read_text())["logical_index_digest"] == json.loads(
        (second / "manifest.json").read_text()
    )["logical_index_digest"]


def test_manifest_records_index_file_checksum(tmp_path: Path) -> None:
    bundle = build_pilot_bundle(tmp_path)
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    expected = hashlib.sha256((bundle / "index.sqlite").read_bytes()).hexdigest()
    assert manifest["file_checksums"]["index.sqlite"] == expected


def test_open_readonly_index_rejects_index_byte_tamper(tmp_path: Path) -> None:
    bundle = build_pilot_bundle(tmp_path)
    index_path = bundle / "index.sqlite"
    payload = bytearray(index_path.read_bytes())
    payload[-1] ^= 1
    index_path.write_bytes(payload)
    with pytest.raises(GrooveIndexInvalid, match="checksum"):
        open_readonly_index(bundle)


def test_open_readonly_index_rejects_manifest_checksum_tamper(tmp_path: Path) -> None:
    bundle = build_pilot_bundle(tmp_path)
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["file_checksums"]["index.sqlite"] = "0" * 64
    manifest_path.write_bytes(canonical_json(manifest))
    with pytest.raises(GrooveIndexInvalid, match="checksum"):
        open_readonly_index(bundle)


def test_open_readonly_index_rejects_manifest_digest_tamper(tmp_path: Path) -> None:
    bundle = build_pilot_bundle(tmp_path)
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["manifest_digest"] = "0" * 64
    manifest_path.write_bytes(canonical_json(manifest))
    with pytest.raises(GrooveIndexInvalid, match="manifest digest"):
        open_readonly_index(bundle)


def test_open_readonly_index_rejects_bundle_manifest_digest_tamper(tmp_path: Path) -> None:
    bundle = build_pilot_bundle(tmp_path)
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["bundle_manifest_digest"] = "0" * 64
    manifest_path.write_bytes(canonical_json(manifest))
    with pytest.raises(GrooveIndexInvalid, match="bundle manifest digest"):
        open_readonly_index(bundle)


def test_open_readonly_index_rejects_sqlite_manifest_artifact_id_order_mismatch(
    tmp_path: Path,
) -> None:
    bundle = build_pilot_bundle(tmp_path)
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifact_ids"] = manifest["artifact_ids"][:1]
    manifest["manifest_digest"] = manifest_digest(manifest)
    with sqlite3.connect(bundle / "index.sqlite") as connection:
        connection.execute(
            "UPDATE index_meta SET value=? WHERE key='manifest_digest'",
            (manifest["manifest_digest"],),
        )
    manifest["file_checksums"]["index.sqlite"] = hashlib.sha256(
        (bundle / "index.sqlite").read_bytes()
    ).hexdigest()
    manifest["bundle_manifest_digest"] = bundle_manifest_digest(manifest)
    manifest_path.write_bytes(canonical_json(manifest))
    with pytest.raises(GrooveIndexInvalid, match="artifact IDs"):
        open_readonly_index(bundle)


def test_load_artifact_round_trips_real_format_timing_and_tracks(tmp_path: Path) -> None:
    bundle = _build_nondefault_ppq_bundle(tmp_path)
    index = open_readonly_index(bundle)
    try:
        artifact = index.load_artifact(str(index.manifest.artifact_ids[0]))
        assert artifact.format.smf_type == 1
        assert artifact.format.ppq == 960
        assert artifact.format.track_count == 2
        assert artifact.timing["length_ticks"] == 240
        assert artifact.timing["tempos"] == [
            {"track_index": 0, "absolute_ticks": 0, "microseconds": 500000}
        ]
        assert len(artifact.tracks) == 2
    finally:
        index.close()


def test_open_readonly_index_accepts_the_packaged_seed() -> None:
    packaged = Path(__file__).resolve().parents[1] / "ableton_mcp_server/resources/groove_seed"
    index = open_readonly_index(packaged)
    try:
        assert index.user_version == SQLITE_USER_VERSION
        assert index.meta["schema_version"] == INDEX_SCHEMA_VERSION
    finally:
        index.close()


def test_open_readonly_index_rejects_explicit_legacy_v1_fixture(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy-v1"
    legacy.mkdir()
    database = legacy / "index.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA user_version=1")
    manifest = {
        "seed_schema": "groove.seed.v1",
        "seed_bundle_id": "legacy-seed",
        "corpus_id": "legacy-corpus",
        "build_id": "legacy-build",
        "schema_version": "groove.index.v1",
        "parser_id": "legacy-parser",
        "normalizer_id": "legacy-normalizer",
        "projection_versions": {},
        "artifact_ids": [],
        "file_checksums": {
            "index.sqlite": hashlib.sha256(database.read_bytes()).hexdigest(),
        },
    }
    (legacy / "manifest.json").write_bytes(canonical_json(manifest))
    with pytest.raises(GrooveSchemaUnsupported):
        open_readonly_index(legacy)
