"""Score the masked HVO against the baselines and answer gate G5."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import torch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "lab"))

from groove_lab.eval.baselines import MarginalSampler, RetrievalBaseline  # noqa: E402
from groove_lab.eval.metrics import (  # noqa: E402
    exact_repeat_rate,
    lane_distribution,
    lane_distribution_distance,
)
from groove_lab.eval.runner import (  # noqa: E402
    EvaluationCase,
    build_cases,
    score_system,
)
from groove_lab.training.generate import generate  # noqa: E402
from groove_lab.training.loader import ShardDataset  # noqa: E402
from groove_lab.training.loop import TrainState, load_checkpoint  # noqa: E402
from groove_lab.training.model import MaskedHvo  # noqa: E402
from groove_lab.training.tasks import TASK_INDEX  # noqa: E402

DATASET = "F:/groove-brain/dataset/build-a"
RUNS = Path("F:/groove-brain/runs")
OUTPUT = RUNS / "gate_g5.json"
SEEDS = (0, 1, 2)
FREE_SAMPLES = 64
CORPUS_REPEAT_RATE = 0.260  # specification 4.2


def _model_system(model: MaskedHvo):
    def run(case: EvaluationCase) -> dict[str, np.ndarray]:
        with torch.no_grad():
            out = model(
                hit=torch.from_numpy(case.truth["hit"]).unsqueeze(0),
                velocity=torch.from_numpy(case.truth["velocity"]).unsqueeze(0),
                offset=torch.from_numpy(case.truth["offset"]).unsqueeze(0),
                observed_mask=torch.from_numpy(case.observed).unsqueeze(0),
                conditions=torch.from_numpy(case.conditions).unsqueeze(0),
                task=torch.tensor([TASK_INDEX[case.task]], dtype=torch.long),
            )
        return {
            "hit": torch.sigmoid(out["hit_logits"])[0].numpy(),
            "velocity": out["velocity"][0].numpy(),
            "offset": out["offset"][0].numpy(),
        }

    return run


def _checkpoint(seed: int) -> MaskedHvo:
    state = TrainState(MaskedHvo(), 1e-3, 0)
    load_checkpoint(state, RUNS / f"m1-seed{seed}" / "best.pt")
    state.model.eval()
    return state.model


def main() -> None:
    torch.set_num_threads(1)
    train = ShardDataset(DATASET, "train", max_subhits=4)
    validation = ShardDataset(DATASET, "validation", max_subhits=4)
    corpus = [train[index] for index in range(len(train))]
    examples = [validation[index] for index in range(len(validation))]
    corpus_hits = [example["hit"] for example in corpus]

    retrieval = RetrievalBaseline(corpus)
    per_seed: dict[str, list[float]] = {
        "masked_hvo": [],
        "retrieval": [],
        "marginal": [],
    }
    free: dict[str, list[np.ndarray]] = {"masked_hvo": [], "marginal": []}

    for seed in SEEDS:
        cases = build_cases(examples, seed=seed)
        model = _checkpoint(seed)
        sampler = MarginalSampler(corpus, seed=seed)

        systems = {
            "masked_hvo": _model_system(model),
            "retrieval": lambda case: retrieval.complete(case.truth, case.observed),
            "marginal": lambda case: sampler.sample(),
        }
        for name, system in systems.items():
            per_seed[name].append(score_system(system, cases)["hit_f1"])

        for sample in range(FREE_SAMPLES):
            free["masked_hvo"].append(
                generate(
                    model,
                    np.zeros(16, dtype=np.float32),
                    seed=seed * 1000 + sample,
                    decoding_steps=32,
                    temperature=1.0,
                )["hit"]
            )
            free["marginal"].append(sampler.sample()["hit"])
        print(f"seed {seed} scored", flush=True)

    summary: dict[str, dict[str, object]] = {}
    for name, scores in per_seed.items():
        summary[name] = {
            "hit_f1_per_seed": scores,
            "hit_f1_mean": float(np.mean(scores)),
            "hit_f1_spread": float(max(scores) - min(scores)),
        }

    best_baseline = max(
        ("retrieval", "marginal"),
        key=lambda name: float(summary[name]["hit_f1_mean"]),
    )
    baseline_spread = float(summary[best_baseline]["hit_f1_spread"])
    beats_every_seed = all(
        model_score > baseline_score
        for model_score, baseline_score in zip(
            per_seed["masked_hvo"], per_seed[best_baseline], strict=True
        )
    )
    margin = float(summary["masked_hvo"]["hit_f1_mean"]) - float(
        summary[best_baseline]["hit_f1_mean"]
    )

    musicality = {
        name: {
            "lane_distance_to_corpus": lane_distribution_distance(grids, corpus_hits),
            "lane_distribution": lane_distribution(grids).tolist(),
            "exact_repeat_rate": exact_repeat_rate(grids, corpus_hits),
        }
        for name, grids in free.items()
    }

    results: dict[str, object] = {
        "corpus_repeat_rate": CORPUS_REPEAT_RATE,
        "corpus_lane_distribution": lane_distribution(corpus_hits).tolist(),
        "systems": summary,
        "best_baseline": best_baseline,
        "g5_primary": {
            "metric": "hit F1 on masked target cells, infill family, validation",
            "beats_best_baseline_on_every_seed": beats_every_seed,
            "margin": margin,
            "baseline_seed_spread": baseline_spread,
            "pass": bool(beats_every_seed and margin > baseline_spread),
        },
        "musicality": musicality,
        "originality_note": (
            "Retrieval returns real corpus windows, so its exact repeat rate is "
            "100% by construction and it is excluded from the free-generation "
            "comparison. Stated before the run, not discovered after."
        ),
    }
    OUTPUT.write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(results, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
