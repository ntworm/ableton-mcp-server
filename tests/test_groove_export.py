"""The export is the extension's whole view of the seed, so its shape is pinned."""

from __future__ import annotations

import json

from scripts.export_groove_index import build_export


def test_export_carries_facets_notes_and_timing(tmp_path) -> None:
    from tests.fixtures.groove_runtime import make_pilot_runtime

    runtime = make_pilot_runtime(tmp_path)
    export = build_export(runtime)

    assert export["schema"] == "groove.export.v1"
    assert export["grooves"], "an export with no grooves is a build failure, not an empty result"
    groove = export["grooves"][0]
    assert set(groove) == {"id", "genre", "bpm", "kit", "bars", "meter", "ppq", "notes"}
    assert isinstance(groove["ppq"], int) and groove["ppq"] > 0
    for note in groove["notes"]:
        pitch, start, duration, velocity = note
        assert 0 <= pitch <= 127
        assert start >= 0
        assert duration > 0
        assert 1 <= velocity <= 127


def test_export_is_deterministic(tmp_path) -> None:
    # The file lands in a shipped package. Two builds of one seed must not
    # produce two different bytes, or the package digest means nothing.
    from tests.fixtures.groove_runtime import make_pilot_runtime

    first = json.dumps(build_export(make_pilot_runtime(tmp_path / "a")), sort_keys=True)
    second = json.dumps(build_export(make_pilot_runtime(tmp_path / "b")), sort_keys=True)
    assert first == second


def test_export_carries_no_path_or_payload(tmp_path) -> None:
    # The seed is path-free by contract and the export must not reintroduce one.
    from tests.fixtures.groove_runtime import make_pilot_runtime

    blob = json.dumps(build_export(make_pilot_runtime(tmp_path)))
    for forbidden in ("C:\\\\", "/Users/", "payload", "blob", ".mid"):
        assert forbidden not in blob
