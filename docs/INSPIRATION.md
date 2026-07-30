# Inspiration & prior art

This repository is **not** a clean-room implementation of the Ableton Live
Object Model. It is an **accumulated toolkit** assembled for one person's
workflow: writing, performing and debugging music in Ableton Live with the
help of MCP-compatible agents. The author walked through several existing
projects to study how they expose Live over the wire, then collected the
parts that fit his own use case into a single server.

If you came here looking for an authoritative reference, please read the
projects below first — they each cover ground that this repository only
borrows.

## Projects that directly shaped this codebase

### `pnomolos/live-wire`

A MIDI Remote Script that exposes a Live Set over a FastAPI HTTP surface,
with verified transport writes and a typed MIDI command dispatcher. Most
of the conceptual layout of the TCP JSONL bridge — the per-tick
verification loop, the typed error envelopes, the `update_display`
scheduling — was lifted from there. The original code is **not** vendored;
the contracts, the bridge shape and the dispatch discipline are.

- https://github.com/pnomolos/live-wire (commit `7fc8b06` referenced for
  design notes; design-only, no code copy).

### `hidingwill/AbletonBridge`

A different take at the same surface: a TCP bridge that exposes device
parameters, transport and a small set of session mutations to a remote
client. The grouped `run_batch` semantics with explicit
`rolled_back: false` semantics, and the way attribute mutations are
verified before reporting success, were inspired by this project.

- https://github.com/hidingwill/AbletonBridge (commit `01c31c4e`
  referenced for design notes; design-only, no code copy).

### `ideoforms/AbletonOSC`

The de-facto reference for exposing the Live Object Model over Open Sound
Control. The constants and command names used by the Extension Host
bridge are aligned with AbletonOSC conventions where it makes sense.

- https://github.com/ideoforms/AbletonOSC

### `ideoforms/pylive`

A query-and-control layer for Live from Python. Its `Live.Object.Model`
quick reference and the parameter-resolution helpers were useful as a
reference when validating the introspection surface of the FastMCP server.

- https://github.com/ideoforms/pylive

### `Simon-Kansara/ableton-live-mcp-server`

Another MCP server for Ableton Live, oriented around OSC rather than the
MIDI Remote Script path. Reading its tool surface influenced the
session-side tool selection in `ableton_mcp_server` — specifically the
decision to keep transport, clips, tracks, and devices on the Python
Remote Script path while routing warping and device loading through the
WebSocket Extension.

- https://github.com/Simon-Kansara/ableton-live-mcp-server

## What this project is

`ableton-mcp-server` is the author's working tool. It exists because:

1. The author's Ableton workflow is more about *iterating* on a Set with
   an agent in the loop than about driving Live from a fixed script.
2. The author runs Live on Windows and is on a WSL distribution where the
   loopback bridge behaves differently; the WSL-safe execution path is
   part of the public surface, not an afterthought.
3. The author's performance setup leans on the Set lifecycle (save,
   quit, fade between tracks) and offline mix analysis (LUFS-I, true
   peak, single-cycle extraction) — these are first-class tools, not
   add-ons.

## What this project is not

- Not a clean-room reference implementation of the Live Object Model.
- Not a fork of any of the projects above. The contract layout borrows
  from them, the code is written from scratch.
- Not a general-purpose Live automation framework. It is, and is expected
  to remain, biased toward the workflows the author uses in shows and
  sessions.

## Where the line is

If you want to read or audit the canonical Live/MCP bridge design, start
with the projects above. If you want a tool that the author uses
day-to-day in his own shows, this is it.
