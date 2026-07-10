from __future__ import annotations

import pytest

from ableton_mcp_server.ids import format_path, parse_path


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("track:2", ("track", 2, None, None, None)),
        ("track:2/device:1", ("device", 2, 1, None, None)),
        ("track:2/device:1/param:3", ("parameter", 2, 1, 3, None)),
        ("track:0/clipslot:4", ("clip_slot", 0, None, None, 4)),
        ("track:0/clipslot:4/clip", ("session_clip", 0, None, None, 4)),
        ("track:7/clip:2", ("arrangement_clip", 7, None, None, 2)),
    ],
)
def test_parse_valid_paths(path: str, expected: tuple[object, ...]) -> None:
    parsed = parse_path(path)
    actual = (
        parsed.kind,
        parsed.track_index,
        parsed.device_index,
        parsed.parameter_index,
        parsed.clip_index,
    )
    assert actual == expected
    assert str(parsed) == path


@pytest.mark.parametrize(
    "path",
    [
        "",
        "track:-1",
        "track:1/param:2",
        "track:1/device",
        "track:1/device:2/clip",
        "track:1/clipslot:2/param:1",
        "track:1/clip:2/extra",
        " track:1",
    ],
)
def test_parse_rejects_malformed_paths(path: str) -> None:
    with pytest.raises(ValueError, match="Invalid path-id"):
        parse_path(path)


def test_format_path_validates_the_result() -> None:
    assert format_path("track:2", "device:1", "param:3") == ("track:2/device:1/param:3")
    with pytest.raises(ValueError, match="Invalid path-id"):
        format_path("track:2", "param:3")
