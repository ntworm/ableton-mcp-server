from __future__ import annotations

from ableton_mcp_server.music_brain import (
    Traits,
    generate_bass,
    generate_drum_groove,
    plan_production,
)

KICK = 36
SNARE = 38
CLOSED_HAT = 42
PEDAL_HAT = 44
OPEN_HAT = 46


def _pitches(notes: list[dict[str, object]]) -> set[object]:
    return {note["pitch"] for note in notes}


def test_drum_groove_repeats_exactly_for_the_same_seed() -> None:
    assert (
        generate_drum_groove(bars=2, seed=7).notes
        == generate_drum_groove(bars=2, seed=7).notes
    )


def test_drum_groove_differs_between_seeds() -> None:
    """The parked prototype ignored ``seed`` entirely; this pins that it cannot."""
    assert (
        generate_drum_groove(bars=4, seed=1).notes
        != generate_drum_groove(bars=4, seed=2).notes
    )


def test_drum_groove_covers_every_requested_bar() -> None:
    notes = generate_drum_groove(bars=3, seed=1).notes
    assert max(float(note["start_time"]) for note in notes) < 12.0
    assert {int(float(note["start_time"]) // 4) for note in notes} == {0, 1, 2}


def test_base_palette_is_kick_snare_and_closed_hat() -> None:
    """With every trait at zero the kit stays small and the backbeat exists,
    because ``groove`` has to have something to accent."""
    notes = generate_drum_groove(bars=2, seed=1).notes
    assert _pitches(notes) == {KICK, SNARE, CLOSED_HAT}


def test_snare_lands_on_the_backbeat() -> None:
    notes = generate_drum_groove(bars=1, seed=1).notes
    snares = sorted(float(n["start_time"]) for n in notes if n["pitch"] == SNARE)
    assert snares == [1.0, 3.0]


def test_full_electro_opens_the_hat_palette() -> None:
    notes = generate_drum_groove(bars=2, seed=1, traits=Traits(electro=1.0)).notes
    assert {OPEN_HAT, PEDAL_HAT} <= _pitches(notes)


def test_bass_stays_inside_the_requested_root_pitch_class() -> None:
    notes = generate_bass(bars=4, seed=3, root_midi=40).notes
    assert {int(note["pitch"]) % 12 for note in notes} == {40 % 12}


def test_bass_differs_between_seeds() -> None:
    assert (
        generate_bass(bars=4, seed=1, root_midi=36).notes
        != generate_bass(bars=4, seed=2, root_midi=36).notes
    )


def test_bass_never_leaves_the_midi_range() -> None:
    notes = generate_bass(bars=8, seed=11, root_midi=127).notes
    assert all(0 <= int(note["pitch"]) <= 127 for note in notes)


def test_plan_reads_a_tempo_written_in_the_prompt() -> None:
    plan = plan_production(prompt="something slow at 96 bpm", bars=None, bpm=None)
    assert plan["bpm"] == 96.0


def test_explicit_bpm_beats_the_prompt() -> None:
    plan = plan_production(prompt="at 96 bpm", bars=None, bpm=128.0)
    assert plan["bpm"] == 128.0


def test_plan_sections_tile_the_whole_arrangement() -> None:
    plan = plan_production(prompt="a track", bars=64, bpm=None)
    sections = plan["sections"]
    assert sections[0]["start_bar"] == 0
    for earlier, later in zip(sections, sections[1:], strict=False):
        assert earlier["start_bar"] + earlier["length_bars"] == later["start_bar"]
    assert sections[-1]["start_bar"] + sections[-1]["length_bars"] == 64


def test_plan_reports_what_it_could_not_resolve_instead_of_inventing() -> None:
    plan = plan_production(prompt="a track", bars=None, bpm=None)
    assert plan["bpm"] is None
    assert "bpm" in plan["unresolved"]
    assert "bars" in plan["unresolved"]


def test_space_removes_notes() -> None:
    dense = generate_drum_groove(bars=4, seed=2).notes
    sparse = generate_drum_groove(bars=4, seed=2, traits=Traits(space=0.8)).notes
    assert len(sparse) < len(dense)


def test_space_lengthens_what_survives() -> None:
    """Every drum note starts at 0.25 beats, so full space must triple it."""
    notes = generate_drum_groove(bars=4, seed=2, traits=Traits(space=1.0)).notes
    assert notes
    assert {round(float(note["duration"]), 6) for note in notes} == {0.75}


def test_space_never_empties_the_pattern() -> None:
    assert generate_drum_groove(bars=1, seed=9, traits=Traits(space=1.0)).notes


def test_weirdness_adds_ghost_notes() -> None:
    plain = generate_drum_groove(bars=4, seed=4).notes
    weird = generate_drum_groove(bars=4, seed=4, traits=Traits(weirdness=1.0)).notes
    assert not [n for n in plain if int(n["velocity"]) <= 45]
    assert [n for n in weird if int(n["velocity"]) <= 45]


def test_weirdness_pushes_notes_off_the_grid() -> None:
    weird = generate_drum_groove(bars=4, seed=4, traits=Traits(weirdness=1.0)).notes
    assert any(round(float(n["start_time"]) * 4, 6) % 1 for n in weird)


def test_weirdness_stays_inside_the_requested_bars() -> None:
    weird = generate_drum_groove(bars=2, seed=4, traits=Traits(weirdness=1.0)).notes
    assert all(0.0 <= float(n["start_time"]) < 8.0 for n in weird)


def test_weirdness_leaps_octaves_without_leaving_the_root() -> None:
    weird = generate_bass(
        bars=8, seed=4, root_midi=36, traits=Traits(weirdness=1.0)
    ).notes
    assert len({int(n["pitch"]) for n in weird}) > 1
    assert {int(n["pitch"]) % 12 for n in weird} == {36 % 12}
    assert all(0 <= int(n["pitch"]) <= 127 for n in weird)


def test_groove_neither_adds_nor_removes_notes() -> None:
    """``groove`` owns timing and accent only, so the note set must survive."""
    straight = generate_drum_groove(bars=2, seed=6, traits=Traits(electro=0.5)).notes
    swung = generate_drum_groove(
        bars=2, seed=6, traits=Traits(electro=0.5, groove=1.0)
    ).notes
    assert len(swung) == len(straight)
    assert sorted(int(n["pitch"]) for n in swung) == sorted(
        int(n["pitch"]) for n in straight
    )


def test_groove_delays_the_offbeat() -> None:
    straight = generate_drum_groove(bars=1, seed=6, traits=Traits(electro=0.5)).notes
    swung = generate_drum_groove(
        bars=1, seed=6, traits=Traits(electro=0.5, groove=1.0)
    ).notes

    def offbeats(notes: list[dict[str, object]]) -> list[float]:
        return sorted(
            float(n["start_time"]) for n in notes if float(n["start_time"]) % 1.0
        )

    assert offbeats(swung) != offbeats(straight)
    assert all(
        late > early
        for late, early in zip(offbeats(swung), offbeats(straight), strict=True)
    )


def test_groove_accents_the_backbeat() -> None:
    def backbeat_velocity(groove: float) -> int:
        notes = generate_drum_groove(
            bars=1, seed=6, traits=Traits(groove=groove)
        ).notes
        return max(int(n["velocity"]) for n in notes if float(n["start_time"]) == 1.0)

    assert backbeat_velocity(1.0) > backbeat_velocity(0.0)


def test_velocity_never_leaves_the_midi_range() -> None:
    notes = generate_drum_groove(
        bars=4, seed=6, traits=Traits(groove=1.0, electro=1.0, weirdness=1.0)
    ).notes
    assert all(1 <= int(n["velocity"]) <= 127 for n in notes)


def test_no_traits_reports_nothing_applied() -> None:
    assert generate_drum_groove(bars=2, seed=8).traits_applied == []


def test_traits_applied_names_only_what_changed_the_output() -> None:
    applied = generate_drum_groove(
        bars=2, seed=8, traits=Traits(space=0.8, groove=1.0)
    ).traits_applied
    assert set(applied) == {"space", "groove"}


def test_a_trait_too_weak_to_change_the_grid_is_not_reported() -> None:
    """``electro`` is quantised into three grid levels; below the first
    threshold it selects the same grid as zero and must not claim credit."""
    generation = generate_drum_groove(bars=2, seed=8, traits=Traits(electro=0.2))
    assert "electro" not in generation.traits_applied


def test_traits_applied_follows_the_pipeline_order() -> None:
    applied = generate_drum_groove(
        bars=2,
        seed=8,
        traits=Traits(groove=1.0, electro=1.0, weirdness=1.0, space=0.5),
    ).traits_applied
    assert applied == ["electro", "space", "weirdness", "groove"]
