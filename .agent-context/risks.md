# Risks

## Resolved / Verified: WebSocket bind code-enforces loopback

`AbletonMCPServer_Extension/src/index.ts` explicitly binds `new WebSocketServer({ host: '127.0.0.1', port: 9889 })`. The listener is code-enforced loopback-only and covered by `tests/test_extension_loopback.py`.


## Critical: Python LOM thread affinity

The socket thread must never touch Live's Python Object Model. It parses/enqueues work; `update_display()` advances handlers on Live's UI thread. Direct socket-thread LOM access can destabilize Live.

Evidence: `AbletonMCPServer_RemoteScript/__init__.py`, `docs/ARCHITECTURE.md`, and remote-threading tests.

## High: WSL loopback is not Windows loopback

With common WSL NAT topology, Linux `127.0.0.1` is not the Windows Live process. Launch `.venv-win/Scripts/ableton-mcp-server.exe` through WSL interoperability; do not point the MCP client at the Linux `.venv` process. `doctor` must complete a real `get_session_info` round-trip.

## High: ambiguous mutation outcome

If the connection fails after a mutation is sent, the client cannot know whether Live applied it. Mutations are deliberately not replayed. Inspect current state before deciding whether to resend.

## High: `run_batch` is not rollback

The batch stops at its first failure. Earlier successful commands remain applied inside one undo step and the response reports `rolled_back: false`. One user undo can revert the grouped successful prefix; automatic reverse replay is unsafe.

## High: duplicated contracts can drift

Root `contracts.py` is canonical; the Remote Script cannot import the installed package and uses vendored `_contracts.py`. Always regenerate through `scripts/vendor_contracts.py`. Never patch both copies independently.

## Medium: session-local path IDs

IDs such as `track:2/device:1` are index locators, not stable handles. Re-list after track/device structural edits. Treat resolution failures as stale references rather than retrying the old ID.

## Medium: deferred writes and Arrangement grid behavior

Transport and cue operations may settle over Live UI ticks. Use the existing deferred write/read-back/retry pattern. Cue toggles can snap with Arrangement grid behavior; preserve the mitigation in `docs/KNOWN_BUGS.md` and never write `Song.start_time` as a substitute for moving the playhead.

## Medium: Extension availability is independent

Tool discovery and TCP `doctor` do not prove the Extension WebSocket bridge is loaded. Warp and device-insertion tools can return `EXTENSION_UNAVAILABLE` while TCP tools work. Build/load the `.ablx` and test the WS route separately.

## Medium: acceptance testing mutates a real Set

The acceptance runner requires an exact project-name confirmation and empty MIDI clip slot. Use a disposable Set. It restores transport/loop state, but intentionally leaves the created clip.

## Medium: proposals can be stale

Files under `prompts/` are implementation requests, not current contracts. For example, a proposal may still request a tool already present while another requested tool remains absent. Compare every proposed layer with contracts, models, registry, handler, tests, and docs before coding.

## Lower-level Live quirks

The canonical catalog is `docs/KNOWN_BUGS.md`, including read-only properties, toggle semantics, custom beat-time wrappers, empty MCP arrays, typed expected errors, MIDI note API differences, and cross-platform log discovery. Read the relevant category before changing those paths; do not duplicate the full catalog here.

