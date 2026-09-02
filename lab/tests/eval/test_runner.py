from __future__ import annotations

import numpy as np

from groove_lab.eval.runner import EvaluationCase, build_cases, score_system


def _example(seed: int) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    hit = (rng.random((32, 18)) > 0.94).astype(np.float32)
    return {
        "hit": hit,
        "subhits": hit.astype(np.int64),
        "velocity": (hit * 0.7).astype(np.float32),
        "offset": np.zeros((32, 18), dtype=np.float32),
        "valid": np.ones((32, 18), dtype=np.float32),
        "conditions": rng.random(16).astype(np.float32),
    }


def test_cases_are_identical_for_the_same_seed() -> None:
    examples = [_example(i) for i in range(10)]
    first = build_cases(examples, seed=1)
    second = build_cases(examples, seed=1)
    assert [c.task for c in first] == [c.task for c in second]
    assert all(
        np.array_equal(a.target, b.target) for a, b in zip(first, second, strict=True)
    )


def test_only_infill_family_tasks_are_scored_for_the_primary_metric() -> None:
    examples = [_example(i) for i in range(40)]
    cases = build_cases(examples, seed=1)
    scored = [c for c in cases if c.counts_for_primary]
    assert scored, "the infill family must produce at least one scored case"
    assert all(
        c.task in {"temporal_infill", "lane_infill", "fill", "continuation"}
        for c in scored
    )


def test_a_perfect_system_scores_one() -> None:
    examples = [_example(i) for i in range(10)]
    cases = build_cases(examples, seed=1)

    def oracle(case: EvaluationCase) -> dict[str, np.ndarray]:
        return {
            "hit": case.truth["hit"],
            "velocity": case.truth["velocity"],
            "offset": case.truth["offset"],
        }

    result = score_system(oracle, cases)
    assert result["hit_f1"] > 0.99


def test_a_silent_system_scores_zero() -> None:
    examples = [_example(i) for i in range(10)]
    cases = build_cases(examples, seed=1)

    def silence(case: EvaluationCase) -> dict[str, np.ndarray]:
        return {
            "hit": np.zeros((32, 18), dtype=np.float32),
            "velocity": np.zeros((32, 18), dtype=np.float32),
            "offset": np.zeros((32, 18), dtype=np.float32),
        }

    assert score_system(silence, cases)["hit_f1"] == 0.0
