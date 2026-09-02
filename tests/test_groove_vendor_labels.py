from __future__ import annotations

import json

from ableton_mcp_server.groove_intelligence.vendor_labels import (
    VendorLabels,
    genre_facet,
    tempo_facet,
)


def _write(tmp_path, records: list[dict]) -> str:
    path = tmp_path / "vendor_labels.jsonl"
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")
    return str(path)


def test_missing_sidecar_is_not_an_error(tmp_path) -> None:
    labels = VendorLabels.load(str(tmp_path / "absent.jsonl"))
    assert labels.for_path("anything") == {}


def test_a_label_is_found_by_corpus_path(tmp_path) -> None:
    path = _write(tmp_path, [{"path": "a/b.mid", "genre": "Metal", "tempo": 140}])
    labels = VendorLabels.load(path)
    assert labels.for_path("a/b.mid")["genre"] == "Metal"


def test_genre_becomes_a_normalised_facet_value() -> None:
    assert genre_facet({"genre": "Pop/Rock/Country"}) == ("pop_rock_country",)
    assert genre_facet({"genre": "Metal"}) == ("metal",)
    assert genre_facet({}) == ()


def test_tempo_becomes_a_coarse_bucket_not_a_raw_number() -> None:
    # A facet is a search axis, not a measurement. The exact tempo stays in the
    # features projection; the facet is what a user can browse by.
    assert tempo_facet({"tempo": 92}) == ("bpm_80_99",)
    assert tempo_facet({"tempo": 140}) == ("bpm_140_159",)
    assert tempo_facet({}) == ()
    assert tempo_facet({"tempo": 0}) == ()
