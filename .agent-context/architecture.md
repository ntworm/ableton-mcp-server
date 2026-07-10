# Architecture

## System boundary

The repository contains one MCP-facing Python package and two Live-side adapters. The Python process never imports Ableton. Live loads the Remote Script and Extension separately.

```text
MCP client
  -> stdio MCP: ableton_mcp_server/server.py
       -> Client serialized routing
            -> TCP JSONL 127.0.0.1:9888
                 -> Remote Script socket thread
                 -> request queue
                 -> update_display() on Live UI thread
                 -> Python Live Object Model
            -> WebSocket JSON-RPC :9889
                 -> Extension Host async handler
                 -> Node.js Live Object Model
```

Primary evidence: `README.md`, `docs/ARCHITECTURE.md`, `ableton_mcp_server/client.py`, `AbletonMCPServer_RemoteScript/__init__.py`, and `AbletonMCPServer_Extension/src/index.ts`.

## Components and ownership

### MCP package

- `server.py`: owns the FastMCP instance and 46-function public registry.
- `models.py`: owns request validation and the 46 request-model mapping.
- `client.py`: owns one TCP client plus a WebSocket client and selects the route from `WEBSOCKET_TARGET_COMMANDS`.
- `protocol.py`, `errors.py`, `write_guard.py`, `ids.py`: framing, typed failures, allowlist enforcement, and path-ID validation.
- `diagnostics.py`, `snapshot.py`, `diff.py`: inspection helpers independent of Live imports.
- `cli.py`, `acceptance.py`: installation/doctor commands and guarded real-Live verification.

### Remote Script

`AbletonMCPServer_RemoteScript/__init__.py` owns the TCP listener, per-request response queues, deferred command generators, undo grouping, and Python LOM handlers. Socket work stays off the UI thread; `update_display()` advances queued LOM work on Live's main thread.

### Extension

`AbletonMCPServer_Extension/src/extension.ts` owns activation/deactivation. `context.ts` stores the initialized SDK context for the Extension lifetime. `index.ts` owns the WebSocket server and handlers for:

- `get_warp_state`;
- `set_warp_state`;
- `load_device_to_track`.

The first two access `AudioClip`; device insertion calls `track.insertDevice()`.

## Routing and contracts

`contracts.py` is canonical. At v0.3.0 it defines 23 read commands, 18 allowed mutations, five explicitly blocked commands, and three WebSocket targets. `scripts/vendor_contracts.py` renders the vendored Remote Script copy, and tests compare the result.

Python MCP-only tools such as diagnostics, snapshot diffing, and extension scaffolding/building do not all correspond one-for-one with remote command sets; therefore 46 public tools and 41 remote commands are both valid counts.

## Protocols

- TCP: newline-delimited UTF-8 JSON request/response envelopes; bound explicitly to `127.0.0.1:9888`.
- WebSocket: JSON-RPC 2.0 request/result/error envelopes on port 9889.
- MCP: FastMCP over stdio; expected remote failures are converted to explicit error results.

The Node WebSocket server currently specifies a port but no `host`. Treat local-only binding as an intended constraint that still needs code-level enforcement; see `risks.md`.

## Mutation lifecycle

Transport/cue mutations use deferred generators: write, yield to later Live ticks, read back, retry within contract limits, then return observed state or a typed error. Standalone mutations create one undo step. `run_batch` creates one outer undo step, stops on the first failure, and leaves the successful prefix applied.

Mutations are never replayed automatically after an ambiguous network failure.

## Identity and references

Path IDs encode index paths such as `track:2/device:1`. They are re-resolved per call and are not durable identities. Track or device structure changes can invalidate them.

## Build/package boundaries

- Hatchling packages `ableton_mcp_server`, force-including root `contracts.py` and the Remote Script under `ableton_mcp_server/_remote_script`.
- The Extension uses TypeScript type checking plus `tsx build.ts`; esbuild bundles `src/extension.ts` to the manifest entry.
- Root and Extension manifests currently share version `0.3.0`.

