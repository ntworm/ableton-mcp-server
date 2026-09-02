"""Generate the blind listening set: 30 trials, two anonymous files each."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "lab"))

from groove_lab.eval.baselines import RetrievalBaseline  # noqa: E402
from groove_lab.eval.export import grid_to_midi  # noqa: E402
from groove_lab.eval.runner import build_cases  # noqa: E402
from groove_lab.training.generate import generate  # noqa: E402
from groove_lab.training.loader import ShardDataset  # noqa: E402
from groove_lab.training.loop import TrainState, load_checkpoint  # noqa: E402
from groove_lab.training.model import MaskedHvo  # noqa: E402

DATASET = "F:/groove-brain/dataset/build-a"
RUNS = Path("F:/groove-brain/runs")
TRIALS = 30
ORDER_SEED = 20260831
BPM = 120.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--checkpoint-seed", type=int, default=0)
    arguments = parser.parse_args()

    torch.set_num_threads(1)
    trials_dir = arguments.out / "trials"
    trials_dir.mkdir(parents=True, exist_ok=True)

    train = ShardDataset(DATASET, "train", max_subhits=4)
    validation = ShardDataset(DATASET, "validation", max_subhits=4)
    corpus = [train[index] for index in range(len(train))]
    retrieval = RetrievalBaseline(corpus)

    state = TrainState(MaskedHvo(), 1e-3, 0)
    load_checkpoint(state, RUNS / f"m1-seed{arguments.checkpoint_seed}" / "best.pt")
    state.model.eval()

    cases = build_cases(
        [validation[index] for index in range(len(validation))], seed=ORDER_SEED
    )[:TRIALS]
    order_rng = np.random.default_rng(ORDER_SEED)
    key: list[dict[str, object]] = []

    for number, case in enumerate(cases, start=1):
        model_grid = generate(
            state.model,
            case.conditions,
            seed=ORDER_SEED + number,
            decoding_steps=32,
            temperature=1.0,
        )
        neighbour = retrieval.complete(case.truth, case.observed)
        baseline_grid = {
            "hit": neighbour["hit"],
            "velocity": neighbour["velocity"],
            "offset": neighbour["offset"],
            "subhits": neighbour["subhits"],
        }

        model_is_a = bool(order_rng.integers(0, 2))
        first, second = (
            (model_grid, baseline_grid) if model_is_a else (baseline_grid, model_grid)
        )
        (trials_dir / f"trial-{number:02d}-A.mid").write_bytes(grid_to_midi(first, BPM))
        (trials_dir / f"trial-{number:02d}-B.mid").write_bytes(grid_to_midi(second, BPM))
        key.append(
            {
                "trial": number,
                "task": case.task,
                "A": "masked_hvo" if model_is_a else "retrieval",
                "B": "retrieval" if model_is_a else "masked_hvo",
            }
        )

    # The key sits beside the trials directory, never inside it.
    (arguments.out / "key.json").write_text(
        json.dumps(
            {"order_seed": ORDER_SEED, "bpm": BPM, "trials": key},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"{len(key)} trials written to {trials_dir}")


if __name__ == "__main__":
    main()
