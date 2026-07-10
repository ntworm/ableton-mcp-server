# Dependencies

## Python runtime

Source: `pyproject.toml` and imports under `ableton_mcp_server/`.

| Dependency | Confirmed role |
|---|---|
| `fastmcp>=3.4,<4` | Creates the MCP server, tool registry, tool metadata, and explicit tool results in `server.py`. |
| `mcp>=1.28,<2` | Supplies MCP content types used at the server boundary. |
| `pydantic>=2.12,<3` | Validates tool and batch requests in `models.py`. |
| `websockets>=14,<15` | Implements the async Python client for the Extension WebSocket bridge. |

Development dependencies are pytest/pytest-asyncio, Ruff, and strict Mypy. Hatchling builds the wheel and force-includes contracts plus the Remote Script.

## Extension runtime/build

Source: `AbletonMCPServer_Extension/package.json` and imports in `src/`/`build.ts`.

| Dependency | Confirmed role |
|---|---|
| `@ableton-extensions/sdk` beta tarball | Initializes the Extension context and exposes `AudioClip`, `WarpMode`, transactions, and device insertion. |
| `ws` | Hosts the JSON-RPC WebSocket server on port 9889. |
| `@ableton-extensions/cli` beta tarball | Packages the built Extension. |
| `typescript` | Strict type checking. |
| `tsx` | Executes `build.ts` and watch mode. |
| `esbuild` | Bundles the Extension entry to CommonJS. |
| `@types/node`, `@types/ws` | Build-time type declarations. |

The SDK and CLI are local `vendor/*.tgz` dependencies and are intentionally excluded from persistent inventory.

## External runtime

- Ableton Live on Windows hosts both Live-side components.
- The Remote Script must be installed/enabled as control surface `AbletonMCPServer`.
- The `.ablx` Extension must be built/loaded for WebSocket-routed tools.
- Node `>=24` is required by the Extension package.
- WSL MCP clients must launch the Windows `.venv-win` executable so bridge loopback stays in the Windows network namespace.

## Optional local tools

Git and `rg` support normal development and context discovery. Repomix and RTK are available locally but are not runtime dependencies; full snapshots are not part of the normal repository workflow.

