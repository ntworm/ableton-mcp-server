from __future__ import annotations

from pathlib import Path

import pytest

from ableton_mcp_server.groove_intelligence import GrooveBuildError
from ableton_mcp_server.groove_intelligence.build import (
    authorize_input,
    build_seed_bundle,
    compile_one,
)
from ableton_mcp_server.groove_intelligence.schema import BuildInput
from tests.fixtures.groove_smf import MINIMAL_TYPE1_SMF, MULTI_TRACK_SMF


def test_pilot_build_is_path_free_and_sorted_by_source_digest(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "z.mid").write_bytes(MINIMAL_TYPE1_SMF)
    (root / "a.mid").write_bytes(MULTI_TRACK_SMF)
    manifest = build_seed_bundle(
        input_root=root,
        inputs=[
            BuildInput(
                path=root / "z.mid",
                source_kind="author",
                license_id="private-full",
                redistribution="full",
            ),
            BuildInput(
                path=root / "a.mid",
                source_kind="author",
                license_id="private-derived",
                redistribution="derived_only",
            ),
        ],
        output_dir=tmp_path / "bundle",
        build_config={"pilot": "v1"},
    )
    text = (tmp_path / "bundle" / "manifest.json").read_text(encoding="utf-8")
    assert str(root) not in text and "z.mid" not in text and "a.mid" not in text
    assert [item.source_digest for item in manifest.inputs] == sorted(
        item.source_digest for item in manifest.inputs
    )


def test_compile_propagates_redistribution_to_license_facet(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    root.mkdir()
    source = root / "derived.mid"
    source.write_bytes(MINIMAL_TYPE1_SMF)
    declared = BuildInput(
        path=source,
        source_kind="author",
        license_id="private-derived",
        redistribution="derived_only",
    )
    authorized, token = authorize_input(
        root,
        source,
        source_kind=declared.source_kind,
        license_id=declared.license_id,
        redistribution=declared.redistribution,
    )

    compiled = compile_one(authorized, build_id="b1", authorized_source=token)

    assert [row["value"] for row in compiled.facets if row["axis"] == "license"] == [
        "derived_only"
    ]


def test_build_rejects_symlink_escape_and_external_valid_midi_at_root_boundary(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.mid"
    outside.write_bytes(MINIMAL_TYPE1_SMF)
    (root / "inside.mid").write_bytes(MINIMAL_TYPE1_SMF)
    try:
        (root / "escape.mid").symlink_to(outside)
    except OSError as error:
        pytest.skip(f"symlink fixture unavailable: {error}")
    with pytest.raises(GrooveBuildError, match="escapes authorized root"):
        authorize_input(
            root,
            root / "escape.mid",
            source_kind="author",
            license_id="private-full",
            redistribution="full",
        )
    with pytest.raises(GrooveBuildError, match="authorized root"):
        authorize_input(
            root,
            outside,
            source_kind="author",
            license_id="private-full",
            redistribution="full",
        )
    valid_input, token = authorize_input(
        root,
        root / "inside.mid",
        source_kind="author",
        license_id="private-full",
        redistribution="full",
    )
    with pytest.raises(GrooveBuildError, match="authorized root"):
        compile_one(
            BuildInput(
                path=outside,
                source_kind="author",
                license_id="private-full",
                redistribution="full",
            ),
            build_id="b1",
            authorized_source=token,
        )
    with pytest.raises(GrooveBuildError, match="license"):
        compile_one(
            valid_input.model_copy(update={"license_id": "", "redistribution": "blocked"}),
            build_id="b1",
            authorized_source=token,
        )
