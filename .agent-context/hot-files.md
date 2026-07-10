# Hot files

Generated churn evidence is in `generated/hot-files.md`. The paths below are curated because their responsibilities and coupled-change requirements make regressions costly; churn alone was not used as proof.

## Protocol and routing

- `contracts.py`: canonical ports, errors, timeouts, command allowlists, and WebSocket targets. Run `scripts/vendor_contracts.py` after edits.
- `AbletonMCPServer_RemoteScript/_contracts.py`: generated mirror. Never edit manually; `tests/test_vendoring.py` checks it.
- `ableton_mcp_server/client.py`: chooses TCP versus WebSocket and enforces the Python client's loopback host.
- `ableton_mcp_server/models.py`: request validation and batch admissibility; changes affect every public boundary.

## Public MCP surface

- `ableton_mcp_server/server.py`: owns all 46 public tools and the registry asserted by `tests/test_server_tools.py`, `tests/test_tool_registry.py`, and `tests/test_models.py`.
- `docs/TOOL_REFERENCE.md`: user-facing tool contract; update with public surface changes.

## Live execution

- `AbletonMCPServer_RemoteScript/__init__.py`: largest and highest-churn file; owns threading, queues, undo steps, deferred generators, and most Python LOM behavior. Relevant coverage spans remote reads/errors/threading, cue, clip, transaction, and transport tests.
- `tests/remote_fakes.py`: shared test Live model. Handler changes frequently require realistic fake updates.
- `AbletonMCPServer_Extension/src/index.ts`: owns all WebSocket handlers and network bind behavior. Pair changes with Python routing/client tests and an Extension build.

## Packaging and release

- `pyproject.toml`: package metadata, dependencies, entry points, force-includes, Ruff, and Mypy.
- `manifest.json` and `AbletonMCPServer_Extension/package.json`: release identity must remain aligned with `pyproject.toml`.
- `scripts/setup_windows.ps1`: creates `.venv-win`, installs/copies the Remote Script, and verifies hashes; test installation changes on Windows.
- `CHANGELOG.md`, `releases/`: release-facing history and artifacts.

## Canonical behavioral documentation

- `docs/ARCHITECTURE.md`: component/routing/threading model.
- `docs/KNOWN_BUGS.md`: Live API quirks and mitigations.
- `README.md`: supported installation, doctor, acceptance, safety, and verification commands.

When behavior changes, update the canonical document rather than expanding persistent context into a duplicate manual.

