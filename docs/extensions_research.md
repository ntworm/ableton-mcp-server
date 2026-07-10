# Ableton Extensions SDK & MCP Ecosystem Research

This document compiles the research on the new **Ableton Extensions SDK** (introduced in Live 12.4.5 Suite Beta in mid-2026), its capabilities, and how existing community projects use it to interface with AI models (specifically via MCP).

---

## 1. The Ableton Extensions SDK Paradigm

Introduced in **Live 12 Suite Beta 12.4.5+**, the Extensions SDK is an official framework for building custom tools that run natively inside Ableton Live. 

### Key Characteristics:
* **Stack**: JavaScript / TypeScript / Node.js.
* **Runtime**: Live runs a persistent, sandboxed Node.js Extension Host process alongside the DAW.
* **Packaging**: Extensions are compiled and packaged into `.ablx` files, which users install via **Preferences → Extensions**.
* **Triggering**: Unlike Max for Live devices, Extensions are not loaded onto tracks. They are triggered on-demand via **contextual right-click menus** on clips, tracks, or devices.
* **UI**: Can render custom user interfaces (modal dialogs, floating windows) using HTML/CSS/JS in embedded webviews.

### Key API Classes:
* `LiveSet` — Access track lists, scenes, global parameters.
* `Track` — CRUD operations on tracks, routing, mixer settings.
* `MidiClip` / `AudioClip` — Read and write clip data. Features helper methods like `getNotes()` and `setNotes()` for direct MIDI manipulation.
* `Device` — Access and automate device parameters.

---

## 2. Project Analysis: `Ronvaknins/ableton-extensions-skill`

This project is an **AI Agent Skill** (a prompt-engineering and instruction package) designed to teach coding agents how to build native Ableton extensions.

### Why it exists:
Because the Extensions SDK is brand new, AI models have no training data on it. They hallucinate non-existent API endpoints and wrong scaffolding structures. This skill primes the AI with:
1. Correct TypeScript API references.
2. Scaffolding structures (`package.json`, `tsconfig.json`, `extension.json`, `src/`).
3. Compilation and packaging workflows (`pnpm build`, `pnpm package` -> `.ablx`).

### Proof of Concept ("One Note Chords"):
Includes a working example of a MIDI-transforming extension:
* **Trigger**: Right-click a MIDI clip.
* **Action**: Read clip notes via `getNotes()`.
* **Logic**: Transform single notes into chords.
* **Writeback**: Replace clip notes via `setNotes()`.

---

## 3. Project Analysis: `jasper-zheng/ableton-sdk-mcp` (and `ableton-warping` skill)

This project integrates the Extensions SDK with the Model Context Protocol (MCP) to perform creative audio manipulations.

### Architecture:
Because the Extension Host is sandboxed, an external MCP client cannot access it directly. The project resolves this via a **Loopback Bridge**:
1. The `.ablx` extension starts a local loopback HTTP/WebSocket listener inside Ableton's process.
2. An external Python/Node MCP Server acts as a client, translating natural language prompts into JSON payloads.
3. Payloads are sent to the local port, where the sandboxed Extension Host receives them and executes LOM calls.

### Specific Focus:
Exposes tools through the **`ableton-warping`** skill:
* **Clip Warping**: Toggle clip warping status and set warp modes (Beats, Tones, Complex, etc.).
* **Warp Markers**: Read, create, and modify `warp_markers` inside audio clips.
* **Tempo**: Adjust global song tempo.

---

## 4. Other Relevant Ecosystem Projects

### `OthmanAdi/loophole`
* **What it is**: A general-purpose MCP server built directly on top of the Extensions SDK.
* **How it works**: Uses a single `.ablx` installer to establish a bridge.
* **Capabilities**: Includes a "Loophole Kit" for studio hygiene, gain staging, arrangement, scales, and groove management, plus a "Loophole Bridge" MCP server allowing LLMs to inspect and modify Live Sets directly without legacy Remote Scripts or Max for Live.

### `tiianhk/MaxMSP-MCP-Server`
* **What it is**: An MCP server that bridges LLMs with the **Max/MSP/Jitter** environment (which Jasper Zheng contributes to).
* **Usage**: Allows agentic workflows where an AI agent can explain Max patches, create synthesizers, or build connections within Max.

---

## 5. Architectural Comparison

| Dimension | Legacy MIDI Remote Script (Our `ableton-mcp-server`) | Max for Live (M4L) | New Extensions SDK (`loophole` / `ableton-sdk-mcp`) |
| :--- | :--- | :--- | :--- |
| **Language** | Python | Max MSP Patches / JS | JavaScript / TypeScript (Node.js) |
| **Runtime** | Inside Live (UI Thread) | Inside Live (DSP/UI Threads) | Sandboxed Node.js process alongside Live |
| **User Interface** | Hardware controller mappings | Live Device Rack UI | Natively rendered Webviews (HTML/CSS) |
| **Interfacing** | Custom TCP Socket (JSONL) | TCP/UDP OSC or API | Local loopback HTTP/WebSocket |
| **Scope** | Global transport, LOM control | Real-time DSP, MIDI effects, instruments | Set hygiene, clip/track CRUD, file I/O |
| **Stability** | Semi-brittle (uses private Python APIs) | Highly stable | Officially documented contract |

---

## 6. Synthesis & Integration Roadmap for `ableton-mcp-server`

To provide the ultimate Ableton developer experience, we can merge these paradigms. Instead of choosing between **runtime control** and **extension building**, our MCP server should do **both**.

### Tier 1: Extension SDK Knowledge Injection (Low Effort)
Expose the Extensions SDK docs and best practices as **MCP Resources**.
* **Resource**: `resources://extensions/sdk_reference` (Returns the markdown documentation from the skill).
* **Prompt**: `prompts/scaffold_extension` (System prompt to guide the AI in generating TypeScript code for a specific right-click menu action).

### Tier 2: Scaffolding and Build Tools (Medium Effort)
Implement Python CLI tools and MCP tools to automate the development pipeline:
* `scaffold_extension(name, author)`: Creates the project directories, template files, and `package.json`.
* `build_extension(path)`: Shells out to `pnpm build` to compile the TypeScript code.
* `package_extension(path)`: Shells out to `pnpm package` to create the final `.ablx` file.

### Tier 3: The Runtime-to-Extension Bridge (High Effort)
Allow the AI to prototype actions using our runtime Python tools (which offer instant feedback), and then automatically codify them into a TypeScript extension.
1. **Prototype**: Agent runs `add_notes_to_clip` to verify a MIDI harmonizer logic.
2. **Translate**: Agent translates the Python code to TypeScript.
3. **Compile**: Agent packages it as an `.ablx` file so the user can permanently run it from a right-click menu.
