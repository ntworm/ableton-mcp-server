# Groove Brain Gate 0 operator runbook

This gate tests installation and safe Ableton Live mutation only. It does not approve a model,
training, corpus ingestion, Arrangement writeback, a persistent global panel, or publication.

## Preconditions

- Use Windows x64 and a supported Ableton Live beta with Extensions enabled.
- Use a new unsaved disposable Live Set.
- Create one MIDI track with an empty Session slot.
- Do not use Arrangement or an occupied slot for the happy path.
- Record the exact Live beta build and Extension Host Node version in `operator-notes.md`.
- Never run crash or failure-injection tests against an unsaved real project.
- Verify the package first with `scripts/gate0/verify_groove_brain_ablx.py`.
- Keep screenshots, receipts, firewall logs, and notes below the external evidence directory; do not
  commit them.

## Evidence capture

Compute the source and vendored dependency identities from the repository:

```powershell
$artifact = 'C:\Users\Usuario\repos\ableton-mcp-server\AbletonMCPServer_Extension\build\groove-brain-gate0\Groove-Brain-Gate-0-0.1.0.ablx'
$sourceCommit = git -C C:\Users\Usuario\repos\ableton-mcp-server rev-parse HEAD
$sdkHash = (Get-FileHash C:\Users\Usuario\repos\ableton-mcp-server\AbletonMCPServer_Extension\vendor\ableton-extensions-sdk-1.0.0-beta.0.tgz -Algorithm SHA256).Hash.ToLowerInvariant()
$cliHash = (Get-FileHash C:\Users\Usuario\repos\ableton-mcp-server\AbletonMCPServer_Extension\vendor\ableton-extensions-cli-1.0.0-beta.0.tgz -Algorithm SHA256).Hash.ToLowerInvariant()
& C:\Users\Usuario\repos\ableton-mcp-server\scripts\gate0\collect_gate0_evidence.ps1 -Artifact $artifact -SourceCommit $sourceCommit -SdkSha256 $sdkHash -CliSha256 $cliHash -Phase before
```

Run the same command with `-Phase after` after Live is fully closed. The collector records snapshots;
it does not kill Live, install the package, change firewall state, or infer PASS from a missing process.

## Happy path

1. Capture `before` evidence.
2. Install `Groove-Brain-Gate-0-0.1.0.ablx` through Live Settings → Extensions.
3. Right-click the known empty ClipSlot and choose `Open Groove Brain Gate 0`.
4. Confirm the modal loads local assets and reports an authenticated helper.
5. Check the explicit disposable-slot confirmation and run the probe.
6. Verify a four-beat MIDI clip appears with C1/kick notes at beats 0, 1, 2, and 3.
7. Verify the result modal reports `status=ok`, `READBACK_MATCH`, counts 4/4, and equal hashes.
8. Save the matching receipt JSON and screenshot in the run directory.
9. Close the result modal and Live; capture `after` evidence.
10. Confirm zero `groove-brain-gate0-helper` process remains.

## Occupied-slot path

1. Reopen from the newly occupied slot.
2. Confirm the result is `SLOT_OCCUPIED`.
3. Confirm no second clip or notes were created and save the receipt.

## Failure injection path

1. Run the Extension Host in development with `GROOVE_BRAIN_GATE0_INJECT=after_create`.
2. Use another disposable empty slot and run the probe once.
3. Confirm the receipt is `partial` with `INJECTED_AFTER_CREATE`.
4. Confirm exactly one empty partial clip exists, no retry occurred, and no automatic delete claimed
   rollback.
5. Undo manually in Live.

## Crash paths

- Kill the helper while the first modal is open. Close the broken modal manually. Verify a diagnostic
  appears and no clip write occurs.
- Kill the Extension Host or Live in the disposable Set. Verify parent stdin EOF terminates the helper.
- Repeat a normal invocation after restart. Verify it uses a new port and token and does not reuse a
  stale target.

## Clean-machine and offline matrix

Use a Windows x64 machine or VM without the repository, Python, Rust, developer Node, MCP Server, or
Remote Script. Copy only the `.ablx` and this non-installed evidence collector.

1. Disconnect networking or enable auditable deny-all outbound rules for Live, Extension Host, and the
   helper.
2. Install only `0.1.0.ablx`; run happy and occupied paths.
3. Require zero egress attempts in firewall or equivalent monitor logs.
4. Install `0.1.1.ablx` over the same Extension identity; verify permitted receipts survive and the new
   receipt records `0.1.1`.
5. If Live serializes modal actions, record `live_modal_concurrency=HOST_SERIALIZED`; process-level
   two-helper isolation must still pass.
6. Close Live, uninstall through supported Live UI, and verify no helper process or executable copy
   remains outside Ableton-managed resources. Record whether non-executable receipt storage remains.

If another runtime/toolchain is needed, the Extension becomes a separate identity, storage is lost,
any egress attempt occurs, or cleanup leaves an executable behind, mark that row `FAIL`. Do not repair
the evidence into PASS by renaming folders or deleting residue manually.
