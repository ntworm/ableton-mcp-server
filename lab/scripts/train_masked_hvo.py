"""Train the masked HVO transformer. M0 memorises; M1 learns."""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from pathlib import Path

import torch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "lab"))

from groove_lab.training.loader import ShardDataset  # noqa: E402
from groove_lab.training.loop import (  # noqa: E402
    TrainState,
    evaluate,
    run_steps,
    save_checkpoint,
)
from groove_lab.training.model import MaskedHvo  # noqa: E402

DATASET = "F:/groove-brain/dataset/build-a"


def _chunks(positions: list[int], size: int, rng) -> list[list[int]]:
    order = list(positions)
    rng.shuffle(order)
    return [order[i : i + size] for i in range(0, len(order), size)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("m0", "m1"), required=True)
    parser.add_argument("--examples", type=int, default=64)
    parser.add_argument("--steps", type=int, default=2000)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--eval-every", type=int, default=200)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--workspace", type=Path, default=Path("F:/groove-brain/runs"))
    arguments = parser.parse_args()

    torch.set_num_threads(1)  # plan 3: more threads make the CPU budget worse
    train = ShardDataset(DATASET, "train", max_subhits=4)
    validation = ShardDataset(DATASET, "validation", max_subhits=4)

    if arguments.mode == "m0":
        positions = list(range(min(arguments.examples, len(train))))
    else:
        positions = list(range(len(train)))

    state = TrainState(MaskedHvo(), arguments.learning_rate, arguments.seed)
    run_dir = arguments.workspace / f"{arguments.mode}-seed{arguments.seed}"
    validation_batches = [
        validation.collate(chunk)
        for chunk in validation.batch_indices(arguments.batch_size, 0)[:4]
    ]
    history: list[dict[str, float]] = []
    best = float("inf")
    started = time.perf_counter()

    while state.step < arguments.steps:
        batches = [
            train.collate(chunk)
            for chunk in _chunks(positions, arguments.batch_size, state.rng)
        ]
        run_steps(state, batches)
        if state.step % arguments.eval_every >= len(batches) and state.step < arguments.steps:
            continue
        train_loss = evaluate(state, batches[:4])
        validation_loss = evaluate(state, validation_batches)
        history.append(
            {
                "step": state.step,
                "train": train_loss,
                "validation": validation_loss,
            }
        )
        print(
            f"step {state.step:6d}  train {train_loss:.5f}  "
            f"validation {validation_loss:.5f}",
            flush=True,
        )
        if validation_loss < best:
            best = validation_loss
            save_checkpoint(state, run_dir / "best.pt")

    save_checkpoint(state, run_dir / "last.pt")
    record = {
        "mode": arguments.mode,
        "examples": len(positions),
        "steps": state.step,
        "seed": arguments.seed,
        "batch_size": arguments.batch_size,
        "learning_rate": arguments.learning_rate,
        "final_train_loss": history[-1]["train"] if history else None,
        "best_validation_loss": best,
        "history": history,
        "wall_seconds": round(time.perf_counter() - started, 2),
        "environment": {
            "python": sys.version.split()[0],
            "torch": torch.__version__,
            "platform": platform.platform(),
        },
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                key: record[key]
                for key in (
                    "mode",
                    "examples",
                    "steps",
                    "final_train_loss",
                    "best_validation_loss",
                    "wall_seconds",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
