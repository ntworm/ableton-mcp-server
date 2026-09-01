# CPU/ONNX budget spike - result

Measured with untrained weights. The question is arithmetic cost, not quality.

## Environment

- Python 3.10.11 on Windows-10-10.0.26200-SP0
- Intel64 Family 6 Model 151 Stepping 2, GenuineIntel
- PyTorch 2.12.0+cpu, CUDA available: False
- ONNX Runtime 1.23.2, providers: AzureExecutionProvider, CPUExecutionProvider

## Maximum decoding steps inside every limit

| Variant | Sequence | Parameters | ONNX bytes | 1 thread | 4 threads | 8 threads |
|---|---|---|---|---|---|---|
| `cell_token` | 576 | 4758791 | 419850 | 16 | 16 | 8 |
| `step_token` | 32 | 4802174 | 415564 | 32 | 32 | 32 |

A value of 0 means even a single decoding pass breaks a limit.

## Every run

Each configuration is measured three times and judged on its worst CPU
result, because a single timing near the ceiling is not stable.

| Variant | Threads | Steps | Wall s | CPU s worst | CPU s best | Peak MiB | Limits broken |
|---|---|---|---|---|---|---|---|
| `cell_token` | 1 | 1 | 0.0648 | 0.0625 | 0.0625 | 433.0 | none |
| `cell_token` | 1 | 2 | 0.1289 | 0.125 | 0.125 | 433.0 | none |
| `cell_token` | 1 | 4 | 0.2555 | 0.25 | 0.2188 | 433.0 | none |
| `cell_token` | 1 | 8 | 0.5188 | 0.5312 | 0.4688 | 433.0 | none |
| `cell_token` | 1 | 16 | 1.0342 | 1.0312 | 0.9375 | 433.0 | none |
| `cell_token` | 1 | 32 | 2.0564 | 2.0156 | 2.0 | 433.1 | cpu_seconds |
| `cell_token` | 4 | 1 | 0.0228 | 0.125 | 0.0625 | 440.3 | none |
| `cell_token` | 4 | 2 | 0.0488 | 0.1875 | 0.125 | 440.3 | none |
| `cell_token` | 4 | 4 | 0.0857 | 0.3594 | 0.3125 | 440.3 | none |
| `cell_token` | 4 | 8 | 0.1747 | 0.6719 | 0.6562 | 440.3 | none |
| `cell_token` | 4 | 16 | 0.339 | 1.3594 | 1.2812 | 440.3 | none |
| `cell_token` | 4 | 32 | 0.6712 | 2.6562 | 2.5781 | 440.3 | cpu_seconds |
| `cell_token` | 8 | 1 | 0.0182 | 0.1719 | 0.125 | 443.1 | none |
| `cell_token` | 8 | 2 | 0.0343 | 0.25 | 0.2344 | 443.1 | none |
| `cell_token` | 8 | 4 | 0.0759 | 0.625 | 0.5 | 443.1 | none |
| `cell_token` | 8 | 8 | 0.1351 | 1.0938 | 0.9844 | 443.1 | none |
| `cell_token` | 8 | 16 | 0.2791 | 2.25 | 2.0625 | 443.1 | cpu_seconds |
| `cell_token` | 8 | 32 | 0.5647 | 4.4062 | 4.2188 | 443.1 | cpu_seconds |
| `step_token` | 1 | 1 | 0.003 | 0.0 | 0.0 | 419.9 | none |
| `step_token` | 1 | 2 | 0.0055 | 0.0156 | 0.0 | 419.9 | none |
| `step_token` | 1 | 4 | 0.0109 | 0.0156 | 0.0 | 419.9 | none |
| `step_token` | 1 | 8 | 0.0224 | 0.0156 | 0.0156 | 419.9 | none |
| `step_token` | 1 | 16 | 0.0449 | 0.0469 | 0.0312 | 419.9 | none |
| `step_token` | 1 | 32 | 0.0889 | 0.0938 | 0.0625 | 419.9 | none |
| `step_token` | 4 | 1 | 0.0015 | 0.0312 | 0.0 | 420.2 | none |
| `step_token` | 4 | 2 | 0.003 | 0.0 | 0.0 | 420.2 | none |
| `step_token` | 4 | 4 | 0.006 | 0.0625 | 0.0 | 420.2 | none |
| `step_token` | 4 | 8 | 0.0111 | 0.0625 | 0.0156 | 420.2 | none |
| `step_token` | 4 | 16 | 0.024 | 0.125 | 0.0781 | 420.2 | none |
| `step_token` | 4 | 32 | 0.0477 | 0.1875 | 0.125 | 420.2 | none |
| `step_token` | 8 | 1 | 0.0014 | 0.0 | 0.0 | 422.0 | none |
| `step_token` | 8 | 2 | 0.0029 | 0.125 | 0.0 | 422.0 | none |
| `step_token` | 8 | 4 | 0.0073 | 0.125 | 0.0 | 422.0 | none |
| `step_token` | 8 | 8 | 0.0115 | 0.125 | 0.0 | 422.0 | none |
| `step_token` | 8 | 16 | 0.0233 | 0.2188 | 0.125 | 422.0 | none |
| `step_token` | 8 | 32 | 0.0439 | 0.375 | 0.25 | 422.0 | none |

## Package footprint

- ONNX Runtime native libraries: 33.4 MiB
- Gate 0 `.ablx` baseline: 154852 bytes
- Model weights per variant are the `ONNX bytes` column above.

This is the runtime and model half of the `.ablx` ceiling that decision O2
has to set. It does not include the helper, the UI or the catalog.

## Reading the memory column

Peak memory is the whole lab process, which has PyTorch loaded alongside
ONNX Runtime. The shipped helper is native and never loads PyTorch, so these
figures are an upper bound contaminated by the harness, not a reading of what
the provider would use. A dedicated measurement in a PyTorch-free process is
needed before anyone claims the 512 MiB ceiling is close.

Raw data: `lab/artifacts/budget.json`.
