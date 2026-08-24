from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ableton_mcp_server.groove_intelligence.build import (
    authorize_input,
    build_seed_bundle,
    compile_one,
)
from ableton_mcp_server.groove_intelligence.constants import (
    RANKER_MANIFEST,
    RANKER_MANIFEST_DIGEST,
)
from ableton_mcp_server.groove_intelligence.index import write_index
from ableton_mcp_server.groove_intelligence.midi_lossless import parse_smf
from ableton_mcp_server.groove_intelligence.projections import derive_features, derive_hvo
from ableton_mcp_server.groove_intelligence.runtime import GrooveRuntime
from ableton_mcp_server.groove_intelligence.schema import BuildInput
from ableton_mcp_server.groove_intelligence.search import search
from ableton_mcp_server.groove_intelligence.taxonomy import classify_facets, classify_path_facets
from tests.fixtures.groove_runtime import MemoryArtifactStore
from tests.fixtures.groove_smf import MINIMAL_TYPE1_SMF


def test_relative_path_taxonomy_is_versioned_bounded_and_does_not_guess_unknown_genres() -> None:
    facets = classify_path_facets(
        "Collection One/Hip-Hop/Boom Bap/Loose Feel/Verse/kit.mid"
    )

    assert facets.version == "groove-taxonomy-v2"
    assert facets.values["collection"] == ("collection_one",)
    assert facets.values["genre"] == ("hip_hop",)
    assert facets.values["subgenre"] == ("boom_bap",)
    assert facets.values["style"] == ("loose_feel",)
    assert facets.values["section"] == ("verse",)
    assert all(
        "/" not in label and "\\" not in label
        for values in facets.values.values()
        for label in values
    )

    unknown = classify_path_facets("My Pack/Mystery Shelf/Unsorted Groove/kit.mid")
    assert "genre" not in unknown.values
    assert "subgenre" not in unknown.values
    assert set(unknown.values["source_category"]) >= {
        "mystery_shelf",
        "unsorted_groove",
    }


def test_superior_drummer_components_produce_musical_facets() -> None:
    facets = classify_path_facets(
        "Drums Groove MIDI/210@GROOVE_MONKEE_FUNK_HIP_HOP_RB/"
        "14@FUNK_SLAP/080-S061@INTRO/Variation_01.mid"
    )

    assert facets.values["collection"] == ("groove_monkee_funk_hip_hop_rb",)
    assert set(facets.values["genre"]) >= {"funk", "hip_hop", "rnb"}
    assert "intro" in facets.values["section"]
    assert "drums_groove_midi" not in facets.values.get("source_category", ())


def test_style_and_alias_tokens_are_derived_from_numbered_components() -> None:
    facets = classify_path_facets(
        "Drums Groove MIDI/05@EZX_DRUMKIT_FROM_HELL/405@STRAIGHT_4#4/"
        "080-S062@FILL_VARIATIONS/Variation_01.mid"
    )

    assert facets.values["collection"] == ("ezx_drumkit_from_hell",)
    assert "straight" in facets.values["style"]
    assert "fill" in facets.values["section"]


def test_observed_compound_genres_are_kept_distinct_from_generic_source_labels() -> None:
    facets = classify_path_facets(
        "Drums Groove MIDI/000346@PROGRESSIVE_METAL/"
        "26@METAL_(1#4)/080-S062@VERSE/Variation_01.mid"
    )

    assert "metal" in facets.values["genre"]
    assert "progressive_metal" in facets.values["subgenre"]
    assert "verse" in facets.values["section"]


def test_collection_names_with_periods_keep_the_full_relative_component() -> None:
    facets = classify_path_facets(
        "Drums Groove MIDI/00001@N.Y - AVATAR/102@STRAIGHT_4#4/"
        "076-S102@HATS_CLOSED_VARIATIONS/Variation_01.mid"
    )

    assert facets.values["collection"] == ("n_y_avatar",)


def test_taxonomy_uses_token_boundaries_for_musical_labels() -> None:
    facets = classify_path_facets("Pack/Rockstar/Metallic/Unknown-Groove/kit.mid")

    assert "rock" not in facets.values.get("genre", ())
    assert "metal" not in facets.values.get("genre", ())
    assert "groove" not in facets.values.get("section", ())


def test_ranker_manifest_digest_covers_taxonomy_contract() -> None:
    assert RANKER_MANIFEST["taxonomy"]["version"] == "groove-taxonomy-v2"
    assert RANKER_MANIFEST["taxonomy"]["aliases"]
    assert RANKER_MANIFEST["taxonomy"]["tokenizer"]
    expected = hashlib.sha256(
        json.dumps(RANKER_MANIFEST, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    assert expected == RANKER_MANIFEST_DIGEST


def test_license_facet_tracks_real_redistribution_without_masking_blocked() -> None:
    parsed = parse_smf(MINIMAL_TYPE1_SMF)
    hvo = derive_hvo(parsed)
    features = derive_features(parsed, hvo)

    for redistribution in ("full", "derived_only", "blocked"):
        facets = classify_facets(features, hvo, redistribution=redistribution)
        assert facets.values["license"] == (redistribution,)


def test_build_taxonomy_is_searchable_by_facet_and_free_text_without_private_path(
    tmp_path: Path,
) -> None:
    root = tmp_path / "private-corpus"
    source = root / "Collection One" / "Hip-Hop" / "Boom Bap" / "Loose Feel" / "Verse" / "kit.mid"
    source.parent.mkdir(parents=True)
    source.write_bytes(MINIMAL_TYPE1_SMF)
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
        build_config={"taxonomy": "v2"},
    )
    authorized, token = authorize_input(
        root,
        source,
        source_kind=declared.source_kind,
        license_id=declared.license_id,
        redistribution=declared.redistribution,
    )
    compiled = compile_one(authorized, build_id=manifest.build_id, authorized_source=token)
    assert str(root) not in str(compiled.summary)
    assert str(root) not in str(compiled.facets)
    assert {row["axis"] for row in compiled.facets} >= {
        "collection",
        "genre",
        "subgenre",
        "style",
        "section",
    }

    write_index(tmp_path / "bundle", [compiled], manifest)
    from ableton_mcp_server.groove_intelligence.index import open_readonly_index

    index = open_readonly_index(tmp_path / "bundle")
    store = MemoryArtifactStore()
    store.put(index.load_artifact(str(manifest.artifact_ids[0])))
    runtime = GrooveRuntime(index=index, store=store)
    try:
        facet_result = search(
            runtime,
            _request(facets={"genre": ["Hip-Hop"]}),
        )
        text_result = search(runtime, _request(query="boom bap"))
        assert len(facet_result.items) == 1
        assert len(text_result.items) == 1
        assert facet_result.items[0].facets["section"] == ["verse"]
        assert str(root) not in facet_result.items[0].model_dump_json()
    finally:
        runtime.close()


def test_duplicate_payloads_union_supported_taxonomy_without_duplicate_artifact(
    tmp_path: Path,
) -> None:
    root = tmp_path / "private-corpus"
    rock = root / "A" / "Rock" / "kit.mid"
    hip_hop = root / "B" / "Hip-Hop" / "kit.mid"
    rock.parent.mkdir(parents=True)
    hip_hop.parent.mkdir(parents=True)
    rock.write_bytes(MINIMAL_TYPE1_SMF)
    hip_hop.write_bytes(MINIMAL_TYPE1_SMF)
    declarations = [
        BuildInput(
            path=rock,
            source_kind="author",
            license_id="private-full",
            redistribution="full",
        ),
        BuildInput(
            path=hip_hop,
            source_kind="author",
            license_id="private-full",
            redistribution="full",
        ),
    ]
    manifest = build_seed_bundle(
        input_root=root,
        inputs=declarations,
        output_dir=tmp_path / "bundle",
        build_config={"taxonomy": "v2"},
    )
    assert len(manifest.artifact_ids) == 1
    from ableton_mcp_server.groove_intelligence.index import open_readonly_index

    index = open_readonly_index(tmp_path / "bundle")
    try:
        row = next(
            item
            for item in index.search_rows(None)
            if item["artifact_id"] == str(manifest.artifact_ids[0])
        )
        genres = {
            str(item["value"])
            for item in row["facets"]
            if item["axis"] == "genre"
        }
        assert genres >= {"rock", "hip_hop"}
    finally:
        index.close()


def _request(**values: object):
    from ableton_mcp_server.groove_intelligence.mcp_models import SearchRequestV1

    return SearchRequestV1(schema_version="groove.search.request.v1", limit=20, **values)
