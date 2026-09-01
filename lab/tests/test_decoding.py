from __future__ import annotations

import numpy as np

from groove_lab.decoding import DecodeState, commit_confident_cells, schedule

STEPS = 32
LANES = 18


def test_schedule_commits_everything_and_never_stalls() -> None:
    for total_steps in (1, 2, 4, 8, 16):
        counts = schedule(STEPS * LANES, total_steps)
        assert len(counts) == total_steps
        assert sum(counts) == STEPS * LANES
        assert all(count >= 1 for count in counts)


def test_state_starts_fully_masked() -> None:
    state = DecodeState.masked(STEPS, LANES)
    assert state.observed_mask.sum() == 0
    assert state.hit.shape == (STEPS, LANES)


def test_locked_lanes_are_observed_from_the_start_and_never_overwritten() -> None:
    state = DecodeState.masked(STEPS, LANES)
    state.lock_lane(4, hits=np.ones(STEPS, dtype=np.float32))
    assert state.observed_mask[:, 4].all()

    logits = np.full((STEPS, LANES), 10.0, dtype=np.float32)
    velocity = np.full((STEPS, LANES), 0.5, dtype=np.float32)
    offset = np.zeros((STEPS, LANES), dtype=np.float32)
    commit_confident_cells(state, logits, velocity, offset, count=STEPS * LANES)

    assert state.hit[:, 4].tolist() == [1.0] * STEPS


def test_commit_marks_exactly_the_requested_number_of_cells() -> None:
    state = DecodeState.masked(STEPS, LANES)
    rng = np.random.default_rng(0)
    logits = rng.normal(size=(STEPS, LANES)).astype(np.float32)
    velocity = np.zeros((STEPS, LANES), dtype=np.float32)
    offset = np.zeros((STEPS, LANES), dtype=np.float32)

    before = int(state.observed_mask.sum())
    commit_confident_cells(state, logits, velocity, offset, count=10)
    after = int(state.observed_mask.sum())
    assert after - before == 10


def test_full_decode_observes_every_cell() -> None:
    state = DecodeState.masked(STEPS, LANES)
    rng = np.random.default_rng(1)
    for count in schedule(STEPS * LANES, 8):
        logits = rng.normal(size=(STEPS, LANES)).astype(np.float32)
        zeros = np.zeros((STEPS, LANES), dtype=np.float32)
        commit_confident_cells(state, logits, zeros, zeros, count=count)
    assert state.observed_mask.all()
