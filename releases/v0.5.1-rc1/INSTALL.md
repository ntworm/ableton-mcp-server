# Install v0.5.1-rc1

These release candidates install on the owner machine only. Do not run them from a CI environment.

## Python wheel

```
pip install releases/v0.5.1-rc1/ableton_mcp_server-0.5.1-py3-none-any.whl
```

## MIDI Remote Script

Extract `AbletonMCPServer_RemoteScript-0.5.1.zip` into your Live MIDI Remote Scripts folder, e.g.
`%USERPROFILE%\Documents\Ableton\User Library\Remote Scripts\`.

## Extension Host

Drop `AbletonMCPServer-Extension-0.5.1.ablx` into the Live Extensions folder. The Extension binds the WebSocket bridge to `127.0.0.1:9889` (loopback only).

## Verification

After install:

```
.venv-win\Scripts\ableton-mcp.exe install-status --json
.venv-win\Scripts\ableton-mcp.exe doctor --json
```

Then open the disposable Set `TESTE_CODEX` and run the gated baseline certification (owner-driven; see RELEASE-NOTES.md).
