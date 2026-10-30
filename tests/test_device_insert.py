"""Where ``load_device_to_track`` puts a device, and the Remote Script reads it needs.

Live keeps a chain in the order MIDI effects, one instrument, audio effects,
and refuses any other insert with "Failed to insert device"
(docs/KNOWN_BUGS.md, Category R). The server plans the index from the first
level of Live's Browser and from ``Device.type``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from ableton_mcp_server.device_insert import insert_params
from ableton_mcp_server.errors import BadInputError
from AbletonMCPServer_RemoteScript import RemoteError, execute_command
from tests.remote_fakes import FakeApplication, FakeBrowser, FakeBrowserItem, FakeDevice, FakeSong

_BROWSER = {
    "instruments": ["Instrument Rack", "Operator"],
    "midi_effects": ["Arpeggiator", "Chord"],
    "audio_effects": ["Auto Filter", "Reverb"],
}
OPERATOR = {"name": "Operator", "type": "instrument"}
ARPEGGIATOR = {"name": "Arpeggiator", "type": "midi_effect"}
REVERB = {"name": "Reverb", "type": "audio_effect"}


class _RemoteScript:
    """Answers the two reads the planner makes and records them."""

    def __init__(self, chain: list[dict[str, Any]]) -> None:
        self.chain = chain
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, command: str, params: Mapping[str, Any] | None = None) -> Any:
        params = dict(params or {})
        self.calls.append((command, params))
        if command == "search_browser":
            query = str(params["query"]).casefold()
            names = _BROWSER[params["category_type"]]
            return [{"name": name} for name in names if query in name.casefold()]
        assert command == "get_device_list"
        return list(self.chain)


@pytest.mark.parametrize(
    ("chain", "device_name", "device_index"),
    [
        ([], "Operator", 0),
        ([ARPEGGIATOR], "Operator", 1),
        ([ARPEGGIATOR, REVERB], "Operator", 1),
        ([REVERB], "Operator", 0),
        ([], "Arpeggiator", 0),
        ([OPERATOR], "Arpeggiator", 0),
        ([ARPEGGIATOR, OPERATOR, REVERB], "Chord", 1),
        ([REVERB], "Arpeggiator", 0),
        ([OPERATOR], "Reverb", 1),
        ([ARPEGGIATOR, OPERATOR, REVERB], "Auto Filter", 3),
    ],
)
def test_device_goes_where_the_chain_order_allows(
    chain: list[dict[str, Any]], device_name: str, device_index: int
) -> None:
    params = insert_params(_RemoteScript(chain), 2, device_name)

    assert params == {"track_index": 2, "device_name": device_name, "device_index": device_index}


def test_a_second_instrument_is_refused_before_the_extension_is_called() -> None:
    with pytest.raises(BadInputError, match="already holds the instrument 'Operator'") as refused:
        insert_params(_RemoteScript([ARPEGGIATOR, OPERATOR]), 0, "Instrument Rack")

    assert refused.value.code == "BAD_INPUT"


def test_the_browser_spelling_is_sent_and_the_lookup_stays_on_the_first_level() -> None:
    remote = _RemoteScript([])

    params = insert_params(remote, 0, "reverb")

    assert params["device_name"] == "Reverb"
    assert [params for command, params in remote.calls if command == "search_browser"] == [
        {"query": "reverb", "category_type": category, "limit": 200, "max_depth": 1}
        for category in ("instruments", "midi_effects", "audio_effects")
    ]


def test_a_name_the_browser_does_not_list_is_appended_as_before() -> None:
    remote = _RemoteScript([OPERATOR])

    assert insert_params(remote, 0, "Serum") == {"track_index": 0, "device_name": "Serum"}
    assert "get_device_list" not in [command for command, _params in remote.calls]


def test_a_chain_read_by_an_older_remote_script_still_gets_a_valid_index() -> None:
    # A Remote Script from before ``type`` existed: the MIDI effect goes first,
    # which Live always accepts.
    remote = _RemoteScript([{"name": "Operator"}, {"name": "Reverb"}])

    assert insert_params(remote, 0, "Arpeggiator")["device_index"] == 0


def test_get_device_list_reports_the_live_device_type() -> None:
    song = FakeSong()
    devices = [FakeDevice(name) for name in ("Arpeggiator", "Operator", "Reverb", "Odd")]
    for device, code in zip(devices, (4, 1, 2, 0), strict=True):
        device.type = code  # type: ignore[attr-defined]
    song.tracks[0].devices = devices

    result = execute_command(song, FakeApplication(), "get_device_list", {"track_index": 0})

    assert [device["type"] for device in result] == [
        "midi_effect",
        "instrument",
        "audio_effect",
        "undefined",
    ]


def test_search_browser_max_depth_stops_at_the_devices() -> None:
    preset = FakeBrowserItem("Operator Bass", uri="query:Synths#Operator:Bass", is_loadable=True)
    operator = FakeBrowserItem(
        "Operator", uri="query:Synths#Operator", is_loadable=True, children=[preset]
    )
    app = FakeApplication(browser=FakeBrowser())
    app.browser.instruments = FakeBrowserItem("Instruments", children=[operator])
    params = {"query": "operator", "category_type": "instruments"}

    shallow = execute_command(FakeSong(), app, "search_browser", {**params, "max_depth": 1})
    deep = execute_command(FakeSong(), app, "search_browser", params)

    assert [item["name"] for item in shallow] == ["Operator"]
    assert [item["name"] for item in deep] == ["Operator", "Operator Bass"]


@pytest.mark.parametrize("max_depth", [0, 6, True, "1"])
def test_search_browser_refuses_a_max_depth_outside_one_to_five(max_depth: Any) -> None:
    app = FakeApplication(browser=FakeBrowser.with_operator())

    with pytest.raises(RemoteError) as refused:
        execute_command(FakeSong(), app, "search_browser", {"query": "x", "max_depth": max_depth})

    assert refused.value.code == "INVALID_PARAMS"
