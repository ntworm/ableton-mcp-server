# Groove Brain lab

Experiment code for the Groove Brain training program. Nothing here ships. The
product package `ableton_mcp_server/` never imports from `groove_lab`, and the
product environment `.venv-win` never installs these dependencies.

## Environment

```bash
py -3.10 -m venv lab/.venv-lab
lab/.venv-lab/Scripts/python.exe -m pip install -r lab/requirements.txt --index-url https://download.pytorch.org/whl/cpu --extra-index-url https://pypi.org/simple
```

CPU-only on purpose. The budget spike measures the user's inference path, which
is CPU, so a CUDA build would make the numbers optimistic.

Python 3.10 rather than the 3.14 the product environment uses, because that is
what the PyTorch CPU wheels target.

## Running the budget spike

```bash
lab/.venv-lab/Scripts/python.exe lab/scripts/run_spike.py
```

Writes `lab/artifacts/budget.json` and the report at
`docs/superpowers/plans/2026-08-31-groove-brain-cpu-onnx-budget-spike-result.md`.

## Tests

```bash
lab/.venv-lab/Scripts/python.exe -m pytest lab/tests -q
```

## Resolved versions

`onnxruntime` is pinned to `1.23.2`, the newest published release; the plan's
`1.24.0` does not exist. Every other pin resolved as written. `run_spike.py`
records the versions it actually ran under into `lab/artifacts/budget.json`
under `environment`.
