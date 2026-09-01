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

# A single timing near the ceiling is not stable: the first sweep of this spike
# put cell_token at 32 steps on one thread and the immediate rerun put it at 16,
# because the machine was busier. Each configuration is therefore measured
# REPEATS times and judged on its worst result, which is the only safe reading of
# a hard ceiling.
REPEATS = 3


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
            attempts = [
                measure(lambda steps=total_steps: _decode_once(session, mapping, steps))
                for _ in range(REPEATS)
            ]
            worst = max(attempts, key=lambda item: item.cpu_seconds)
            values = {
                "generation_seconds": max(a.wall_seconds for a in attempts),
                "cpu_seconds": worst.cpu_seconds,
                "startup_seconds": startup_seconds,
                "memory_mib": max(a.peak_memory_mib for a in attempts),
            }
            broken = verdict(values)
            runs.append(
                {
                    "threads": threads,
                    "decoding_steps": total_steps,
                    "repeats": REPEATS,
                    "wall_seconds_worst": round(values["generation_seconds"], 4),
                    "cpu_seconds_worst": round(worst.cpu_seconds, 4),
                    "cpu_seconds_best": round(
                        min(a.cpu_seconds for a in attempts), 4
                    ),
                    "startup_seconds": round(startup_seconds, 4),
                    "startup_cpu_seconds": round(startup_cpu, 4),
                    "peak_memory_mib": round(values["memory_mib"], 1),
                    "limits_broken": broken,
                }
            )
            print(
                f"  {name:11s} threads={threads} steps={total_steps:2d} "
                f"wall={values['generation_seconds']:6.3f}s "
                f"cpu={worst.cpu_seconds:6.3f}s (best {min(a.cpu_seconds for a in attempts):.3f}) "
                f"{'OK' if not broken else 'BREAKS ' + ','.join(broken)}",
                flush=True,
            )
            if not broken:
                best = total_steps
        best_by_threads[str(threads)] = best
    return entry


def _runtime_footprint() -> dict[str, int]:
    """Bytes ONNX Runtime and the model would add on top of the Gate 0 package."""

    runtime_root = Path(ort.__file__).resolve().parent
    native = sum(
        path.stat().st_size
        for path in runtime_root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".dll", ".pyd", ".so"}
    )
    return {
        "onnxruntime_native_bytes": native,
        "gate0_ablx_bytes": 154852,
    }


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

    report["footprint"] = _runtime_footprint()

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
        "Each configuration is measured three times and judged on its worst CPU",
        "result, because a single timing near the ceiling is not stable.",
        "",
        "| Variant | Threads | Steps | Wall s | CPU s worst | CPU s best | Peak MiB | Limits broken |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name, entry in report["variants"].items():
        for run in entry["runs"]:
            broken = ", ".join(run["limits_broken"]) or "none"
            lines.append(
                f"| `{name}` | {run['threads']} | {run['decoding_steps']} | "
                f"{run['wall_seconds_worst']} | {run['cpu_seconds_worst']} | "
                f"{run['cpu_seconds_best']} | {run['peak_memory_mib']} | {broken} |"
            )

    footprint = report["footprint"]
    native_mib = footprint["onnxruntime_native_bytes"] / (1024 * 1024)
    lines += [
        "",
        "## Package footprint",
        "",
        f"- ONNX Runtime native libraries: {native_mib:.1f} MiB",
        f"- Gate 0 `.ablx` baseline: {footprint['gate0_ablx_bytes']} bytes",
        "- Model weights per variant are the `ONNX bytes` column above.",
        "",
        "This is the runtime and model half of the `.ablx` ceiling that decision O2",
        "has to set. It does not include the helper, the UI or the catalog.",
        "",
        "## Reading the memory column",
        "",
        "Peak memory is the whole lab process, which has PyTorch loaded alongside",
        "ONNX Runtime. The shipped helper is native and never loads PyTorch, so these",
        "figures are an upper bound contaminated by the harness, not a reading of what",
        "the provider would use. A dedicated measurement in a PyTorch-free process is",
        "needed before anyone claims the 512 MiB ceiling is close.",
        "",
        "Raw data: `lab/artifacts/budget.json`.",
    ]
    RESULT_DOC.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
