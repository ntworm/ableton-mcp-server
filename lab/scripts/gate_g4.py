"""Measure gate G4 against the thresholds declared before the runs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import torch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "lab"))

from groove_lab.training.generate import (  # noqa: E402
    diversity,
    generate,
    is_structurally_valid,
)
from groove_lab.training.loop import TrainState, load_checkpoint  # noqa: E402
from groove_lab.training.model import MaskedHvo  # noqa: E402

RUNS = Path("F:/groove-brain/runs")
OUTPUT = RUNS / "gate_g4.json"
SEEDS = (0, 1, 2)
SAMPLES = 64
DECODING_STEPS = 32

# Declared in the plan before any run. Not to be moved afterwards.
MAX_M0_TRAIN_LOSS = 0.05
MIN_VALIDITY = 1.0
MIN_DIVERSITY = 0.05
CORPUS_HITS_PER_BAR = 16.0
DENSITY_FACTOR = 2.0


def _load(path: Path) -> MaskedHvo:
    state = TrainState(MaskedHvo(), learning_rate=1e-3, seed=0)
    load_checkpoint(state, path)
    model = state.model
    model.eval()
    return model


def main() -> None:
    torch.set_num_threads(1)

    m0 = json.loads((RUNS / "m0-seed0" / "run.json").read_text(encoding="utf-8"))
    m0_loss = float(m0["final_train_loss"])

    per_seed: dict[int, list[dict[str, np.ndarray]]] = {}
    valid = 0
    total = 0
    densities: list[float] = []
    for seed in SEEDS:
        model = _load(RUNS / f"m1-seed{seed}" / "best.pt")
        grids = []
        for sample in range(SAMPLES):
            grid = generate(
                model,
                conditions=np.zeros(16, dtype=np.float32),
                seed=seed * 1000 + sample,
                decoding_steps=DECODING_STEPS,
            )
            grids.append(grid)
            total += 1
            valid += int(is_structurally_valid(grid))
            densities.append(float(grid["hit"].sum()) / 2.0)
        per_seed[seed] = grids
        print(f"seed {seed}: {SAMPLES} samples decoded", flush=True)

    validity = valid / total if total else 0.0
    # Same sample index, different training seed: pure model-to-model variation.
    across_seeds = float(
        np.mean(
            [
                diversity([per_seed[seed][sample] for seed in SEEDS])
                for sample in range(SAMPLES)
            ]
        )
    )
    within = float(np.mean([diversity(per_seed[seed][:16]) for seed in SEEDS]))
    density = float(np.mean(densities))

    results: dict[str, object] = {
        "m0_final_train_loss": {
            "value": m0_loss,
            "threshold": MAX_M0_TRAIN_LOSS,
            "pass": m0_loss < MAX_M0_TRAIN_LOSS,
        },
        "structural_validity": {
            "value": validity,
            "threshold": MIN_VALIDITY,
            "pass": validity >= MIN_VALIDITY,
        },
        "diversity_across_seeds": {
            "value": across_seeds,
            "threshold": MIN_DIVERSITY,
            "pass": across_seeds >= MIN_DIVERSITY,
        },
        "diversity_within_a_seed": {
            "value": within,
            "threshold": MIN_DIVERSITY,
            "pass": within >= MIN_DIVERSITY,
        },
        "hits_per_bar": {
            "value": density,
            "range": [
                CORPUS_HITS_PER_BAR / DENSITY_FACTOR,
                CORPUS_HITS_PER_BAR * DENSITY_FACTOR,
            ],
            "pass": (
                CORPUS_HITS_PER_BAR / DENSITY_FACTOR
                <= density
                <= CORPUS_HITS_PER_BAR * DENSITY_FACTOR
            ),
        },
        "samples": total,
        "decoding_steps": DECODING_STEPS,
    }
    results["gate_g4_pass"] = all(
        bool(entry["pass"]) for entry in results.values() if isinstance(entry, dict)
    )
    OUTPUT.write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(results, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
