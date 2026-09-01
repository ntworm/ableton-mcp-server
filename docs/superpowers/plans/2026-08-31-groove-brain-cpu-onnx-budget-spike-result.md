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
| `cell_token` | 576 | 4758791 | 419850 | 32 | 16 | 16 |
| `step_token` | 32 | 4802174 | 415564 | 32 | 32 | 32 |

A value of 0 means even a single decoding pass breaks a limit.

## Every run

| Variant | Threads | Steps | Wall s | CPU s | Peak MiB | Limits broken |
|---|---|---|---|---|---|---|
| `cell_token` | 1 | 1 | 0.0609 | 0.0625 | 434.0 | none |
| `cell_token` | 1 | 2 | 0.124 | 0.125 | 434.0 | none |
| `cell_token` | 1 | 4 | 0.241 | 0.2344 | 434.1 | none |
| `cell_token` | 1 | 8 | 0.4807 | 0.4844 | 434.1 | none |
| `cell_token` | 1 | 16 | 0.9849 | 0.9844 | 434.1 | none |
| `cell_token` | 1 | 32 | 1.9377 | 1.9375 | 434.1 | none |
| `cell_token` | 4 | 1 | 0.0207 | 0.0625 | 440.4 | none |
| `cell_token` | 4 | 2 | 0.037 | 0.1875 | 440.4 | none |
| `cell_token` | 4 | 4 | 0.0776 | 0.2812 | 440.4 | none |
| `cell_token` | 4 | 8 | 0.2017 | 0.8125 | 440.4 | none |
| `cell_token` | 4 | 16 | 0.4169 | 1.6406 | 440.4 | none |
| `cell_token` | 4 | 32 | 0.8062 | 3.2344 | 440.4 | cpu_seconds |
| `cell_token` | 8 | 1 | 0.0158 | 0.125 | 442.0 | none |
| `cell_token` | 8 | 2 | 0.0396 | 0.375 | 442.0 | none |
| `cell_token` | 8 | 4 | 0.0698 | 0.5 | 442.0 | none |
| `cell_token` | 8 | 8 | 0.1338 | 1.0 | 442.0 | none |
| `cell_token` | 8 | 16 | 0.2481 | 2.0 | 442.0 | none |
| `cell_token` | 8 | 32 | 0.52 | 4.1094 | 442.0 | cpu_seconds |
| `step_token` | 1 | 1 | 0.0026 | 0.0 | 419.9 | none |
| `step_token` | 1 | 2 | 0.005 | 0.0 | 419.9 | none |
| `step_token` | 1 | 4 | 0.0107 | 0.0156 | 419.9 | none |
| `step_token` | 1 | 8 | 0.0213 | 0.0312 | 419.9 | none |
| `step_token` | 1 | 16 | 0.0415 | 0.0469 | 419.9 | none |
| `step_token` | 1 | 32 | 0.0849 | 0.0938 | 419.9 | none |
| `step_token` | 4 | 1 | 0.0015 | 0.0625 | 420.2 | none |
| `step_token` | 4 | 2 | 0.0031 | 0.0 | 420.2 | none |
| `step_token` | 4 | 4 | 0.0062 | 0.0625 | 420.2 | none |
| `step_token` | 4 | 8 | 0.0122 | 0.0312 | 420.2 | none |
| `step_token` | 4 | 16 | 0.0242 | 0.0625 | 420.2 | none |
| `step_token` | 4 | 32 | 0.0551 | 0.1875 | 420.2 | none |
| `step_token` | 8 | 1 | 0.0015 | 0.0625 | 420.5 | none |
| `step_token` | 8 | 2 | 0.0023 | 0.0 | 420.5 | none |
| `step_token` | 8 | 4 | 0.005 | 0.0781 | 420.5 | none |
| `step_token` | 8 | 8 | 0.0107 | 0.125 | 420.5 | none |
| `step_token` | 8 | 16 | 0.0199 | 0.1406 | 420.5 | none |
| `step_token` | 8 | 32 | 0.0397 | 0.375 | 420.5 | none |

Raw data: `lab/artifacts/budget.json`.
