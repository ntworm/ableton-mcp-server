"""Sweep decoding steps and threads to find what fits in cpu_seconds <= 2.0.

Writes ``lab/artifacts/budget.json`` and the result document under
``docs/superpowers/plans/``.  Nothing here is trained: the weights are random,
because the question is arithmetic cost, not quality.
"""

from __future__ import annotations

import json
import platform
import sys
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort
import torch

# The Dynamo exporter prints a check mark, which a cp1252 console cannot encode.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "lab"))

from groove_lab.budget import LIMITS, measure, verdict  # noqa: E402
from groove_lab.decoding import DecodeState, commit_confident_cells, schedule  # noqa: E402
from groove_lab.export import export_to_onnx, make_session, output_map  # noqa: E402
from groove_lab.model import (  # noqa: E402
    CONDITIONS,
    LANES,
    STEPS,
    CellTokenHvo,
    StepTokenHvo,
    count_parameters,
)

ARTIFACTS = REPO_ROOT / "lab" / "artifacts"
RESULT_DOC = (
    REPO_ROOT
    / "docs"
    / "superpowers"
    / "plans"
    / "2026-08-31-groove-brain-cpu-onnx-budget-spike-result.md"
)

THREAD_COUNTS = (1, 4, 8)
STEP_COUNTS = (1, 2, 4, 8, 16, 32)
VARIANTS = {"cell_token": CellTokenHvo, "step_token": StepTokenHvo}


def _decode_once(
    session: ort.InferenceSession, mapping: dict[str, str], total_steps: int
) -> int:
    """Run one full decode and return the number of committed cells.

    The output-name mapping is resolved once by the caller, so the measurement
    covers inference and the decoding loop rather than session introspection.
    """

    state = DecodeState.masked(STEPS, LANES)
    conditions = np.zeros((1, CONDITIONS), dtype=np.float32)
    names = [mapping[key] for key in ("hit_logits", "velocity", "offset")]
    committed = 0
    for count in schedule(STEPS * LANES, total_steps):
        hit_logits, velocity, offset = session.run(
            names,
            {
                "hit": state.hit[None, ...],
                "velocity": state.velocity[None, ...],
                "offset": state.offset[None, ...],
                "observed_mask": state.observed_mask[None, ...],
                "conditions": conditions,
            },
        )
        committed += commit_confident_cells(
            state, hit_logits[0], velocity[0], offset[0], count=count
        )
    return committed


def _sweep_variant(name: str, factory: type) -> dict[str, object]:
    model = factory().eval()
    path = ARTIFACTS / f"{name}.onnx"
    exporter = export_to_onnx(model, path)
    entry: dict[str, object] = {
        "sequence_length": model.sequence_length,
        "parameters": count_parameters(model),
        "onnx_bytes": path.stat().st_size,
        "exporter": exporter,
        "runs": [],
        "max_decoding_steps": {},
    }
    runs: list[dict[str, object]] = entry["runs"]  # type: ignore[assignment]
    best_by_threads: dict[str, int] = entry["max_decoding_steps"]  # type: ignore[assignment]

    for threads in THREAD_COUNTS:
        start_wall = time.perf_counter()
        start_cpu = time.process_time()
        session = make_session(path, threads)
        mapping = output_map(session)
        session.run(
            None,
            {
                "hit": np.zeros((1, STEPS, LANES), dtype=np.float32),
                "velocity": np.zeros((1, STEPS, LANES), dtype=np.float32),
                "offset": np.zeros((1, STEPS, LANES), dtype=np.float32),
                "observed_mask": np.zeros((1, STEPS, LANES), dtype=np.float32),
                "conditions": np.zeros((1, CONDITIONS), dtype=np.float32),
            },
        )
        startup_seconds = time.perf_counter() - start_wall
        startup_cpu = time.process_time() - start_cpu

        best = 0
        for total_steps in STEP_COUNTS:
            _decode_once(session, mapping, total_steps)  # warm the caches
            result = measure(
                lambda steps=total_steps: _decode_once(session, mapping, steps)
            )
            values = {
                "generation_seconds": result.wall_seconds,
                "cpu_seconds": result.cpu_seconds,
                "startup_seconds": startup_seconds,
                "memory_mib": result.peak_memory_mib,
            }
            broken = verdict(values)
            runs.append(
                {
                    "threads": threads,
                    "decoding_steps": total_steps,
                    "wall_seconds": round(result.wall_seconds, 4),
                    "cpu_seconds": round(result.cpu_seconds, 4),
                    "startup_seconds": round(startup_seconds, 4),
                    "startup_cpu_seconds": round(startup_cpu, 4),
                    "peak_memory_mib": round(result.peak_memory_mib, 1),
                    "limits_broken": broken,
                }
            )
            print(
                f"  {name:11s} threads={threads} steps={total_steps:2d} "
                f"wall={result.wall_seconds:6.3f}s cpu={result.cpu_seconds:6.3f}s "
                f"{'OK' if not broken else 'BREAKS ' + ','.join(broken)}",
                flush=True,
            )
            if not broken:
                best = total_steps
        best_by_threads[str(threads)] = best
    return entry


def main() -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(0)

    report: dict[str, object] = {
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "processor": platform.processor(),
            "torch": torch.__version__,
            "onnxruntime": ort.__version__,
            "cuda_available": torch.cuda.is_available(),
            "providers": ort.get_available_providers(),
        },
        "limits": LIMITS,
        "variants": {},
    }
    variants: dict[str, object] = report["variants"]  # type: ignore[assignment]

    for name, factory in VARIANTS.items():
        variants[name] = _sweep_variant(name, factory)

    (ARTIFACTS / "budget.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _write_result_document(report)
    print(
        json.dumps(
            {name: entry["max_decoding_steps"] for name, entry in variants.items()},
            indent=2,
        )
    )


def _write_result_document(report: dict) -> None:
    environment = report["environment"]
    lines = [
        "# CPU/ONNX budget spike - result",
        "",
        "Measured with untrained weights. The question is arithmetic cost, not quality.",
        "",
        "## Environment",
        "",
        f"- Python {environment['python']} on {environment['platform']}",
        f"- {environment['processor']}",
        f"- PyTorch {environment['torch']}, CUDA available: {environment['cuda_available']}",
        f"- ONNX Runtime {environment['onnxruntime']}, providers: "
        f"{', '.join(environment['providers'])}",
        "",
        "## Maximum decoding steps inside every limit",
        "",
        "| Variant | Sequence | Parameters | ONNX bytes | 1 thread | 4 threads | 8 threads |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, entry in report["variants"].items():
        best = entry["max_decoding_steps"]
        lines.append(
            f"| `{name}` | {entry['sequence_length']} | {entry['parameters']} | "
            f"{entry['onnx_bytes']} | {best['1']} | {best['4']} | {best['8']} |"
        )
    lines += [
        "",
        "A value of 0 means even a single decoding pass breaks a limit.",
        "",
        "## Every run",
        "",
        "| Variant | Threads | Steps | Wall s | CPU s | Peak MiB | Limits broken |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, entry in report["variants"].items():
        for run in entry["runs"]:
            broken = ", ".join(run["limits_broken"]) or "none"
            lines.append(
                f"| `{name}` | {run['threads']} | {run['decoding_steps']} | "
                f"{run['wall_seconds']} | {run['cpu_seconds']} | "
                f"{run['peak_memory_mib']} | {broken} |"
            )
    lines += ["", "Raw data: `lab/artifacts/budget.json`."]
    RESULT_DOC.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
