"""Instrument comprehension and authoring shorthands.

These tools exist because an agent that cannot see inside a rack, cannot tell
which device owns a parameter name, and cannot read an envelope back is
composing blind — and because shipping one note cell beats shipping the two
hundred notes it expands into.
"""

from __future__ import annotations

import pytest

from AbletonMCPServer_RemoteScript import RemoteError, execute_command
from tests.remote_fakes import FakeApplication, FakeDevice, FakeParameter, FakeSong


class FakeChain:
    def __init__(self, name: str, volume: float, devices: list[FakeDevice]) -> None:
        self.name = name
        self.devices = devices
        self.mute = False
        self.solo = False
        self.mixer_device = type(
            "ChainMixer",
            (),
            {"volume": FakeParameter("Volume", volume), "panning": FakeParameter("Pan", 0.0)},
        )()


class FakeRack(FakeDevice):
    def __init__(
        self, name: str = "Instrument Rack", chains: list[FakeChain] | None = None
    ) -> None:
        super().__init__(name)
        self.class_name = "InstrumentGroupDevice"
        self.parameters = [FakeParameter("Device On", 1.0)] + [
            FakeParameter(f"Macro {index}", 0.0) for index in range(1, 9)
        ]
        self.chains = chains if chains is not None else []


class FakeNoteLength(FakeDevice):
    def __init__(self) -> None:
        super().__init__("Note Length")
        self.class_name = "MidiNoteLength"
        self.parameters = [
            FakeParameter("Sync On", 0.0),
            FakeParameter("Time Length", 0.14),
            FakeParameter("Gate", 130.0, 1.0, 200.0),
        ]


class SampledEnvelope:
    """Mirrors the LOM: only ``value_at_time`` exists, never a breakpoint list."""

    def __init__(self, ramp_end: float = 32.0) -> None:
        self.ramp_end = ramp_end

    def value_at_time(self, time: float) -> float:
        return min(1.0, time / self.ramp_end)


def test_get_device_chains_exposes_what_the_device_list_hides() -> None:
    song = FakeSong()
    rack = FakeRack(chains=[FakeChain("nylon", 0.7, [FakeDevice("Kontakt 8")])])
    song.tracks[0].devices = [rack]

    result = execute_command(
        song, FakeApplication(), "get_device_chains", {"track_index": 0, "device_index": 0}
    )

    assert result["chain_count"] == 1
    chain = result["chains"][0]
    assert chain["name"] == "nylon"
    assert chain["volume"] == 0.7
    assert chain["devices"][0]["name"] == "Kontakt 8"


def test_get_device_chains_refuses_a_device_without_chains() -> None:
    song = FakeSong()

    with pytest.raises(RemoteError) as error:
        execute_command(
            song, FakeApplication(), "get_device_chains", {"track_index": 0, "device_index": 0}
        )

    assert error.value.code == "WRONG_TYPE"


def test_midi_chain_report_names_the_device_that_overrides_durations() -> None:
    song = FakeSong()
    song.tracks[0].devices = [FakeNoteLength(), FakeDevice("Operator")]

    result = execute_command(song, FakeApplication(), "get_midi_chain_report", {"track_index": 0})

    assert result["rewrites_input"] is True
    finding = result["devices"][0]
    assert finding["class_name"] == "MidiNoteLength"
    assert "Time Length" in finding["consequence"]
    assert finding["values"]["Time Length"] == 0.14


def test_midi_chain_report_walks_into_rack_chains() -> None:
    """The Velocity device that caps a drum track hides inside a rack chain."""

    song = FakeSong()
    hidden = FakeNoteLength()
    rack = FakeRack("MIDI Effect Rack", chains=[FakeChain("Velocity", 0.85, [hidden])])
    song.tracks[0].devices = [rack]

    result = execute_command(song, FakeApplication(), "get_midi_chain_report", {"track_index": 0})

    assert result["rewrites_input"] is True
    finding = result["devices"][0]
    assert finding["path"] == "track:0/device:0/chain:0/device:0"
    assert finding["chain_name"] == "Velocity"
    assert finding["values"]["Time Length"] == 0.14


def test_describe_instrument_asks_for_the_macro_mapping_it_needs() -> None:
    song = FakeSong()
    song.tracks[0].devices = [FakeRack()]

    result = execute_command(song, FakeApplication(), "describe_instrument", {"track_index": 0})

    assert result["has_instrument"] is True
    assert result["class_name"] == "InstrumentGroupDevice"
    assert any("rename" in request for request in result["setup_requests"])


def test_describe_instrument_reports_a_track_with_no_instrument() -> None:
    song = FakeSong()
    song.tracks[0].devices = [FakeNoteLength()]

    result = execute_command(song, FakeApplication(), "describe_instrument", {"track_index": 0})

    assert result["has_instrument"] is False
    assert result["setup_requests"]


def test_ambiguous_parameter_name_is_refused_instead_of_guessed() -> None:
    song = FakeSong()
    song.tracks[0].devices = [FakeRack("MIDI Effect Rack"), FakeRack("Instrument Rack")]

    with pytest.raises(RemoteError) as error:
        execute_command(
            song,
            FakeApplication(),
            "create_clip_automation",
            {
                "track_index": 0,
                "clip_index": 0,
                "parameter_name": "Macro 1",
                "automation_points": [{"time": 0.0, "value": 1.0}],
            },
        )

    assert error.value.code == "AMBIGUOUS_MATCH"
    assert error.value.details == {"candidates": [0, 1]}


def test_device_index_resolves_the_ambiguity() -> None:
    song = FakeSong()
    song.tracks[0].devices = [FakeRack("MIDI Effect Rack"), FakeRack("Instrument Rack")]

    result = execute_command(
        song,
        FakeApplication(),
        "create_clip_automation",
        {
            "track_index": 0,
            "clip_index": 0,
            "parameter_name": "Macro 1",
            "automation_points": [{"time": 0.0, "value": 1.0}],
            "device_index": 1,
        },
    )

    assert result["points_written"] == 1


def test_clip_automation_curve_expands_control_points_into_contiguous_steps() -> None:
    song = FakeSong()

    result = execute_command(
        song,
        FakeApplication(),
        "create_clip_automation_curve",
        {
            "track_index": 0,
            "clip_index": 0,
            "parameter_name": "Filter Freq",
            "control_points": [{"time": 0.0, "value": 0.0}, {"time": 2.0, "value": 1.0}],
            "shape": "linear",
            "resolution": 0.5,
        },
    )

    assert result["control_points"] == 2
    assert result["points_written"] == 5  # four steps plus the closing point
    clip = song.tracks[0].clip_slots[0].clip
    parameter = song.tracks[0].devices[0].parameters[1]
    steps = clip.automation_envelope(parameter).steps
    # every step reaches the next one: no gap means no comb
    assert steps[0][1] == pytest.approx(0.5)
    assert [round(value, 3) for _, _, value in steps] == [0.0, 0.25, 0.5, 0.75, 1.0]


def test_clip_automation_curve_refuses_an_expansion_beyond_the_step_budget() -> None:
    song = FakeSong()

    with pytest.raises(RemoteError) as error:
        execute_command(
            song,
            FakeApplication(),
            "create_clip_automation_curve",
            {
                "track_index": 0,
                "clip_index": 0,
                "parameter_name": "Filter Freq",
                "control_points": [{"time": 0.0, "value": 0.0}, {"time": 600.0, "value": 1.0}],
                "resolution": 0.25,
            },
        )

    assert error.value.code == "BAD_INPUT"
    assert "resolution" in str(error.value)


def test_add_notes_pattern_repeats_the_cell_with_transposition() -> None:
    song = FakeSong()

    result = execute_command(
        song,
        FakeApplication(),
        "add_notes_pattern",
        {
            "track_index": 0,
            "clip_index": 0,
            "cell": [
                {"pitch": 60, "start_time": 0.0, "duration": 0.25, "velocity": 90},
                {"pitch": 64, "start_time": 0.5, "duration": 0.25, "velocity": 70},
            ],
            "cell_length": 1.0,
            "repeats": 3,
            "transpose_per_repeat": 2,
        },
    )

    assert result["added"] == 6
    assert result["repeats"] == 3
    written = song.tracks[0].clip_slots[0].clip.add_payloads[-1]
    pitches = [note.pitch for note in written]
    starts = [round(note.start_time, 3) for note in written]
    assert pitches == [60, 64, 62, 66, 64, 68]
    assert starts == [0.0, 0.5, 1.0, 1.5, 2.0, 2.5]


def test_get_clip_automation_samples_the_envelope() -> None:
    song = FakeSong()
    clip = song.tracks[0].clip_slots[0].clip
    clip.length = 4.0
    parameter = song.tracks[0].devices[0].parameters[1]
    clip._automation_envelopes[parameter] = SampledEnvelope(ramp_end=4.0)

    result = execute_command(
        song,
        FakeApplication(),
        "get_clip_automation",
        {
            "track_index": 0,
            "clip_index": 0,
            "parameter_name": "Filter Freq",
            "resolution": 1.0,
        },
    )

    assert result["has_envelope"] is True
    assert result["sample_count"] == 4
    assert [sample["value"] for sample in result["samples"]] == [0.0, 0.25, 0.5, 0.75]


def test_parameter_write_reaches_a_device_inside_a_rack_chain() -> None:
    """The control that caps a drum track's dynamics lives one level down."""

    song = FakeSong()
    nested = FakeNoteLength()
    rack = FakeRack("MIDI Effect Rack", chains=[FakeChain("Velocity", 0.85, [nested])])
    song.tracks[0].devices = [rack]

    result = execute_command(
        song,
        FakeApplication(),
        "set_parameter_value",
        {
            "track_index": 0,
            "device_index": 0,
            "chain_index": 0,
            "chain_device_index": 0,
            "parameter_name": "Time Length",
            "value": 0.4,
        },
    )

    assert result["value"] == pytest.approx(0.4)
    assert result["resolved"]["chain_index"] == 0
    assert result["resolved"]["chain_device_index"] == 0
    assert nested.parameters[1].value == pytest.approx(0.4)


def test_chain_mixer_volume_is_addressable_without_an_inner_device() -> None:
    song = FakeSong()
    chain = FakeChain("nylon", 0.7, [FakeDevice("Kontakt 8")])
    song.tracks[0].devices = [FakeRack(chains=[chain])]

    result = execute_command(
        song,
        FakeApplication(),
        "set_parameter_value",
        {
            "track_index": 0,
            "device_index": 0,
            "chain_index": 0,
            "parameter_name": "volume",
            "value": 0.35,
        },
    )

    assert result["value"] == pytest.approx(0.35)
    assert chain.mixer_device.volume.value == pytest.approx(0.35)


def test_chain_mixer_refuses_a_parameter_it_does_not_own() -> None:
    song = FakeSong()
    song.tracks[0].devices = [FakeRack(chains=[FakeChain("nylon", 0.7, [])])]

    with pytest.raises(RemoteError) as error:
        execute_command(
            song,
            FakeApplication(),
            "get_parameter_value",
            {
                "track_index": 0,
                "device_index": 0,
                "chain_index": 0,
                "parameter_name": "Cutoff",
            },
        )

    assert error.value.code == "INVALID_PARAMS"
    assert "chain_device_index" in str(error.value)
