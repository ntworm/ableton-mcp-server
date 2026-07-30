# Contributing

This project is intended for **loopback, single-host** use between an
MCP-compatible agent and a running Ableton Live instance. Contributions are
welcome, but please read the rules below before opening a pull request.

## Read first

- `AGENTS.md` — repository-wide rules, including the coupled-change contract.
- `docs/ARCHITECTURE.md` — the two bridges, the live thread, and the owner
  acceptance flow.
- `docs/KNOWN_BUGS.md` — Live / LOM failure modes that the code already
  defends against. New code must not regress these.
- `CHANGELOG.md` — the format is **Keep a Changelog**. New entries go
  under a new `## [Unreleased]` section above the highest released version.

## Local development

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pip install mypy
```

The four gates are:

```bash
python -m ruff check ableton_mcp_server AbletonMCPServer_RemoteScript scripts tests
python -m mypy --strict ableton_mcp_server
python -m pytest -q --tb=line
python scripts/coverage_check.py
```

A pull request should keep **all four green** and stay above the 85% coverage
floor declared in `scripts/coverage_check.py`.

## Coupled-change rules

These are required by `AGENTS.md` and are enforced by the test suite:

- Editing `contracts.py` regenerates `ableton_mcp_server/_contracts.py` via
  `python scripts/vendor_contracts.py`. Never hand-edit the vendored file.
- A new public tool must update `server.py`, `models.py`, the relevant tests,
  `docs/TOOL_REFERENCE.md`, and the asserted tool count in
  `tests/test_server_tools.py`.
- A new routed command must update `contracts.py`, the Python client, the
  Remote Script or Extension handler, the request model, and the tests.
- Bumping a release version must keep `pyproject.toml`, `manifest.json`, and
  `AbletonMCPServer_Extension/package.json` aligned.

## Real Live testing

The Pull Request CI runs without Live. **Do not** test your change against a
real Live Set in CI; the maintainer runs the owner acceptance test on a
disposable Set locally before each release. See `docs/ARCHITECTURE.md` for
the `ableton-mcp.exe acceptance` runner and its required confirmation flags.

## What is not accepted

- Changes that forward the TCP or WebSocket bridge to a non-loopback host.
- Auto-retry on ambiguous mutations. The protocol is explicit-by-design and
  callers must decide.
- Tool count or contract changes that are not aligned across the four
  metadata files.
- Mixing unrelated refactors into a feature or fix commit.

## Commit messages

The repository uses **Conventional Commits** prefixes already
(see `git log --oneline`). Keep the subject line under 70 characters and
include a body that explains the *why*, not just the *what*.
