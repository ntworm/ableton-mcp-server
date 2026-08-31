# Groove Brain Gate 0 Result

Observed on 2026-08-31 from source commit `9438a692f851fd6ba615e5f183165850e367ae98`.

## Compatibility captured

- Windows `10.0.26200.0`, x64.
- Ableton Live 12 Beta `12.4.5b11`.
- Extension Host Node `v24.14.1`.
- `@ableton-extensions/sdk` and `@ableton-extensions/cli` `1.0.0-beta.0`.
- SDK archive SHA-256 `a10ec4d85d1b3af32de924ff77454b05bf3cfd5a0bfcd3b8a6c2bd74069d7a6c`.
- CLI archive SHA-256 `ffbfcc18c65f1debe6ab368a53d7313aa1c8f746faed42da5178e793cbaf0bfc`.

The package was not installed or executed in Live during this run. The open `Untitled*` Set contained
Piano V3 and RC-Midi-Receiver material and was not treated as disposable. The owner chose to leave the
direct Live test until last.

| Gate | Result | Evidence path/hash |
|---|---|---|
| Exact compatibility matrix captured | PASS | Versions and vendored archive hashes above |
| `.ablx` inventory/hash/size verified | PASS | `fresh-package-0.1.0.json`; SHA-256 `08b3c40321711ac87472c92042e9455f7a130307cfaa521bbfde24153d2d7428`; 154,774 bytes; 7 files |
| Clean machine requires only `.ablx` | FAIL | Clean Windows machine/VM run deferred |
| Installed resource discovery independent of CWD | PASS | `resource-path.test.ts`; 40/40 Node tests |
| Bundled helper hash verified before spawn | PASS | Helper SHA-256 `7bf6c5a1c44b007b926af84aa7347b469c28e4ee153368f3b21c718faa44c242`; runtime and archive verifier PASS |
| Loopback port allocated atomically | PASS | Rust binds `127.0.0.1:0`; two-session integration PASS |
| Secret absent from argv/server requests/logs; fragment cleared before health | PASS | Token travels over stdin and bearer header only; URL fragment is removed before health; no token logging found |
| Contextual modal loads local UI | FAIL | Live contextual action not executed |
| Explicit empty-slot confirmation | PASS | Production UI event tests PASS |
| Session create/set/readback matches | FAIL | State machine/unit readback PASS; real Live SDK writeback deferred |
| Occupied slot fails before mutation | PASS | State-machine test verifies zero create calls and preserved clip |
| Failure after create reports partial/no retry | PASS | Injected state-machine test verifies `partial`, one create, no retry/rollback claim |
| Normal close leaves zero helper | PASS | Two real helper processes authenticate and stop; zero helper remained after tests |
| Helper crash leaves Set unmodified | FAIL | Disposable-Set crash path deferred |
| Host/Live crash leaves zero helper | FAIL | Disposable-Set host-kill path deferred |
| Two helper sessions isolate port/token | PASS | Node integration verifies distinct modal URLs/ports and authenticated health |
| Update preserves permitted storage | FAIL | 0.1.0/0.1.1 packages verified; supported Live update/storage run deferred |
| Uninstall leaves no executable process/copy | FAIL | Supported Live uninstall run deferred |
| Offline run makes zero egress attempt | FAIL | Firewall/clean-machine observation deferred |
| Existing MCP Extension build/regressions pass | PASS | Existing Extension build PASS; focused Python regressions 6/6 PASS |

**Decision:** STOP

**Disabled capabilities:** Arrangement, global persistent panel, SD3 mapping, inference, corpus, model training.

## Fresh automated verification

- Node Gate 0 tests: 40 passed, 0 failed, 0 skipped after package staging.
- Strict Gate 0 TypeScript typecheck: PASS.
- Gate 0 build and package from an empty generated build directory: PASS.
- Existing MCP Extension build: PASS.
- Rust tests: 10 passed; Clippy with `-D warnings`: PASS.
- Focused Python tests: 6 passed; Ruff: PASS.
- Fresh `0.1.1` package SHA-256: `0dcfbf1b64fb90e6667f80b85face66639a76827710c7a5c686fb04c02ae4c63`.
- Both package versions have different package hashes, matching version contracts, and the same helper
  hash.
- Gate-owned `git diff --check`: PASS. Repository-wide `git diff --check` still reports whitespace in
  unrelated pre-existing prototype edits; those files were preserved and excluded.

External evidence root:
`C:\Users\Usuario\repos\_release-artifacts\groove-brain-gate0`.

## Stop condition

No corpus, retrieval, ONNX, or model-training work may begin from this result. Replace `FAIL` rows only
with observed evidence from the operator runbook. A later all-PASS report may change the decision to
`GO LIMITED`.
