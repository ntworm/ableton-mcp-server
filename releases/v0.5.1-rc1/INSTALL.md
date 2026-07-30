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

### 1. Preferred Installation Flow (Auto)
Double-click `AbletonMCPServer-Extension-0.5.1.ablx` or drag and drop it directly into the Ableton Live window to let Ableton install the extension automatically.

### 2. Manual Extraction Fallback
If the preferred flow fails or is not supported by your Live version, you can manually extract/unzip the `.ablx` file (which is a zip archive) into the following directory:
- **Windows**: `%LOCALAPPDATA%\Ableton\Extensions\ntworm.abletonmcpserver-extension`
- **macOS**: `~/Library/Application Support/Ableton/Extensions/ntworm.abletonmcpserver-extension`

## Restarting Requirement
**CRITICAL**: You MUST completely close and restart Ableton Live for the new Extension and MIDI Remote Script to be registered and loaded.

## Verification
1. Verify that `manifest.json` in the installed extension folder displays the correct version and metadata.
2. Ensure the installed files match the hashes in `SHA256SUMS`.
3. Run the following status commands to check the installation:
```
.venv-win\Scripts\ableton-mcp.exe install-status --json
.venv-win\Scripts\ableton-mcp.exe doctor --json
```

Then open the disposable Set `TESTE_CODEX` and run the gated baseline certification (owner-driven; see RELEASE-NOTES.md).
