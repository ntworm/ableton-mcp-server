"""Export a masked HVO variant to ONNX and run it under ONNX Runtime.

TorchScript has been deprecated since PyTorch 2.10, so the Dynamo exporter is the
supported route.  The module records which exporter actually succeeded in
``EXPORTER_USED``, because that fact belongs in the spike's report rather than in
somebody's memory.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import onnxruntime as ort
import torch
from torch import nn

from .model import CONDITIONS, LANES, STEPS

INPUT_NAMES = ["hit", "velocity", "offset", "observed_mask", "conditions"]
OUTPUT_NAMES = ["hit_logits", "subhits_logits", "velocity_out", "offset_out"]

EXPORTER_USED = "unknown"


def _example_inputs(batch: int = 1) -> tuple[torch.Tensor, ...]:
    shape = (batch, STEPS, LANES)
    return (
        torch.zeros(shape),
        torch.zeros(shape),
        torch.zeros(shape),
        torch.zeros(shape),
        torch.zeros((batch, CONDITIONS)),
    )


def export_to_onnx(model: nn.Module, path: Path) -> str:
    """Write ``model`` to ``path`` and return the exporter that produced it."""

    global EXPORTER_USED
    model.eval()
    args = _example_inputs()
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        torch.onnx.export(
            model,
            args,
            str(path),
            input_names=INPUT_NAMES,
            output_names=OUTPUT_NAMES,
            dynamo=True,
        )
        EXPORTER_USED = "dynamo"
    except Exception:  # noqa: BLE001 - the fallback is the point of this branch
        torch.onnx.export(
            model,
            args,
            str(path),
            input_names=INPUT_NAMES,
            output_names=OUTPUT_NAMES,
            opset_version=17,
        )
        EXPORTER_USED = "torchscript"
    return EXPORTER_USED


def make_session(path: Path, threads: int) -> ort.InferenceSession:
    options = ort.SessionOptions()
    options.intra_op_num_threads = threads
    options.inter_op_num_threads = 1
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    return ort.InferenceSession(
        str(path), sess_options=options, providers=["CPUExecutionProvider"]
    )


def output_map(session: ort.InferenceSession) -> dict[str, str]:
    """Map the four logical head names onto whatever the exporter called them.

    The order of ``session.get_outputs()`` follows the model's return order, which
    is stable, but the names are the exporter's choice.  Binding by position and
    reporting the real names keeps the harness honest either way.
    """

    names = [output.name for output in session.get_outputs()]
    logical = ["hit_logits", "subhits_logits", "velocity", "offset"]
    return dict(zip(logical, names, strict=True))


def run_onnx_session(
    path: Path, inputs: dict[str, np.ndarray], threads: int = 1
) -> dict[str, np.ndarray]:
    session = make_session(path, threads)
    mapping = output_map(session)
    values = session.run(None, inputs)
    by_name = dict(zip([o.name for o in session.get_outputs()], values, strict=True))
    return {logical: by_name[actual] for logical, actual in mapping.items()}
