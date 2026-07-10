# PLAN: Ableton MCP Server v0.3.0 — The Unified Super Bridge & Agentic Skill

This document is the master engineering specification and implementation plan for upgrading **`ableton-mcp-server`** from **v0.2.1** to **v0.3.0**. 

It details the transition from a runtime debug/inspection tool into a **unified music production copilot, composition analyzer, and Extensions SDK development environment**.

---

## 1. Executive Summary & Objective

The objective of **v0.3.0** is to expand the AI agent's agency from simple transport operations and MIDI note writes into **complete set diagnostics, guarded track/device CRUD, and native Ableton Live Extension development**. 

Rather than choosing between a MIDI Remote Script (Python) or the new Extensions SDK (TypeScript), v0.3.0 implements a **Hybrid Dual-Bridge Architecture** that utilizes both communication paths. This enables the AI agent to:
1. **Analyze Compositions**: Read the entire Live Set structure, evaluate MIDI note overlap, scale drift, and arrangement anomalies, and diagnose musical errors.
2. **Execute Guarded Mutations**: Add tracks, rename structures, load devices, and clear states under client-side safety constraints.
3. **Scaffold & Build Extensions**: Prototype logic at runtime via MCP, then compile and package native `.ablx` extensions for permanent installation.
4. **Stream Real-Time telemetry**: Stream transport, selection changes, and internal LOM events directly to the AI client for live diagnostics.

---

## 2. Assessment of Current State (v0.2.1)

In v0.2.1, the system uses a single path-of-execution:
* **Host Component**: A FastMCP server written in Python 3.10+ communicating via `Client` over TCP JSONL (`127.0.0.1:9888`).
* **Ableton Component**: A MIDI Remote Script (`AbletonMCPServer_RemoteScript`) that spins up a background socket thread, parses incoming messages, and queues LOM reads/writes to run on the main UI thread via `update_display` ticks.
* **Limitations**:
  * Destructive/creative commands (e.g., track creation, device loading) are blocked by the `contracts.py` blocklist.
  * No access to the new JavaScript/TypeScript Extensions SDK features.
  * No mechanism to read/write audio warping modes or warp markers (essential for audio manipulation).
  * No logging or event-driven feedback; the server must poll to discover changes.

---

## 3. Analysis of Research Findings

Our research of the Ableton developer ecosystem revealed three critical models:

### 3.1 `Ronvaknins/ableton-extensions-skill`
* **Finding**: Proves that AI models fail to write valid Extensions SDK code due to lack of training data.
* **Mechanism**: Uses a structured instruction set (`SKILL.md`) that maps SDK classes like `LiveSet`, `Track`, `MidiClip`, and `AudioClip`.
* **API Details**:
  * `MidiClip.getNotes()` and `MidiClip.setNotes()` manipulate notes using an array of `Note` objects.
  * Manifest keys in `extension.json` define right-click context menu hooks under `"actions"`.

### 3.2 `jasper-zheng/ableton-sdk-mcp` (and `ableton-warping` skill)
* **Finding**: Shows how to bridge the sandboxed Extensions environment.
* **Mechanism**: Because the Node.js Extension Host runs in a strict sandbox, the extension must host a loopback HTTP/WebSocket listener internally.
* **API Details**: Exposes warp controls:
  * `AudioClip.warping` (Boolean).
  * `AudioClip.warp_mode` (Enum: `Beats`, `Tones`, `Texture`, `Re-Pitch`, `Complex`, `Complex Pro`).
  * `AudioClip.warp_markers` (Array of time-to-beat mappings).

### 3.3 `OthmanAdi/loophole`
* **Finding**: Exposes a clean, direct MCP server architecture utilizing ONLY the Extensions SDK.
* **Mechanism**: A single `.ablx` file handles the bridge. It provides "kit tools" (set hygiene, arrangement, gain staging) and "bridge tools" (LOM access).

---

## 4. Architectural Specification (The Hybrid Dual-Bridge)

To leverage both paradigms, v0.3.0 implements the following topology:

```text
                      ┌──────────────────────────────────────┐
                      │             AI Agent                 │
                      └──────────────────┬───────────────────┘
                                         │ (stdio MCP)
                      ┌──────────────────▼───────────────────┐
                      │    FastMCP Server (Python 3.10+)     │
                      └──────────┬───────────────────┬───────┘
                                 │                   │
            (TCP JSONL: 9888)    │                   │ (WebSockets JSON-RPC: 9889)
  ┌──────────────────────────────▼───┐   ┌───────────▼──────────────────────┐
  │   Ableton Remote Script (Py)     │   │   Node.js Extension Host (.ablx) │
  │   - UI-Tick request queue        │   │   - Local Loopback WS Server      │
  │   - Fast MIDI insertion          │   │   - Context Menus & Webviews     │
  │   - Backward compatibility       │   │   - Warp Marker Manipulation     │
  └──────────────────────────────────┘   └──────────────────────────────────┘
```

### 4.1 Thread Safety & Communication Mechanics
1. **MIDI Remote Script (TCP JSONL)**:
   * Runs inside Live's Python interpreter.
   * Background thread reads from `127.0.0.1:9888`.
   * Pushes commands to a thread-safe Queue.
   * `update_display()` pops one command per tick, executes LOM reads/writes, yields if deferred state verification is required, and pushes the result back to the client.
2. **Extensions SDK Host (WebSockets)**:
   * Runs inside Live's Node.js engine.
   * Compiles TS/JS that boots a loopback WebSocket server on `127.0.0.1:9889`.
   * Because Node.js is inherently asynchronous and event-driven, requests to the LOM do not require a custom queue/tick yield machine; they can resolve via standard JS `async/await` patterns native to the SDK.
3. **Python MCP Orchestrator**:
   * The server acts as a unified client.
   * Resolves the target bridge based on command type (e.g., transport changes go via TCP, warping edits go via WebSockets).
   * Maps responses from both channels to unified Pydantic schemas.

---

## 5. Detailed Feature Specifications & New MCP Tools

### 5.1 Composition Diagnostics & Timing Tools

#### Tool: `diagnose_midi_clip`
* **Description**: Scan a MIDI clip to find composition errors (overlapping notes, timing issues, notes outside scale).
* **Input Schema (Pydantic)**:
  ```python
  class DiagnoseMidiClipInput(BaseModel):
      track_path_id: str
      clip_index: int
      scale_root: Optional[str] = None # e.g. "C"
      scale_type: Optional[str] = None # e.g. "Major"
  ```
* **Output Schema**:
  ```python
  class DiagnoseMidiClipOutput(BaseModel):
      has_overlaps: bool
      overlaps_count: int
      notes_outside_scale: List[Dict[str, Any]]
      timing_drift_detected: bool
      recommendations: List[str]
  ```
* **Live Implementation**:
  1. Retrieve MIDI notes via `get_clip_notes` Remote Script command.
  2. Parse the list of `(pitch, start_time, duration, velocity, muted)` tuples.
  3. Sort notes by `start_time` and check if any notes on the same pitch overlap (`current_start < previous_start + previous_duration`).
  4. Compare pitches to scale notes (using standard interval mapping).
  5. Check if notes are strictly quantized to grid values (1/16, 1/8, etc.) or if they show drift (`time % grid_duration > threshold`).

#### Tool: `get_composition_structure`
* **Description**: Retrieve the track layout, scene groupings, and empty clips.
* **Input Schema**: None.
* **Output Schema**:
  ```python
  class GetCompositionStructureOutput(BaseModel):
      tracks: List[Dict[str, Any]]
      scenes_count: int
      tempo_automation_exists: bool
      unnamed_tracks: List[str]
  ```

---

### 5.2 Controlled Creative Mutations

#### Tool: `create_midi_track_guarded`
* **Description**: Add a new MIDI track to the set.
* **Input Schema**:
  ```python
  class CreateMidiTrackInput(BaseModel):
      track_name: str
      index: Optional[int] = None
  ```
* **Safety Rules**:
  * Remote script side checks if `len(self.song.tracks) >= 96` (prevents Ableton UI lag).
  * Limits generation to MIDI tracks (audio track insertion blocked).

#### Tool: `load_device_to_track`
* **Description**: Load a specific device/plug-in onto a track using the Extensions SDK browser API.
* **Input Schema**:
  ```python
  class LoadDeviceInput(BaseModel):
      track_path_id: str
      device_name: str
  ```
* **WebSocket Payload**:
  ```json
  {
    "jsonrpc": "2.0",
    "method": "loadDevice",
    "params": {
      "trackPathId": "track:2",
      "deviceName": "Operator"
    },
    "id": 1
  }
  ```

---

### 5.3 Extension SDK Scaffolding & Building

#### Tool: `scaffold_extension`
* **Description**: Create a template Ableton Extension folder.
* **Input Schema**:
  ```python
  class ScaffoldExtensionInput(BaseModel):
      name: str
      author: str
      output_directory: str
  ```
* **Scaffolded File Structure**:
  * `package.json`: Contains SDK package dependencies and build configurations.
    ```json
    {
      "name": "my-extension",
      "version": "1.0.0",
      "devDependencies": {
        "@ableton/extensions-sdk": "^1.0.0-beta.0",
        "typescript": "^5.0.0"
      },
      "scripts": {
        "build": "tsc",
        "package": "ableton-package-extension"
      }
    }
    ```
  * `tsconfig.json`: Target configuration.
    ```json
    {
      "compilerOptions": {
        "target": "ES2022",
        "module": "NodeNext",
        "strict": true,
        "outDir": "./dist"
      }
    }
    ```
  * `extension.json`: Ableton Extension manifest definition.
    ```json
    {
      "$schema": "https://ableton.github.io/extensions-sdk/schema.json",
      "name": "My Extension",
      "author": "Author",
      "actions": [
        {
          "id": "my_action",
          "name": "My Action",
          "context": "clip"
        }
      ]
    }
    ```
  * `src/index.ts`: Boilerplate TS code.

#### Tool: `build_extension`
* **Description**: Run Node.js build to compile an extension project.
* **Input Schema**:
  ```python
  class BuildExtensionInput(BaseModel):
      project_path: str
  ```
* **Execution**: Runs `pnpm install` followed by `pnpm run build` using the Windows host subprocess shell.

---

### 5.4 WebSocket Loopback Bridge Tools

#### Tool: `get_warp_state`
* **Description**: Retrieve warping status, warp mode, and warp markers of an audio clip.
* **Input Schema**:
  ```python
  class GetWarpStateInput(BaseModel):
      track_path_id: str
      clip_index: int
  ```
* **WebSocket Query**:
  ```json
  {"jsonrpc": "2.0", "method": "getWarpState", "params": {"track": 2, "clip": 0}, "id": 2}
  ```

#### Tool: `set_warp_state`
* **Description**: Modify warp parameters and write warp markers.
* **Input Schema**:
  ```python
  class SetWarpStateInput(BaseModel):
      track_path_id: str
      clip_index: int
      warping: bool
      warp_mode: str # Beats, Tones, Complex, etc.
      warp_markers: Optional[List[Dict[str, float]]] = None
  ```

---

### 5.5 Real-Time Event Streamer & Debugger

#### Tool: `start_event_stream`
* **Description**: Establish a WebSocket channel that listens for LOM changes (tempo, clip slot selections, added tracks) and streams them to the AI agent.
* **Implementation**: Uses Python `websockets` library inside `client.py` to keep a persistent socket open, broadcasting events to the FastMCP logging console.

---

## 6. Detailed Code & File Changes

To complete the implementation, the following files will be created or modified.

### 6.1 `pyproject.toml`
* **Modification**: Add `websockets` dependency for python-side WebSocket server management. Add Node execution commands configuration.
```toml
[project]
dependencies = [
    "mcp>=1.28,<2",
    "fastmcp>=3.4,<4",
    "pydantic>=2.12,<3",
    "websockets>=11.0", # NEW for loopback WebSocket client
]
```

### 6.2 `contracts.py`
* **Modification**: Add new commands to allowlists and define constants for the hybrid WebSocket path.
```python
# New allowed read commands
READ_COMMANDS.update({
    "get_composition_structure",
    "get_warp_state",
    "get_lom_events",
})

# New allowed mutation commands
ALLOWED_MUTATIONS.update({
    "create_midi_track_guarded",
    "load_device_to_track",
    "set_warp_state",
    "rename_track_or_clip",
    "clear_track_state",
})

# Define targets for routing
WEBSOCKET_TARGET_COMMANDS = {
    "get_warp_state",
    "set_warp_state",
    "load_device_to_track",
}
```

### 6.3 `ableton_mcp_server/client.py`
* **Modification**: Rewrite `Client` to support dual communication. When a command belongs to `WEBSOCKET_TARGET_COMMANDS`, route it to `127.0.0.1:9889` using `websockets.connect()`. Otherwise, route it to `127.0.0.1:9888` using the raw TCP socket client.

```python
import socket
import json
import asyncio
import websockets
from ableton_mcp_server.protocol import Request, Response
from ableton_mcp_server.contracts import WEBSOCKET_TARGET_COMMANDS

class HybridClient:
    def __init__(self, host: str = "127.0.0.1", tcp_port: int = 9888, ws_port: int = 9889):
        self.host = host
        self.tcp_port = tcp_port
        self.ws_port = ws_port

    async def send_command(self, cmd_type: str, params: dict) -> dict:
        if cmd_type in WEBSOCKET_TARGET_COMMANDS:
            return await self._send_websocket(cmd_type, params)
        else:
            return self._send_tcp(cmd_type, params)

    async def _send_websocket(self, method: str, params: dict) -> dict:
        uri = f"ws://{self.host}:{self.ws_port}"
        async with websockets.connect(uri) as websocket:
            payload = {
                "jsonrpc": "2.0",
                "method": method,
                "params": params,
                "id": 1
            }
            await websocket.send(json.dumps(payload))
            response = await websocket.recv()
            res_data = json.loads(response)
            if "error" in res_data:
                raise Exception(res_data["error"]["message"])
            return res_data["result"]

    def _send_tcp(self, cmd_type: str, params: dict) -> dict:
        # Standard socket connection logic to port 9888...
        pass
```

### 6.4 `ableton_mcp_server/server.py`
* **Modification**: Add the new FastMCP tools.

```python
from mcp.server.fastmcp import FastMCP
from ableton_mcp_server.client import HybridClient
from ableton_mcp_server.models import (
    DiagnoseMidiClipInput, GetCompositionStructureOutput,
    CreateMidiTrackInput, GetWarpStateInput, SetWarpStateInput
)

mcp = FastMCP("AbletonMCPServer")
client = HybridClient()

@mcp.tool()
async def get_composition_structure() -> str:
    """Retrieve the track layout, scene groupings, and composition properties."""
    res = await client.send_command("get_composition_structure", {})
    return json.dumps(res, indent=2)

@mcp.tool()
async def diagnose_midi_clip(track_path_id: str, clip_index: int) -> str:
    """Scan a midi clip for overlapping notes, notes outside scale, and quantization issues."""
    params = {"track_path_id": track_path_id, "clip_index": clip_index}
    res = await client.send_command("diagnose_midi_clip", params)
    return json.dumps(res, indent=2)

@mcp.tool()
async def create_midi_track(name: str) -> str:
    """Create a new MIDI track inside Ableton Live under safe constraints."""
    params = {"name": name}
    res = await client.send_command("create_midi_track_guarded", params)
    return json.dumps(res, indent=2)

@mcp.tool()
async def get_warp_state(track_path_id: str, clip_index: int) -> str:
    """Retrieve warping modes, status, and warp markers of an audio clip."""
    params = {"track_path_id": track_path_id, "clip_index": clip_index}
    res = await client.send_command("get_warp_state", params)
    return json.dumps(res, indent=2)
```

### 6.5 `AbletonMCPServer_RemoteScript/__init__.py`
* **Modification**: Add command handlers in the Python Remote Script dispatch loop.
```python
def handle_create_midi_track_guarded(self, params):
    name = params.get("name", "MIDI Track")
    if len(self.song.tracks) >= 96:
        raise Exception("TRACK_LIMIT_REACHED")
    self.song.create_midi_track(-1)
    new_track = self.song.tracks[-1]
    new_track.name = name
    return {"status": "ok", "track_index": len(self.song.tracks) - 1}

def handle_diagnose_midi_clip(self, params):
    # Retrieve notes and scan for composition errors
    pass
```

### 6.6 `AbletonMCPServer_Extension/` (The TypeScript Component)
* **Description**: Create this folder inside the repository to package the Extension Host bridge code.
* **`src/index.ts`**:
```typescript
import { ExtensionHost } from '@ableton/extensions-sdk';
import { WebSocketServer } from 'ws';

const host = new ExtensionHost();
const wss = new WebSocketServer({ port: 9889 });

wss.on('connection', (ws) => {
  ws.on('message', async (message) => {
    const request = JSON.parse(message.toString());
    const { method, params, id } = request;

    try {
      let result;
      if (method === 'getWarpState') {
        result = await handleGetWarpState(params);
      } else if (method === 'setWarpState') {
        result = await handleSetWarpState(params);
      } else if (method === 'loadDevice') {
        result = await handleLoadDevice(params);
      }
      ws.send(JSON.stringify({ jsonrpc: '2.0', result, id }));
    } catch (err: any) {
      ws.send(JSON.stringify({ jsonrpc: '2.0', error: { message: err.message }, id }));
    }
  });
});

async function handleGetWarpState(params: any) {
  const clip = await host.liveSet.getTrack(params.track).getClip(params.clip);
  return {
    warping: clip.warping,
    warpMode: clip.warpMode,
    warpMarkers: clip.warpMarkers
  };
}
```

---

## 7. Verification & Testing Plan

### 7.1 Automated Offline Mocking
* Modify `scripts/mock_remote_script.py` to also spin up a mock WebSocket loopback server on port `9889`.
* Ensure it returns fake responses for `getWarpState` and `loadDevice`.
* Add `tests/test_websocket_bridge.py` to verify connection retry logic and correct target routing:
  ```bash
  python -m pytest tests/test_websocket_bridge.py
  ```

### 7.2 LOM Diagnostic Verification
* Add `tests/test_diagnostics.py` to verify note-overlap scans. Provide fake lists of overlapping note coordinates and assert that `diagnose_midi_clip` identifies exactly which start times are conflicting.

### 7.3 Guarded Live Acceptance Test
Update `tests/acceptance.py` to include:
* Creating a MIDI track.
* Writing MIDI notes and verifying them.
* Scanning the clip to verify no overlaps exist.
* Querying warping settings (requires an audio clip fixture).
* Cleaning up/deleting the created track.

---

## 8. Known Edge Cases & Mitigations

### 8.1 Live UI Thread Blocking (TypeScript)
* **Risk**: Node WebSocket servers can trigger high CPU usage if connection loops are not properly garbage collected, causing Ableton's UI frame rate to drop.
* **Mitigation**: Use connection timeouts and force client cleanups. Limit the Extension Host WebSocket listener queue execution rate.

### 8.2 Path-ID Resolution Conflicts
* **Risk**: If the user modifies track structure while the AI is analyzing, the path-id (e.g., `track:2/clipslot:4`) becomes stale.
* **Mitigation**: Standardize error codes so that any `STALE_REFERENCE` triggers an automatic re-scan of the set layout in the client.

### 8.3 Sandboxed File Write Limitations
* **Risk**: The Extensions SDK cannot write compiled `.ablx` files directly to the User Library folders due to security sandboxing.
* **Mitigation**: The python MCP server (running outside the sandbox) handles the file copying and directory moves, while the sandboxed SDK only handles internal LOM executions.
