# Groove Brain Gate 0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove, before any corpus or model work, that one Windows `.ablx` can contain a local web UI and native helper, launch them from a contextual Ableton Extension action, perform one explicitly confirmed non-destructive Session MIDI write/readback, and shut down without external runtime dependencies or orphan processes.

**Architecture:** Build an isolated Gate 0 Extension under the existing Extension project so it reuses the vendored beta SDK/CLI and current `node_modules` without changing the released MCP Extension entrypoint. A Rust helper binds atomically to `127.0.0.1:0`, serves bundled static UI, authenticates health requests, and exits on parent-pipe EOF; the Extension alone owns Live SDK handles and MIDI mutation. The artifact is promoted only by a binary stop/go matrix on a clean offline machine.

**Tech Stack:** Ableton Extensions SDK/CLI `1.0.0-beta.0`, Extension Host Node.js 24, TypeScript 5.9, esbuild, Node native test runner through `tsx`, Rust 1.96, `serde 1.0.229`, `serde_json 1.0.151`, `subtle 2.6.1`, Python 3.10+ for archive verification, pytest 9, PowerShell 7/Windows PowerShell for operator evidence.

---

## Hard stop and scope

This plan implements only Gate 0. It does not ingest MIDI, train a model, bundle ONNX, build the final dashboard, support Arrangement writeback, inspect Superior Drummer, modify the existing MCP transport, publish, or release.

Stop after Task 10 unless every required Gate 0 row is `PASS`. A failure in resource discovery, helper execution, modal lifecycle, safe write/readback, offline operation, crash cleanup, update behavior, or single-install operation returns the architecture to design. Installing Python, Node, Rust, MCP Server, Remote Script, CUDA, a service, or a second product on the clean user machine is not an allowed workaround.

The implementation should remain on the current checkout because the owner previously required one central `main`; do not create another worktree for this planning lineage. Preserve all unrelated dirty files and stage exact task paths only.

## Compatibility contract to freeze before implementation

Record these values in every evidence packet:

- Windows edition/build and architecture;
- Ableton Live executable version and beta build;
- Extension Host `process.version`, `process.platform`, and `process.arch`;
- SHA-256 of the vendored SDK and CLI tarballs;
- Git commit under test;
- Rust compiler and Cargo versions used to build the helper;
- `.ablx` SHA-256, compressed bytes, installed bytes, and full entry inventory.

The vendored CLI README requires Node 24.14.1 or newer, while the currently observed developer shell reports Node 24.13.1. Do not silently accept this mismatch. Task 1 records it; Task 3 packaging uses the exact Node executable and records whether the CLI succeeds. The Extension Host's own Node version is separate and must be measured inside Live.

## File ownership map

The Gate 0 spike is isolated under `AbletonMCPServer_Extension/groove-brain-gate0/`.

| Path | Responsibility | Read by |
|---|---|---|
| `AbletonMCPServer_Extension/package.json` | Gate 0 test/build/package scripts only | npm |
| `AbletonMCPServer_Extension/groove-brain-gate0/manifest.json` | source manifest template | `build.ts`, `package.ts` |
| `AbletonMCPServer_Extension/groove-brain-gate0/tsconfig.json` | strict Gate 0 typecheck | `tsc -p` |
| `AbletonMCPServer_Extension/groove-brain-gate0/build.ts` | bundles the isolated Extension entry | `npm run gate0:build` |
| `AbletonMCPServer_Extension/groove-brain-gate0/package.ts` | builds helper, stages assets, invokes vendored CLI, writes runtime hash | `npm run gate0:package` |
| `AbletonMCPServer_Extension/groove-brain-gate0/src/resource-path.ts` | resolves installed resource root from entry directory | `helper-process.ts` |
| `AbletonMCPServer_Extension/groove-brain-gate0/src/protocol.ts` | bootstrap, ready, modal, and receipt types/parsers | Extension/helper integration |
| `AbletonMCPServer_Extension/groove-brain-gate0/src/helper-process.ts` | hash verification, spawn, readiness, health, shutdown | `actions.ts` |
| `AbletonMCPServer_Extension/groove-brain-gate0/src/session-clip-probe.ts` | fail-closed Session write/readback state machine | `actions.ts`, unit tests |
| `AbletonMCPServer_Extension/groove-brain-gate0/src/sdk-slot-adapter.ts` | adapts an SDK `ClipSlot`/`MidiClip` to the testable port | `actions.ts` |
| `AbletonMCPServer_Extension/groove-brain-gate0/src/receipt-store.ts` | writes redacted evidence to Extension storage | `actions.ts` |
| `AbletonMCPServer_Extension/groove-brain-gate0/src/actions.ts` | contextual action, modal, confirmation, probe, result UI | `extension.ts` |
| `AbletonMCPServer_Extension/groove-brain-gate0/src/extension.ts` | isolated Extension activate/deactivate lifecycle | esbuild entry |
| `AbletonMCPServer_Extension/groove-brain-gate0/ui/index.html` | static modal shell | Rust helper exact route `/` |
| `AbletonMCPServer_Extension/groove-brain-gate0/ui/app.js` | fragment bootstrap, authenticated health, explicit close/result | `index.html` |
| `AbletonMCPServer_Extension/groove-brain-gate0/ui/styles.css` | local-only Ableton-like presentation | `index.html` |
| `AbletonMCPServer_Extension/groove-brain-gate0/helper/Cargo.toml` and `AbletonMCPServer_Extension/groove-brain-gate0/helper/Cargo.lock` | reproducible helper dependencies | Cargo |
| `AbletonMCPServer_Extension/groove-brain-gate0/helper/src/protocol.rs` | stdin bootstrap/shutdown types and validation | Rust `main.rs` |
| `AbletonMCPServer_Extension/groove-brain-gate0/helper/src/server.rs` | exact static/health HTTP routes and security headers | Rust `main.rs` |
| `AbletonMCPServer_Extension/groove-brain-gate0/helper/src/main.rs` | bind, ready handshake, stdin EOF watchdog, server loop | native executable |
| `AbletonMCPServer_Extension/groove-brain-gate0/tests/resource-path.test.ts`, `helper-process.test.ts`, `modal-result.test.ts`, and `session-clip-probe.test.ts` | Node unit/integration coverage | `npm run gate0:test` |
| `scripts/gate0/verify_groove_brain_ablx.py` | deterministic archive/hash/size verification | pytest and operator commands |
| `tests/test_groove_brain_gate0_package.py` | verifier and source contract tests | pytest |
| `scripts/gate0/collect_gate0_evidence.ps1` | clean-machine evidence capture outside Git | operator runbook |
| `docs/groove-brain/gate0-runbook.md` | destructive-safe Live/manual matrix | operator |
| `docs/reports/2026-08-30-groove-brain-gate0-result.md` | final stop/go summary, created only in Task 10 | owner review |

Generated files remain outside Git:

- `AbletonMCPServer_Extension/build/groove-brain-gate0/` — staged roots and `.ablx` files;
- Cargo target directory under that build root;
- clean-machine evidence under `C:\Users\Usuario\repos\_release-artifacts\groove-brain-gate0\<run-id>`.

## Task 1: Isolated TypeScript scaffold and deterministic resource path

**Files:**
- Modify: `AbletonMCPServer_Extension/package.json`
- Create: `AbletonMCPServer_Extension/groove-brain-gate0/manifest.json`
- Create: `AbletonMCPServer_Extension/groove-brain-gate0/tsconfig.json`
- Create: `AbletonMCPServer_Extension/groove-brain-gate0/build.ts`
- Create: `AbletonMCPServer_Extension/groove-brain-gate0/src/resource-path.ts`
- Create: `AbletonMCPServer_Extension/groove-brain-gate0/tests/resource-path.test.ts`

- [ ] **Step 1: Write the failing resource-path test**

```ts
import assert from 'node:assert/strict';
import path from 'node:path';
import test from 'node:test';
import { resourceRootFromEntryDir } from '../src/resource-path.js';

test('resource root is the parent of installed dist and ignores cwd', () => {
  const installedRoot = path.resolve('C:/Gate0 Installed/Groove Brain');
  const entryDir = path.join(installedRoot, 'dist');
  assert.equal(resourceRootFromEntryDir(entryDir), installedRoot);
});
```

- [ ] **Step 2: Add only the initial npm scripts and run the red test**

Add these keys to the existing `scripts` object without changing existing scripts:

```json
"gate0:typecheck": "tsc -p groove-brain-gate0/tsconfig.json --noEmit",
"gate0:test": "tsx --test groove-brain-gate0/tests/*.test.ts",
"gate0:build": "npm run gate0:typecheck && tsx groove-brain-gate0/build.ts"
```

Run:

```powershell
cd AbletonMCPServer_Extension
npm run gate0:test
```

Expected: FAIL because `src/resource-path.ts` does not exist.

- [ ] **Step 3: Create the source manifest and strict TypeScript config**

`manifest.json`:

```json
{
  "name": "Groove Brain Gate 0",
  "author": "ntworm",
  "entry": "dist/extension.js",
  "version": "0.1.0",
  "minimumApiVersion": "1.0.0"
}
```

`tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "esModuleInterop": true,
    "strict": true,
    "skipLibCheck": true,
    "types": ["node"],
    "noEmit": true
  },
  "include": ["src/**/*.ts", "tests/**/*.ts", "build.ts", "package.ts"]
}
```

- [ ] **Step 4: Implement the resource resolver**

```ts
import path from 'node:path';

export function resourceRootFromEntryDir(entryDir: string): string {
  if (!path.isAbsolute(entryDir)) {
    throw new Error('ENTRY_DIR_NOT_ABSOLUTE');
  }
  return path.resolve(entryDir, '..');
}
```

- [ ] **Step 5: Create the isolated esbuild entry build**

```ts
import * as esbuild from 'esbuild';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.dirname(fileURLToPath(import.meta.url));
const manifest = JSON.parse(fs.readFileSync(path.join(root, 'manifest.json'), 'utf8')) as {
  entry: string;
};

await esbuild.build({
  entryPoints: [path.join(root, 'src', 'extension.ts')],
  outfile: path.join(root, manifest.entry),
  bundle: true,
  format: 'cjs',
  platform: 'node',
  target: 'node24',
  sourcesContent: false,
  sourcemap: false,
  logLevel: 'info',
});
```

Do not run `gate0:build` until Task 5 creates `src/extension.ts`.

- [ ] **Step 6: Run the focused green test and typecheck the files that exist**

```powershell
npm run gate0:test
npx tsc --noEmit --strict --target ES2022 --module NodeNext --moduleResolution NodeNext groove-brain-gate0/src/resource-path.ts groove-brain-gate0/tests/resource-path.test.ts
```

Expected: both commands PASS.

- [ ] **Step 7: Commit the isolated scaffold**

```powershell
git add AbletonMCPServer_Extension/package.json AbletonMCPServer_Extension/groove-brain-gate0/manifest.json AbletonMCPServer_Extension/groove-brain-gate0/tsconfig.json AbletonMCPServer_Extension/groove-brain-gate0/build.ts AbletonMCPServer_Extension/groove-brain-gate0/src/resource-path.ts AbletonMCPServer_Extension/groove-brain-gate0/tests/resource-path.test.ts
git commit -m "test: scaffold Groove Brain Gate 0 extension"
```

## Task 2: Native helper bootstrap, HTTP security, and parent-death behavior

**Files:**
- Create: `AbletonMCPServer_Extension/groove-brain-gate0/helper/Cargo.toml`
- Create: `AbletonMCPServer_Extension/groove-brain-gate0/helper/Cargo.lock`
- Create: `AbletonMCPServer_Extension/groove-brain-gate0/helper/src/protocol.rs`
- Create: `AbletonMCPServer_Extension/groove-brain-gate0/helper/src/server.rs`
- Create: `AbletonMCPServer_Extension/groove-brain-gate0/helper/src/main.rs`

- [ ] **Step 1: Create the pinned helper manifest**

```toml
[package]
name = "groove-brain-gate0-helper"
version = "0.1.0"
edition = "2024"
license = "MIT"

[dependencies]
serde = { version = "=1.0.229", features = ["derive"] }
serde_json = "=1.0.151"
subtle = "=2.6.1"

[profile.release]
lto = true
codegen-units = 1
panic = "abort"
strip = true
```

Run the following once and commit the generated lock. Do not use floating Git dependencies:

```powershell
cargo generate-lockfile --manifest-path AbletonMCPServer_Extension/groove-brain-gate0/helper/Cargo.toml
```

- [ ] **Step 2: Write protocol validation tests first**

Place these tests at the bottom of `protocol.rs` before its implementation:

```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_wrong_protocol() {
        let raw = r#"{"type":"bootstrap","protocol":2,"token":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","ui_dir":"C:\\ui","parent_pid":42}"#;
        assert_eq!(parse_bootstrap(raw).unwrap_err(), "UNSUPPORTED_PROTOCOL");
    }

    #[test]
    fn rejects_short_or_non_hex_token() {
        let short = r#"{"type":"bootstrap","protocol":1,"token":"abc","ui_dir":"C:\\ui","parent_pid":42}"#;
        assert_eq!(parse_bootstrap(short).unwrap_err(), "INVALID_TOKEN");
    }
}
```

Run:

```powershell
cargo test --target-dir AbletonMCPServer_Extension/build/groove-brain-gate0/cargo-target --manifest-path AbletonMCPServer_Extension/groove-brain-gate0/helper/Cargo.toml
```

Expected: FAIL because the types and `parse_bootstrap` do not exist.

- [ ] **Step 3: Implement the complete stdin protocol**

```rust
use serde::{Deserialize, Serialize};
use std::path::PathBuf;

pub const PROTOCOL_VERSION: u32 = 1;

#[derive(Debug, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum ParentMessage {
    Bootstrap {
        protocol: u32,
        token: String,
        ui_dir: PathBuf,
        parent_pid: u32,
    },
    Shutdown { protocol: u32 },
}

#[derive(Debug)]
pub struct Bootstrap {
    pub token: String,
    pub ui_dir: PathBuf,
    pub parent_pid: u32,
}

#[derive(Debug, Serialize)]
pub struct ReadyMessage {
    pub r#type: &'static str,
    pub protocol: u32,
    pub host: &'static str,
    pub port: u16,
    pub parent_pid: u32,
}

pub fn parse_bootstrap(raw: &str) -> Result<Bootstrap, &'static str> {
    let message: ParentMessage = serde_json::from_str(raw).map_err(|_| "INVALID_JSON")?;
    match message {
        ParentMessage::Bootstrap { protocol, token, ui_dir, parent_pid } => {
            if protocol != PROTOCOL_VERSION {
                return Err("UNSUPPORTED_PROTOCOL");
            }
            if token.len() != 64 || !token.bytes().all(|b| b.is_ascii_hexdigit()) {
                return Err("INVALID_TOKEN");
            }
            if !ui_dir.is_absolute() {
                return Err("UI_DIR_NOT_ABSOLUTE");
            }
            Ok(Bootstrap { token, ui_dir, parent_pid })
        }
        ParentMessage::Shutdown { .. } => Err("BOOTSTRAP_REQUIRED"),
    }
}

pub fn is_shutdown(raw: &str) -> bool {
    matches!(
        serde_json::from_str::<ParentMessage>(raw),
        Ok(ParentMessage::Shutdown { protocol }) if protocol == PROTOCOL_VERSION
    )
}
```

- [ ] **Step 4: Write HTTP parser/auth tests before the server**

At the bottom of `server.rs`:

```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_exact_local_request() {
        let request = parse_request(
            "POST /api/health HTTP/1.1\r\nHost: localhost:45123\r\nOrigin: http://localhost:45123\r\nAuthorization: Bearer aaaa\r\nContent-Length: 0\r\n\r\n",
        )
        .unwrap();
        assert_eq!(request.method, "POST");
        assert_eq!(request.path, "/api/health");
        assert_eq!(request.header("host"), Some("localhost:45123"));
    }

    #[test]
    fn token_comparison_is_exact() {
        assert!(token_matches("Bearer abc", "abc"));
        assert!(!token_matches("Bearer abcd", "abc"));
        assert!(!token_matches("abc", "abc"));
    }

    #[test]
    fn only_known_assets_resolve() {
        assert_eq!(asset_name("/"), Some(("index.html", "text/html; charset=utf-8")));
        assert_eq!(asset_name("/app.js"), Some(("app.js", "text/javascript; charset=utf-8")));
        assert_eq!(asset_name("/../secret"), None);
    }
}
```

Run the same `cargo test --target-dir ... --manifest-path ...` command; expected FAIL because the parser, comparison, and asset resolver are absent.

- [ ] **Step 5: Implement the bounded HTTP server**

```rust
use std::collections::HashMap;
use std::fs;
use std::io::{self, Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::thread;
use std::time::Duration;
use subtle::ConstantTimeEq;

const MAX_HEADER_BYTES: usize = 16 * 1024;
const CSP: &str = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'none'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'";

#[derive(Debug)]
pub struct ParsedRequest {
    method: String,
    path: String,
    headers: HashMap<String, String>,
}

impl ParsedRequest {
    fn header(&self, name: &str) -> Option<&str> {
        self.headers.get(&name.to_ascii_lowercase()).map(String::as_str)
    }
}

pub fn parse_request(raw: &str) -> Result<ParsedRequest, &'static str> {
    let mut lines = raw.split("\r\n");
    let mut first = lines.next().ok_or("MISSING_REQUEST_LINE")?.split_ascii_whitespace();
    let method = first.next().ok_or("MISSING_METHOD")?.to_owned();
    let path = first.next().ok_or("MISSING_PATH")?.to_owned();
    if first.next() != Some("HTTP/1.1") || first.next().is_some() {
        return Err("INVALID_REQUEST_LINE");
    }
    let mut headers = HashMap::new();
    for line in lines.take_while(|line| !line.is_empty()) {
        let (name, value) = line.split_once(':').ok_or("INVALID_HEADER")?;
        headers.insert(name.trim().to_ascii_lowercase(), value.trim().to_owned());
    }
    Ok(ParsedRequest { method, path, headers })
}

pub fn token_matches(header: &str, token: &str) -> bool {
    let expected = format!("Bearer {token}");
    header.as_bytes().ct_eq(expected.as_bytes()).into()
}

pub fn asset_name(path: &str) -> Option<(&'static str, &'static str)> {
    match path {
        "/" => Some(("index.html", "text/html; charset=utf-8")),
        "/app.js" => Some(("app.js", "text/javascript; charset=utf-8")),
        "/styles.css" => Some(("styles.css", "text/css; charset=utf-8")),
        _ => None,
    }
}

fn write_response(
    stream: &mut TcpStream,
    status: &str,
    content_type: &str,
    body: &[u8],
) -> io::Result<()> {
    write!(
        stream,
        "HTTP/1.1 {status}\r\nContent-Type: {content_type}\r\nContent-Length: {}\r\nContent-Security-Policy: {CSP}\r\nX-Content-Type-Options: nosniff\r\nReferrer-Policy: no-referrer\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n",
        body.len()
    )?;
    stream.write_all(body)
}

fn read_headers(stream: &mut TcpStream) -> io::Result<String> {
    stream.set_read_timeout(Some(Duration::from_secs(2)))?;
    let mut data = Vec::with_capacity(1024);
    let mut byte = [0_u8; 1];
    while data.len() < MAX_HEADER_BYTES {
        if stream.read(&mut byte)? == 0 {
            break;
        }
        data.push(byte[0]);
        if data.ends_with(b"\r\n\r\n") {
            return String::from_utf8(data)
                .map_err(|_| io::Error::new(io::ErrorKind::InvalidData, "non-utf8 header"));
        }
    }
    Err(io::Error::new(io::ErrorKind::InvalidData, "header too large or incomplete"))
}

fn handle_connection(
    mut stream: TcpStream,
    ui_dir: &Path,
    token: &str,
    expected_host: &str,
) -> io::Result<()> {
    let raw = match read_headers(&mut stream) {
        Ok(raw) => raw,
        Err(_) => return write_response(&mut stream, "400 Bad Request", "text/plain", b"bad request"),
    };
    let request = match parse_request(&raw) {
        Ok(request) => request,
        Err(_) => return write_response(&mut stream, "400 Bad Request", "text/plain", b"bad request"),
    };
    if request.header("host") != Some(expected_host) {
        return write_response(&mut stream, "403 Forbidden", "text/plain", b"forbidden");
    }
    if request.path == "/api/health" {
        let expected_origin = format!("http://{expected_host}");
        if request.method != "POST" || request.header("origin") != Some(expected_origin.as_str()) {
            return write_response(&mut stream, "403 Forbidden", "text/plain", b"forbidden");
        }
        let authorized = request
            .header("authorization")
            .is_some_and(|value| token_matches(value, token));
        if !authorized {
            return write_response(&mut stream, "401 Unauthorized", "application/json", br#"{"status":"unauthorized"}"#);
        }
        return write_response(
            &mut stream,
            "200 OK",
            "application/json",
            br#"{"status":"ok","protocol":1}"#,
        );
    }
    if request.method != "GET" {
        return write_response(&mut stream, "405 Method Not Allowed", "text/plain", b"method not allowed");
    }
    let Some((name, content_type)) = asset_name(&request.path) else {
        return write_response(&mut stream, "404 Not Found", "text/plain", b"not found");
    };
    let body = fs::read(ui_dir.join(name))?;
    write_response(&mut stream, "200 OK", content_type, &body)
}

pub fn bind_loopback() -> io::Result<TcpListener> {
    let listener = TcpListener::bind("127.0.0.1:0")?;
    listener.set_nonblocking(true)?;
    Ok(listener)
}

pub fn run(
    listener: TcpListener,
    ui_dir: PathBuf,
    token: String,
    shutdown: Arc<AtomicBool>,
) -> io::Result<()> {
    let port = listener.local_addr()?.port();
    let expected_host = format!("localhost:{port}");
    while !shutdown.load(Ordering::Acquire) {
        match listener.accept() {
            Ok((stream, address)) if address.ip().is_loopback() => {
                let _ = handle_connection(stream, &ui_dir, &token, &expected_host);
            }
            Ok(_) => {}
            Err(error) if error.kind() == io::ErrorKind::WouldBlock => {
                thread::sleep(Duration::from_millis(20));
            }
            Err(error) => return Err(error),
        }
    }
    Ok(())
}
```

- [ ] **Step 6: Implement main, ready handshake, shutdown message, and EOF watchdog**

```rust
mod protocol;
mod server;

use protocol::{is_shutdown, parse_bootstrap, ReadyMessage, PROTOCOL_VERSION};
use std::io::{self, Write};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::thread;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut first = String::new();
    if io::stdin().read_line(&mut first)? == 0 {
        return Err("BOOTSTRAP_EOF".into());
    }
    let bootstrap = parse_bootstrap(first.trim_end()).map_err(|code| code.to_owned())?;
    for name in ["index.html", "app.js", "styles.css"] {
        if !bootstrap.ui_dir.join(name).is_file() {
            return Err(format!("MISSING_UI_ASSET:{name}").into());
        }
    }

    let listener = server::bind_loopback()?;
    let port = listener.local_addr()?.port();
    let ready = ReadyMessage {
        r#type: "ready",
        protocol: PROTOCOL_VERSION,
        host: "127.0.0.1",
        port,
        parent_pid: bootstrap.parent_pid,
    };
    println!("{}", serde_json::to_string(&ready)?);
    io::stdout().flush()?;

    let shutdown = Arc::new(AtomicBool::new(false));
    let watcher_flag = Arc::clone(&shutdown);
    thread::spawn(move || loop {
        let mut line = String::new();
        match io::stdin().read_line(&mut line) {
            Ok(0) | Err(_) => {
                watcher_flag.store(true, Ordering::Release);
                break;
            }
            Ok(_) if is_shutdown(line.trim_end()) => {
                watcher_flag.store(true, Ordering::Release);
                break;
            }
            Ok(_) => {}
        }
    });

    server::run(listener, bootstrap.ui_dir, bootstrap.token, shutdown)?;
    Ok(())
}
```

- [ ] **Step 7: Run Rust unit tests, clippy, and release build**

```powershell
cargo test --target-dir AbletonMCPServer_Extension/build/groove-brain-gate0/cargo-target --manifest-path AbletonMCPServer_Extension/groove-brain-gate0/helper/Cargo.toml
cargo clippy --target-dir AbletonMCPServer_Extension/build/groove-brain-gate0/cargo-target --manifest-path AbletonMCPServer_Extension/groove-brain-gate0/helper/Cargo.toml --all-targets -- -D warnings
cargo build --release --locked --target-dir AbletonMCPServer_Extension/build/groove-brain-gate0/cargo-target --manifest-path AbletonMCPServer_Extension/groove-brain-gate0/helper/Cargo.toml
```

Expected: all PASS and `AbletonMCPServer_Extension/build/groove-brain-gate0/cargo-target/release/groove-brain-gate0-helper.exe` exists. No Cargo target is created under the source tree.

- [ ] **Step 8: Commit the native helper**

```powershell
git add AbletonMCPServer_Extension/groove-brain-gate0/helper/Cargo.toml AbletonMCPServer_Extension/groove-brain-gate0/helper/Cargo.lock AbletonMCPServer_Extension/groove-brain-gate0/helper/src/protocol.rs AbletonMCPServer_Extension/groove-brain-gate0/helper/src/server.rs AbletonMCPServer_Extension/groove-brain-gate0/helper/src/main.rs
git commit -m "feat: add loopback Gate 0 helper"
```

## Task 3: Local UI and reproducible `.ablx` packaging

**Files:**
- Modify: `AbletonMCPServer_Extension/package.json`
- Create: `AbletonMCPServer_Extension/groove-brain-gate0/ui/index.html`
- Create: `AbletonMCPServer_Extension/groove-brain-gate0/ui/app.js`
- Create: `AbletonMCPServer_Extension/groove-brain-gate0/ui/styles.css`
- Create: `AbletonMCPServer_Extension/groove-brain-gate0/package.ts`

- [ ] **Step 1: Create an entirely local modal shell**

`index.html`:

```html
<!doctype html>
<html lang="pt-BR">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Groove Brain — Gate 0</title>
    <link rel="stylesheet" href="/styles.css">
  </head>
  <body>
    <main>
      <p class="eyebrow">GROOVE BRAIN / GATE 0</p>
      <h1>Prova local da Extension</h1>
      <p id="status">Autenticando helper local…</p>
      <section id="controls" hidden>
        <p>Esta ação criará um clipe MIDI de quatro beats no Session slot vazio que abriu o painel.</p>
        <label><input id="confirm" type="checkbox"> Confirmo que o slot é descartável e está vazio.</label>
        <button id="run" disabled>Executar write/readback</button>
        <button id="cancel" class="secondary">Cancelar</button>
      </section>
      <pre id="error" role="alert"></pre>
    </main>
    <script src="/app.js" defer></script>
  </body>
</html>
```

`styles.css`:

```css
:root { color-scheme: dark; font: 15px/1.45 Inter, Segoe UI, sans-serif; background: #1d1d1d; color: #efefef; }
body { margin: 0; }
main { max-width: 760px; margin: 0 auto; padding: 48px; }
.eyebrow { color: #ffb347; letter-spacing: .16em; font-size: 12px; }
h1 { font-size: 34px; margin: 8px 0 24px; }
section { display: grid; gap: 18px; padding: 24px; border: 1px solid #444; border-radius: 8px; }
button { border: 0; border-radius: 5px; padding: 12px 18px; background: #ff9f1a; color: #111; font-weight: 700; }
button:disabled { opacity: .4; }
button.secondary { background: #3a3a3a; color: #eee; }
#error { color: #ff7777; white-space: pre-wrap; }
```

- [ ] **Step 2: Implement fragment authentication and the same event path used by the real UI**

```js
const statusNode = document.querySelector('#status');
const controls = document.querySelector('#controls');
const confirmNode = document.querySelector('#confirm');
const runNode = document.querySelector('#run');
const cancelNode = document.querySelector('#cancel');
const errorNode = document.querySelector('#error');

function closeAndSend(payload) {
  const message = { method: 'close_and_send', params: [JSON.stringify(payload)] };
  if (window.chrome?.webview) {
    window.chrome.webview.postMessage(message);
    return;
  }
  if (window.webkit?.messageHandlers?.live) {
    window.webkit.messageHandlers.live.postMessage(message);
    return;
  }
  throw new Error('ABLETON_MODAL_BRIDGE_UNAVAILABLE');
}

async function bootstrap() {
  const token = window.location.hash.slice(1);
  history.replaceState(null, '', window.location.pathname);
  if (!/^[0-9a-f]{64}$/i.test(token)) {
    throw new Error('INVALID_BOOTSTRAP_TOKEN');
  }
  const response = await fetch('/api/health', {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    cache: 'no-store',
  });
  if (!response.ok) {
    throw new Error(`HELPER_HEALTH_${response.status}`);
  }
  const body = await response.json();
  if (body.status !== 'ok' || body.protocol !== 1) {
    throw new Error('HELPER_PROTOCOL_MISMATCH');
  }
  statusNode.textContent = 'Helper local autenticado. Nenhuma conexão externa usada.';
  controls.hidden = false;
}

confirmNode.addEventListener('change', () => {
  runNode.disabled = !confirmNode.checked;
});
runNode.addEventListener('click', () => {
  closeAndSend({ action: 'run_session_probe', confirmed: true, protocol: 1 });
});
cancelNode.addEventListener('click', () => {
  closeAndSend({ action: 'cancel', confirmed: false, protocol: 1 });
});

bootstrap().catch((error) => {
  statusNode.textContent = 'Falha no Gate 0.';
  errorNode.textContent = error instanceof Error ? error.message : String(error);
});
```

- [ ] **Step 3: Add the package script before implementing it and verify red**

Add:

```json
"gate0:package": "npm run gate0:build && tsx groove-brain-gate0/package.ts --version 0.1.0"
```

Run `npm run gate0:package`.

Expected: FAIL because `package.ts` and, until Task 5, the Extension entry are absent.

- [ ] **Step 4: Implement staging, helper build, runtime hash, and CLI invocation**

```ts
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const sourceRoot = path.dirname(fileURLToPath(import.meta.url));
const extensionRoot = path.resolve(sourceRoot, '..');
const versionIndex = process.argv.indexOf('--version');
const version = versionIndex >= 0 ? process.argv[versionIndex + 1] : undefined;
if (!version || !/^\d+\.\d+\.\d+$/.test(version)) {
  throw new Error('VERSION_REQUIRED');
}
const buildRoot = path.join(extensionRoot, 'build', 'groove-brain-gate0');
const cargoTarget = path.join(buildRoot, 'cargo-target');
const stage = path.join(buildRoot, 'staging', version);
fs.rmSync(stage, { recursive: true, force: true });
fs.mkdirSync(path.join(stage, 'dist'), { recursive: true });
fs.mkdirSync(path.join(stage, 'runtime', 'windows-x64'), { recursive: true });

const cargo = spawnSync(
  'cargo',
  ['build', '--release', '--locked', '--manifest-path', path.join(sourceRoot, 'helper', 'Cargo.toml')],
  { stdio: 'inherit', shell: false, env: { ...process.env, CARGO_TARGET_DIR: cargoTarget } },
);
if (cargo.status !== 0) throw new Error(`CARGO_BUILD_FAILED:${cargo.status}`);

const helperName = 'groove-brain-gate0-helper.exe';
const helperSource = path.join(cargoTarget, 'release', helperName);
const helperTarget = path.join(stage, 'runtime', 'windows-x64', helperName);
fs.copyFileSync(helperSource, helperTarget);
const helperSha256 = createHash('sha256').update(fs.readFileSync(helperTarget)).digest('hex');
fs.writeFileSync(
  path.join(stage, 'runtime', 'manifest.json'),
  JSON.stringify({ protocol: 1, platform: 'win32-x64', helper: `windows-x64/${helperName}`, sha256: helperSha256 }, null, 2) + '\n',
  'utf8',
);

fs.cpSync(path.join(sourceRoot, 'ui'), path.join(stage, 'ui'), { recursive: true });
fs.copyFileSync(path.join(sourceRoot, 'dist', 'extension.js'), path.join(stage, 'dist', 'extension.js'));
const manifest = JSON.parse(fs.readFileSync(path.join(sourceRoot, 'manifest.json'), 'utf8')) as Record<string, unknown>;
manifest.version = version;
fs.writeFileSync(path.join(stage, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n', 'utf8');

const output = path.join(buildRoot, `Groove-Brain-Gate-0-${version}.ablx`);
const cli = path.join(extensionRoot, 'node_modules', '@ableton-extensions', 'cli', 'dist', 'cli.mjs');
const packaged = spawnSync(
  process.execPath,
  [cli, 'package', stage, '-i', 'ui', '-i', 'runtime', '-o', output],
  { stdio: 'inherit', shell: false },
);
if (packaged.status !== 0) throw new Error(`ABLx_PACKAGE_FAILED:${packaged.status}`);
console.log(JSON.stringify({ output, stage, helperSha256, node: process.version }));
```

- [ ] **Step 5: Defer the first green package until Task 5**

At this point run Rust checks again and inspect source assets:

```powershell
cargo test --target-dir build/groove-brain-gate0/cargo-target --manifest-path groove-brain-gate0/helper/Cargo.toml
Get-ChildItem groove-brain-gate0/ui
```

Expected: Rust PASS and exactly `index.html`, `app.js`, `styles.css`.

- [ ] **Step 6: Commit UI and packaging pipeline**

```powershell
git add AbletonMCPServer_Extension/package.json AbletonMCPServer_Extension/groove-brain-gate0/ui AbletonMCPServer_Extension/groove-brain-gate0/package.ts
git commit -m "build: package Groove Brain Gate 0 assets"
```

## Task 4: Verified helper spawn, readiness, authentication, concurrency, and shutdown

**Files:**
- Create: `AbletonMCPServer_Extension/groove-brain-gate0/src/protocol.ts`
- Create: `AbletonMCPServer_Extension/groove-brain-gate0/src/helper-process.ts`
- Create: `AbletonMCPServer_Extension/groove-brain-gate0/tests/helper-process.test.ts`

- [ ] **Step 1: Define strict protocol parsers and tests**

`protocol.ts`:

```ts
export const GATE0_PROTOCOL = 1 as const;

export interface HelperReady {
  type: 'ready';
  protocol: 1;
  host: '127.0.0.1';
  port: number;
  parent_pid: number;
}

export type ModalResult =
  | { action: 'cancel'; confirmed: false; protocol: 1 }
  | { action: 'run_session_probe'; confirmed: true; protocol: 1 };

export function parseHelperReady(raw: string, expectedParentPid: number): HelperReady {
  const value: unknown = JSON.parse(raw);
  if (!value || typeof value !== 'object') throw new Error('INVALID_READY');
  const candidate = value as Record<string, unknown>;
  if (
    candidate.type !== 'ready' ||
    candidate.protocol !== GATE0_PROTOCOL ||
    candidate.host !== '127.0.0.1' ||
    !Number.isInteger(candidate.port) ||
    Number(candidate.port) < 1 ||
    Number(candidate.port) > 65535 ||
    candidate.parent_pid !== expectedParentPid
  ) {
    throw new Error('INVALID_READY');
  }
  return candidate as unknown as HelperReady;
}

export function parseModalResult(raw: string): ModalResult {
  const value: unknown = JSON.parse(raw);
  if (!value || typeof value !== 'object') throw new Error('INVALID_MODAL_RESULT');
  const candidate = value as Record<string, unknown>;
  if (candidate.protocol !== GATE0_PROTOCOL) throw new Error('INVALID_MODAL_PROTOCOL');
  if (candidate.action === 'cancel' && candidate.confirmed === false) {
    return candidate as unknown as ModalResult;
  }
  if (candidate.action === 'run_session_probe' && candidate.confirmed === true) {
    return candidate as unknown as ModalResult;
  }
  throw new Error('INVALID_MODAL_RESULT');
}
```

Add to `helper-process.test.ts`:

```ts
import assert from 'node:assert/strict';
import test from 'node:test';
import { parseHelperReady } from '../src/protocol.js';

test('ready parser rejects wrong parent and unsafe port', () => {
  assert.throws(
    () => parseHelperReady('{"type":"ready","protocol":1,"host":"127.0.0.1","port":0,"parent_pid":7}', 7),
    /INVALID_READY/,
  );
  assert.throws(
    () => parseHelperReady('{"type":"ready","protocol":1,"host":"127.0.0.1","port":40000,"parent_pid":8}', 7),
    /INVALID_READY/,
  );
});
```

Run `npm run gate0:test`; expected FAIL until the remaining test imports exist, then keep this assertion green.

- [ ] **Step 2: Implement runtime inventory verification and process lifecycle**

```ts
import { createHash, randomBytes } from 'node:crypto';
import { once } from 'node:events';
import fs from 'node:fs';
import path from 'node:path';
import readline from 'node:readline';
import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process';
import { GATE0_PROTOCOL, parseHelperReady, type HelperReady } from './protocol.js';

interface RuntimeManifest {
  protocol: 1;
  platform: 'win32-x64';
  helper: string;
  sha256: string;
}

function sha256(pathname: string): string {
  return createHash('sha256').update(fs.readFileSync(pathname)).digest('hex');
}

function loadRuntime(resourceRoot: string): { executable: string; manifest: RuntimeManifest } {
  const manifestPath = path.join(resourceRoot, 'runtime', 'manifest.json');
  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8')) as RuntimeManifest;
  if (
    manifest.protocol !== GATE0_PROTOCOL ||
    manifest.platform !== 'win32-x64' ||
    !/^[0-9a-f]{64}$/.test(manifest.sha256)
  ) {
    throw new Error('INVALID_RUNTIME_MANIFEST');
  }
  const executable = path.resolve(resourceRoot, 'runtime', manifest.helper);
  const runtimeRoot = path.resolve(resourceRoot, 'runtime') + path.sep;
  if (!executable.startsWith(runtimeRoot) || !fs.statSync(executable).isFile()) {
    throw new Error('INVALID_HELPER_PATH');
  }
  if (sha256(executable) !== manifest.sha256) throw new Error('HELPER_HASH_MISMATCH');
  return { executable, manifest };
}

async function readyLine(
  child: ChildProcessWithoutNullStreams,
  timeoutMs: number,
): Promise<HelperReady> {
  const lines = readline.createInterface({ input: child.stdout, crlfDelay: Infinity });
  try {
    const linePromise = new Promise<string>((resolve, reject) => {
      lines.once('line', resolve);
      child.once('exit', (code) => reject(new Error(`HELPER_EXITED_BEFORE_READY:${code}`)));
    });
    const timeoutPromise = new Promise<never>((_, reject) => {
      const timer = setTimeout(() => reject(new Error('HELPER_READY_TIMEOUT')), timeoutMs);
      timer.unref();
    });
    return parseHelperReady(await Promise.race([linePromise, timeoutPromise]), process.pid);
  } finally {
    lines.close();
  }
}

export class HelperSession {
  private stopped = false;

  private constructor(
    private readonly child: ChildProcessWithoutNullStreams,
    public readonly ready: HelperReady,
    private readonly token: string,
  ) {}

  static async start(resourceRoot: string, timeoutMs = 5_000): Promise<HelperSession> {
    if (process.platform !== 'win32' || process.arch !== 'x64') {
      throw new Error('UNSUPPORTED_GATE0_PLATFORM');
    }
    const { executable } = loadRuntime(resourceRoot);
    const token = randomBytes(32).toString('hex');
    const child = spawn(executable, [], {
      cwd: resourceRoot,
      windowsHide: true,
      stdio: ['pipe', 'pipe', 'pipe'],
      env: { SystemRoot: process.env.SystemRoot ?? 'C:\\Windows' },
    });
    child.stdin.write(
      `${JSON.stringify({
        type: 'bootstrap',
        protocol: GATE0_PROTOCOL,
        token,
        ui_dir: path.join(resourceRoot, 'ui'),
        parent_pid: process.pid,
      })}\n`,
    );
    try {
      const ready = await readyLine(child, timeoutMs);
      return new HelperSession(child, ready, token);
    } catch (error) {
      child.kill();
      throw error;
    }
  }

  get origin(): string {
    return `http://localhost:${this.ready.port}`;
  }

  get modalUrl(): string {
    return `${this.origin}/#${this.token}`;
  }

  async assertHealthy(): Promise<void> {
    const response = await fetch(`${this.origin}/api/health`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${this.token}` },
      cache: 'no-store',
      signal: AbortSignal.timeout(2_000),
    });
    if (!response.ok) throw new Error(`HELPER_HEALTH_${response.status}`);
    const body = (await response.json()) as { status?: string; protocol?: number };
    if (body.status !== 'ok' || body.protocol !== GATE0_PROTOCOL) {
      throw new Error('HELPER_HEALTH_PAYLOAD');
    }
  }

  async stop(timeoutMs = 2_000): Promise<void> {
    if (this.stopped) return;
    this.stopped = true;
    if (this.child.exitCode !== null) return;
    this.child.stdin.write(`${JSON.stringify({ type: 'shutdown', protocol: GATE0_PROTOCOL })}\n`);
    this.child.stdin.end();
    const waitForExit = async (): Promise<void> => {
      if (this.child.exitCode !== null) return;
      await once(this.child, 'exit');
    };
    const exited = waitForExit().then(() => true);
    const timeout = new Promise<false>((resolve) => {
      const timer = setTimeout(() => resolve(false), timeoutMs);
      timer.unref();
    });
    if (!(await Promise.race([exited, timeout]))) {
      if (this.child.exitCode === null) {
        this.child.kill();
        await waitForExit();
      }
    }
  }
}
```

Do not log `modalUrl`, `token`, bootstrap JSON, or request headers.

- [ ] **Step 3: Extend the integration test to prove two isolated helpers**

Add `fs`, `path`, and `HelperSession` to the test file's top-level imports, then append:

```ts
import fs from 'node:fs';
import path from 'node:path';
import { HelperSession } from '../src/helper-process.js';

const stage = path.resolve('build/groove-brain-gate0/staging/0.1.0');

test('two sessions use distinct endpoints, authenticate, and stop', {
  skip: fs.existsSync(stage) ? false : 'Gate 0 package stage is created in Task 5',
}, async () => {
  const first = await HelperSession.start(stage);
  const second = await HelperSession.start(stage);
  try {
    assert.notEqual(first.ready.port, second.ready.port);
    assert.notEqual(first.modalUrl, second.modalUrl);
    await Promise.all([first.assertHealthy(), second.assertHealthy()]);
  } finally {
    await Promise.all([first.stop(), second.stop()]);
  }
});
```

- [ ] **Step 4: Run the pre-package unit surface without manufacturing an entry file**

```powershell
cargo build --release --locked --target-dir build/groove-brain-gate0/cargo-target --manifest-path groove-brain-gate0/helper/Cargo.toml
npm run gate0:test
```

Expected: parser/resource tests PASS and the two-helper integration test reports exactly one intentional skip because Task 5 has not created the package stage. Task 5 must rerun the same suite with zero skips after packaging.

- [ ] **Step 5: Run typecheck and commit**

```powershell
npm run gate0:typecheck
git add AbletonMCPServer_Extension/groove-brain-gate0/src/protocol.ts AbletonMCPServer_Extension/groove-brain-gate0/src/helper-process.ts AbletonMCPServer_Extension/groove-brain-gate0/tests/helper-process.test.ts
git commit -m "feat: supervise bundled Gate 0 helper"
```

## Task 5: Contextual ClipSlot action and modal lifecycle

**Files:**
- Create: `AbletonMCPServer_Extension/groove-brain-gate0/src/actions.ts`
- Create: `AbletonMCPServer_Extension/groove-brain-gate0/src/extension.ts`
- Create: `AbletonMCPServer_Extension/groove-brain-gate0/tests/modal-result.test.ts`

- [ ] **Step 1: Write modal parser tests**

```ts
import assert from 'node:assert/strict';
import test from 'node:test';
import { parseModalResult } from '../src/protocol.js';

test('modal parser accepts only explicit cancel or confirmed probe', () => {
  assert.deepEqual(
    parseModalResult('{"action":"cancel","confirmed":false,"protocol":1}'),
    { action: 'cancel', confirmed: false, protocol: 1 },
  );
  assert.deepEqual(
    parseModalResult('{"action":"run_session_probe","confirmed":true,"protocol":1}'),
    { action: 'run_session_probe', confirmed: true, protocol: 1 },
  );
  assert.throws(
    () => parseModalResult('{"action":"run_session_probe","confirmed":false,"protocol":1}'),
    /INVALID_MODAL_RESULT/,
  );
});
```

Run `npm run gate0:test`; expected PASS for this pure parser.

- [ ] **Step 2: Implement one active contextual modal at a time**

```ts
import type { ExtensionContext, Handle } from '@ableton-extensions/sdk';
import { HelperSession } from './helper-process.js';
import { parseModalResult, type ModalResult } from './protocol.js';

let activeHelper: HelperSession | null = null;

function isHandle(value: unknown): value is Handle {
  return Boolean(value) && typeof value === 'object' && typeof (value as { id?: unknown }).id === 'bigint';
}

export async function openGate0Modal(
  context: ExtensionContext<'1.0.0'>,
  argument: unknown,
  resourceRoot: string,
): Promise<{ handle: Handle; result: ModalResult }> {
  if (!isHandle(argument)) throw new Error('CLIP_SLOT_HANDLE_REQUIRED');
  if (activeHelper) throw new Error('GATE0_INVOCATION_ALREADY_ACTIVE');
  const helper = await HelperSession.start(resourceRoot);
  activeHelper = helper;
  try {
    await helper.assertHealthy();
    const raw = await context.ui.showModalDialog(helper.modalUrl, 960, 680);
    return { handle: argument, result: parseModalResult(raw) };
  } finally {
    activeHelper = null;
    await helper.stop();
  }
}

export async function shutdownGate0Modal(): Promise<void> {
  const helper = activeHelper;
  activeHelper = null;
  if (helper) await helper.stop();
}
```

- [ ] **Step 3: Implement isolated activation and contextual registration**

```ts
import { initialize, type ActivationContext } from '@ableton-extensions/sdk';
import { openGate0Modal, shutdownGate0Modal } from './actions.js';
import { resourceRootFromEntryDir } from './resource-path.js';

const COMMAND_ID = 'groove-brain.gate0.open';
let unregisterAction: (() => Promise<void>) | null = null;

function activate(activation: ActivationContext): void {
  const context = initialize(activation, '1.0.0');
  const resourceRoot = resourceRootFromEntryDir(__dirname);
  context.commands.registerCommand(COMMAND_ID, (argument: unknown) => {
    void openGate0Modal(context, argument, resourceRoot)
      .then(({ result }) => console.log(`[groove-brain-gate0] modal result: ${result.action}`))
      .catch((error: unknown) => {
        const message = error instanceof Error ? error.message : String(error);
        console.error(`[groove-brain-gate0] ${message}`);
      });
  });
  void context.ui
    .registerContextMenuAction('ClipSlot', 'Open Groove Brain Gate 0', COMMAND_ID)
    .then((unregister) => {
      unregisterAction = unregister;
    });
}

function deactivate(): void {
  const unregister = unregisterAction;
  unregisterAction = null;
  void shutdownGate0Modal().finally(() => {
    if (unregister) void unregister();
  });
}

export { activate, deactivate };
```

This action is deliberately `ClipSlot`-only. Do not register track, clip, Arrangement, or global scopes in Gate 0.

- [ ] **Step 4: Build and package the first real isolated Extension**

```powershell
npm run gate0:test
npm run gate0:build
npm run gate0:package
```

Expected: TypeScript strict check PASS, `dist/extension.js` exists, Rust release build PASS, `build/groove-brain-gate0/Groove-Brain-Gate-0-0.1.0.ablx` exists, and the final `npm run gate0:test` reports zero skips. Rerun `npm run gate0:test` once more after packaging to discharge Task 4's intentional pre-package skip.

- [ ] **Step 5: Ensure the released MCP Extension is untouched**

```powershell
npm run build
git diff --exit-code -- manifest.json src/extension.ts src/index.ts
```

Expected: existing Extension build PASS and no modifications to its manifest or source.

- [ ] **Step 6: Commit the contextual modal**

```powershell
git add AbletonMCPServer_Extension/groove-brain-gate0/src/actions.ts AbletonMCPServer_Extension/groove-brain-gate0/src/extension.ts AbletonMCPServer_Extension/groove-brain-gate0/tests/modal-result.test.ts
git commit -m "feat: open Groove Brain from a ClipSlot action"
```

## Task 6: Explicit Session clip probe, partial-failure receipt, and readback

**Files:**
- Create: `AbletonMCPServer_Extension/groove-brain-gate0/src/session-clip-probe.ts`
- Create: `AbletonMCPServer_Extension/groove-brain-gate0/src/sdk-slot-adapter.ts`
- Create: `AbletonMCPServer_Extension/groove-brain-gate0/src/receipt-store.ts`
- Modify: `AbletonMCPServer_Extension/groove-brain-gate0/src/actions.ts`
- Create: `AbletonMCPServer_Extension/groove-brain-gate0/tests/session-clip-probe.test.ts`

- [ ] **Step 1: Write red tests for empty, occupied, success, and failure-after-create**

```ts
import assert from 'node:assert/strict';
import test from 'node:test';
import { runSessionClipProbe, type ClipPort, type SlotPort } from '../src/session-clip-probe.js';

function fakeSlot(initial: ClipPort | null = null): { slot: SlotPort; clips: ClipPort[] } {
  const clips: ClipPort[] = initial ? [initial] : [];
  return {
    clips,
    slot: {
      handleId: 'slot-7',
      getClip: () => clips.at(-1) ?? null,
      createMidiClip: async () => {
        const clip: ClipPort = { handleId: 'clip-9', name: '', notes: [] };
        clips.push(clip);
        return clip;
      },
    },
  };
}

test('occupied slot is blocked before mutation', async () => {
  const existing: ClipPort = { handleId: 'old', name: 'Keep', notes: [] };
  const { slot, clips } = fakeSlot(existing);
  const receipt = await runSessionClipProbe(slot, { nowEpochMs: () => 1000, nowMonotonicMs: () => 5 });
  assert.equal(receipt.status, 'blocked');
  assert.equal(receipt.code, 'SLOT_OCCUPIED');
  assert.equal(clips.length, 1);
});

test('successful write is read back exactly', async () => {
  const { slot } = fakeSlot();
  const receipt = await runSessionClipProbe(slot, { nowEpochMs: () => 1000, nowMonotonicMs: () => 5 });
  assert.equal(receipt.status, 'ok');
  assert.equal(receipt.intendedCount, 4);
  assert.equal(receipt.readbackCount, 4);
  assert.equal(receipt.intendedHash, receipt.readbackHash);
});

test('failure after create reports partial and never retries or deletes', async () => {
  const { slot, clips } = fakeSlot();
  const receipt = await runSessionClipProbe(slot, {
    nowEpochMs: () => 1000,
    nowMonotonicMs: () => 5,
    injectFailure: 'after_create',
  });
  assert.equal(receipt.status, 'partial');
  assert.equal(receipt.code, 'INJECTED_AFTER_CREATE');
  assert.equal(clips.length, 1);
});
```

Run `npm run gate0:test`; expected FAIL because the state machine does not exist.

- [ ] **Step 2: Implement the complete testable write/readback state machine**

```ts
import { createHash, randomUUID } from 'node:crypto';

export interface Gate0Note {
  pitch: number;
  startTime: number;
  duration: number;
  velocity: number;
}

export interface ClipPort {
  handleId: string;
  name: string;
  notes: Gate0Note[];
}

export interface SlotPort {
  handleId: string;
  getClip(): ClipPort | null;
  createMidiClip(lengthBeats: number): Promise<ClipPort>;
}

export interface ProbeReceipt {
  receiptId: string;
  status: 'ok' | 'blocked' | 'failed' | 'partial';
  code: string;
  startedAtEpochMs: number;
  durationMs: number;
  slotHandle: string;
  clipHandle: string | null;
  intendedCount: number;
  readbackCount: number;
  intendedHash: string;
  readbackHash: string | null;
  retryAttempted: false;
  rollbackClaimed: false;
}

interface ProbeOptions {
  nowEpochMs: () => number;
  nowMonotonicMs: () => number;
  injectFailure?: 'after_create';
}

const NOTES: Gate0Note[] = [0, 1, 2, 3].map((startTime) => ({
  pitch: 36,
  startTime,
  duration: 0.25,
  velocity: 100,
}));

function canonical(notes: Gate0Note[]): Gate0Note[] {
  return notes
    .map(({ pitch, startTime, duration, velocity }) => ({ pitch, startTime, duration, velocity }))
    .sort((a, b) => a.startTime - b.startTime || a.pitch - b.pitch);
}

function hashNotes(notes: Gate0Note[]): string {
  return createHash('sha256').update(JSON.stringify(canonical(notes))).digest('hex');
}

export async function runSessionClipProbe(
  slot: SlotPort,
  options: ProbeOptions,
): Promise<ProbeReceipt> {
  const startedAtEpochMs = options.nowEpochMs();
  const startedMono = options.nowMonotonicMs();
  const base = {
    receiptId: randomUUID(),
    startedAtEpochMs,
    slotHandle: slot.handleId,
    intendedCount: NOTES.length,
    intendedHash: hashNotes(NOTES),
    retryAttempted: false as const,
    rollbackClaimed: false as const,
  };
  if (slot.getClip() !== null) {
    return {
      ...base,
      status: 'blocked',
      code: 'SLOT_OCCUPIED',
      durationMs: options.nowMonotonicMs() - startedMono,
      clipHandle: null,
      readbackCount: 0,
      readbackHash: null,
    };
  }

  let clip: ClipPort | null = null;
  try {
    clip = await slot.createMidiClip(4);
    if (options.injectFailure === 'after_create') throw new Error('INJECTED_AFTER_CREATE');
    clip.name = 'Groove Brain Gate 0 Probe';
    clip.notes = NOTES.map((note) => ({ ...note }));
    const readback = canonical(clip.notes);
    const readbackHash = hashNotes(readback);
    return {
      ...base,
      status: readbackHash === base.intendedHash ? 'ok' : 'failed',
      code: readbackHash === base.intendedHash ? 'READBACK_MATCH' : 'READBACK_MISMATCH',
      durationMs: options.nowMonotonicMs() - startedMono,
      clipHandle: clip.handleId,
      readbackCount: readback.length,
      readbackHash,
    };
  } catch (error) {
    const code = error instanceof Error ? error.message : 'UNKNOWN_WRITE_ERROR';
    return {
      ...base,
      status: clip ? 'partial' : 'failed',
      code,
      durationMs: options.nowMonotonicMs() - startedMono,
      clipHandle: clip?.handleId ?? null,
      readbackCount: clip?.notes.length ?? 0,
      readbackHash: clip ? hashNotes(clip.notes) : null,
    };
  }
}
```

Epoch timestamps use `Date.now()`; elapsed duration uses `performance.now()`. They are never compared to each other.

- [ ] **Step 3: Implement the narrow SDK adapter using verified SDK classes**

```ts
import {
  ClipSlot,
  MidiClip,
  type ExtensionContext,
  type Handle,
  type NoteDescription,
} from '@ableton-extensions/sdk';
import type { ClipPort, Gate0Note, SlotPort } from './session-clip-probe.js';

function adaptNotes(notes: NoteDescription[]): Gate0Note[] {
  return notes.map((note) => ({
    pitch: note.pitch,
    startTime: note.startTime,
    duration: note.duration,
    velocity: note.velocity ?? 100,
  }));
}

function adaptClip(clip: {
  handle: Handle;
  name: string;
  notes: NoteDescription[];
}): ClipPort {
  return {
    handleId: clip.handle.id.toString(),
    get name() { return clip.name; },
    set name(value: string) { clip.name = value; },
    get notes() { return adaptNotes(clip.notes); },
    set notes(value: Gate0Note[]) { clip.notes = value; },
  };
}

export function adaptClipSlot(
  context: ExtensionContext<'1.0.0'>,
  handle: Handle,
): SlotPort {
  const slot = context.getObjectFromHandle(handle, ClipSlot);
  return {
    handleId: slot.handle.id.toString(),
    getClip: () => {
      const clip = slot.clip;
      if (!clip) return null;
      return adaptClip(context.getObjectFromHandle(clip.handle, MidiClip));
    },
    createMidiClip: async (lengthBeats: number) => adaptClip(await slot.createMidiClip(lengthBeats)),
  };
}
```

Run `npm run gate0:typecheck`. Expected: PASS. The non-obvious API proof is the vendored signature `getObjectFromHandle(handle, MidiClip)` plus strict compilation; no unchecked cast is allowed.

- [ ] **Step 4: Store redacted receipts outside the package**

```ts
import fs from 'node:fs';
import path from 'node:path';
import type { ExtensionContext } from '@ableton-extensions/sdk';
import type { ProbeReceipt } from './session-clip-probe.js';

export function storeReceipt(
  context: ExtensionContext<'1.0.0'>,
  receipt: ProbeReceipt,
): string {
  const root = context.environment.storageDirectory;
  if (!root) throw new Error('STORAGE_DIRECTORY_UNAVAILABLE');
  const directory = path.join(root, 'gate0', 'receipts');
  fs.mkdirSync(directory, { recursive: true });
  const destination = path.join(directory, `${receipt.startedAtEpochMs}-${receipt.receiptId}.json`);
  fs.writeFileSync(destination, `${JSON.stringify(receipt, null, 2)}\n`, { encoding: 'utf8', flag: 'wx' });
  return destination;
}
```

Receipt contains hashes/counts/ephemeral handle strings, never full notes, token, project name, or personal paths in logs.

- [ ] **Step 5: Wire the confirmed modal result into one write and a result modal**

Change `openGate0Modal` so it returns the parsed handle/result as in Task 5. In the command callback, replace the `.then` body with:

```ts
.then(async ({ handle, result }) => {
  if (result.action === 'cancel') return;
  const slot = adaptClipSlot(context, handle);
  const injectFailure = process.env.GROOVE_BRAIN_GATE0_INJECT === 'after_create'
    ? 'after_create' as const
    : undefined;
  const receipt = await runSessionClipProbe(slot, {
    nowEpochMs: Date.now,
    nowMonotonicMs: () => performance.now(),
    injectFailure,
  });
  storeReceipt(context, receipt);
  const summary = JSON.stringify({ ...receipt, receiptSaved: true }, null, 2)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;');
  const html = `<meta charset="utf-8"><style>body{font:14px monospace;background:#1d1d1d;color:#eee;padding:24px}pre{white-space:pre-wrap}</style><h1>Gate 0 receipt</h1><pre>${summary}</pre>`;
  await context.ui.showModalDialog(`data:text/html;charset=utf-8,${encodeURIComponent(html)}`, 840, 620);
})
```

Add imports for `adaptClipSlot`, `runSessionClipProbe`, and `storeReceipt`. Do not wrap create/set/readback in a claimed rollback transaction. Do not automatically delete a partial clip or retry.

- [ ] **Step 6: Run red/green tests and the complete local gate**

```powershell
npm run gate0:test
npm run gate0:typecheck
npm run gate0:build
npm run gate0:package
npm run build
```

Expected: all PASS. Existing Extension build still PASS.

- [ ] **Step 7: Commit the safe Session probe**

```powershell
git add AbletonMCPServer_Extension/groove-brain-gate0/src/session-clip-probe.ts AbletonMCPServer_Extension/groove-brain-gate0/src/sdk-slot-adapter.ts AbletonMCPServer_Extension/groove-brain-gate0/src/receipt-store.ts AbletonMCPServer_Extension/groove-brain-gate0/src/actions.ts AbletonMCPServer_Extension/groove-brain-gate0/src/extension.ts AbletonMCPServer_Extension/groove-brain-gate0/tests/session-clip-probe.test.ts
git commit -m "feat: prove safe Session clip writeback"
```

## Task 7: Archive verifier, inventory, size budget, and source-contract tests

**Files:**
- Create: `scripts/gate0/verify_groove_brain_ablx.py`
- Create: `tests/test_groove_brain_gate0_package.py`

- [ ] **Step 1: Write failing package-verifier tests**

```python
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from scripts.gate0.verify_groove_brain_ablx import verify_ablx


def _artifact(path: Path, *, helper_bytes: bytes = b"helper") -> Path:
    helper_hash = hashlib.sha256(helper_bytes).hexdigest()
    runtime = {
        "protocol": 1,
        "platform": "win32-x64",
        "helper": "windows-x64/groove-brain-gate0-helper.exe",
        "sha256": helper_hash,
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", '{"entry":"dist/extension.js"}')
        archive.writestr("dist/extension.js", "module.exports={};")
        archive.writestr("ui/index.html", "<html></html>")
        archive.writestr("ui/app.js", "")
        archive.writestr("ui/styles.css", "")
        archive.writestr("runtime/manifest.json", json.dumps(runtime))
        archive.writestr("runtime/windows-x64/groove-brain-gate0-helper.exe", helper_bytes)
    return path


def test_verifier_accepts_exact_hashed_inventory(tmp_path: Path) -> None:
    report = verify_ablx(_artifact(tmp_path / "gate0.ablx"))
    assert report["status"] == "pass"
    assert report["entry_count"] == 7
    assert report["helper_hash_match"] is True


def test_verifier_rejects_helper_hash_mismatch(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path / "gate0.ablx")
    with zipfile.ZipFile(artifact, "a") as archive:
        archive.writestr("runtime/windows-x64/groove-brain-gate0-helper.exe", b"tampered")
    with pytest.raises(ValueError, match="DUPLICATE_ENTRY|HELPER_HASH_MISMATCH"):
        verify_ablx(artifact)
```

Run:

```powershell
.\.venv-win\Scripts\python.exe -m pytest tests\test_groove_brain_gate0_package.py -q
```

Expected: FAIL because the verifier does not exist.

- [ ] **Step 2: Implement exact archive verification**

```python
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

REQUIRED = {
    "manifest.json",
    "dist/extension.js",
    "ui/index.html",
    "ui/app.js",
    "ui/styles.css",
    "runtime/manifest.json",
    "runtime/windows-x64/groove-brain-gate0-helper.exe",
}
MAX_COMPRESSED_BYTES = 50 * 1024 * 1024


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_ablx(path: Path) -> dict[str, Any]:
    path = path.resolve(strict=True)
    if path.stat().st_size > MAX_COMPRESSED_BYTES:
        raise ValueError("PACKAGE_TOO_LARGE")
    with zipfile.ZipFile(path) as archive:
        names = [info.filename for info in archive.infolist() if not info.is_dir()]
        if len(names) != len(set(names)):
            raise ValueError("DUPLICATE_ENTRY")
        actual = set(names)
        missing = sorted(REQUIRED - actual)
        forbidden = sorted(
            name
            for name in actual
            if name.endswith((".map", ".pdb", ".rs", ".ts"))
            or "/target/" in name
            or "node_modules/" in name
        )
        if missing:
            raise ValueError(f"MISSING_ENTRIES:{','.join(missing)}")
        if forbidden:
            raise ValueError(f"FORBIDDEN_ENTRIES:{','.join(forbidden)}")
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("entry") != "dist/extension.js":
            raise ValueError("INVALID_EXTENSION_ENTRY")
        runtime = json.loads(archive.read("runtime/manifest.json"))
        helper_path = f"runtime/{runtime.get('helper', '')}"
        if helper_path not in actual:
            raise ValueError("RUNTIME_HELPER_MISSING")
        helper_hash = _sha256(archive.read(helper_path))
        if helper_hash != runtime.get("sha256"):
            raise ValueError("HELPER_HASH_MISMATCH")
        installed_bytes = sum(info.file_size for info in archive.infolist() if not info.is_dir())
    return {
        "status": "pass",
        "artifact": str(path),
        "artifact_sha256": _sha256(path.read_bytes()),
        "compressed_bytes": path.stat().st_size,
        "installed_bytes": installed_bytes,
        "entry_count": len(names),
        "entries": sorted(names),
        "helper_sha256": helper_hash,
        "helper_hash_match": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = verify_ablx(args.artifact)
    encoded = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Add source-contract assertions to the same test file**

```python
ROOT = Path(__file__).resolve().parents[1]
GATE0 = ROOT / "AbletonMCPServer_Extension" / "groove-brain-gate0"


def test_gate0_source_is_isolated_and_loopback_only() -> None:
    package = json.loads((ROOT / "AbletonMCPServer_Extension" / "package.json").read_text())
    manifest = json.loads((GATE0 / "manifest.json").read_text())
    server = (GATE0 / "helper" / "src" / "server.rs").read_text(encoding="utf-8")
    extension = (GATE0 / "src" / "extension.ts").read_text(encoding="utf-8")
    assert manifest["entry"] == "dist/extension.js"
    assert "gate0:package" in package["scripts"]
    assert 'TcpListener::bind("127.0.0.1:0")' in server
    assert "registerContextMenuAction('ClipSlot'" in extension
    assert "Arrangement" not in extension
```

- [ ] **Step 4: Run verifier, pytest, Ruff, and package budget**

```powershell
cd C:\Users\Usuario\repos\ableton-mcp-server
.\.venv-win\Scripts\python.exe -m pytest tests\test_groove_brain_gate0_package.py -q
.\.venv-win\Scripts\python.exe -m ruff check scripts\gate0\verify_groove_brain_ablx.py tests\test_groove_brain_gate0_package.py
.\.venv-win\Scripts\python.exe scripts\gate0\verify_groove_brain_ablx.py AbletonMCPServer_Extension\build\groove-brain-gate0\Groove-Brain-Gate-0-0.1.0.ablx --output C:\Users\Usuario\repos\_release-artifacts\groove-brain-gate0\package-0.1.0.json
```

Expected: pytest/Ruff PASS, verifier `status=pass`, no source maps/source/target/node_modules entries, helper hash matches, compressed package below 50 MiB.

- [ ] **Step 5: Commit verifier and tests**

```powershell
git add scripts/gate0/verify_groove_brain_ablx.py tests/test_groove_brain_gate0_package.py
git commit -m "test: verify Groove Brain Gate 0 package"
```

## Task 8: Developer Live run, failure injection, and operator runbook

**Files:**
- Create: `scripts/gate0/collect_gate0_evidence.ps1`
- Create: `docs/groove-brain/gate0-runbook.md`

- [ ] **Step 1: Create the evidence collector with no repository writes**

```powershell
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Artifact,
    [Parameter(Mandatory = $true)][string]$SourceCommit,
    [Parameter(Mandatory = $true)][string]$SdkSha256,
    [Parameter(Mandatory = $true)][string]$CliSha256,
    [Parameter(Mandatory = $true)][ValidateSet('before', 'after')][string]$Phase,
    [string]$OutputRoot = 'C:\Users\Usuario\repos\_release-artifacts\groove-brain-gate0'
)

$ErrorActionPreference = 'Stop'
$artifactPath = (Resolve-Path -LiteralPath $Artifact).Path
$runIdPath = Join-Path $OutputRoot 'current-run-id.txt'
New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null
if ($Phase -eq 'before') {
    $runId = Get-Date -Format 'yyyyMMdd-HHmmss'
    Set-Content -LiteralPath $runIdPath -Value $runId -NoNewline
} else {
    $runId = (Get-Content -LiteralPath $runIdPath -Raw).Trim()
}
$runDir = Join-Path $OutputRoot $runId
New-Item -ItemType Directory -Force -Path $runDir | Out-Null
$helpers = @(Get-Process -Name 'groove-brain-gate0-helper' -ErrorAction SilentlyContinue | ForEach-Object {
    @{ id = $_.Id; start_time = $_.StartTime.ToUniversalTime().ToString('o') }
})
$payload = [ordered]@{
    schema_version = 1
    phase = $Phase
    captured_at_utc = [DateTime]::UtcNow.ToString('o')
    windows = [Environment]::OSVersion.VersionString
    architecture = [Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
    source_commit = $SourceCommit
    sdk_sha256 = $SdkSha256
    cli_sha256 = $CliSha256
    artifact = $artifactPath
    artifact_sha256 = (Get-FileHash -LiteralPath $artifactPath -Algorithm SHA256).Hash.ToLowerInvariant()
    helper_processes = $helpers
    network_profile = @(Get-NetConnectionProfile -ErrorAction SilentlyContinue | Select-Object Name, IPv4Connectivity, IPv6Connectivity)
}
$payload | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $runDir "$Phase.json") -Encoding utf8
Write-Output $runDir
```

This script records process/network evidence only. It does not kill Live, install the `.ablx`, modify firewall state, or infer PASS from absence of a process snapshot.

- [ ] **Step 2: Write the exact disposable-Set runbook**

The runbook must contain these operator preconditions and exact observations:

```markdown
# Groove Brain Gate 0 operator runbook

## Preconditions

- Use a new unsaved disposable Live Set.
- Create one MIDI track with an empty Session slot.
- Do not use Arrangement or an occupied slot.
- Record exact Live beta build and Extension Host Node version from Gate 0 logs/receipt.
- Never run crash tests against an unsaved real project.

## Happy path

1. Capture `before` evidence.
2. Install `Groove-Brain-Gate-0-0.1.0.ablx` through Live Settings → Extensions.
3. Right-click the known empty ClipSlot and choose `Open Groove Brain Gate 0`.
4. Confirm modal loads local assets and reports authenticated helper.
5. Check the explicit disposable-slot confirmation and run the probe.
6. Verify a four-beat MIDI clip appears with C1/kick notes at beats 0, 1, 2, and 3.
7. Verify result modal reports `status=ok`, `READBACK_MATCH`, counts 4/4, and equal hashes.
8. Close result modal and Live; capture `after` evidence.
9. Confirm zero `groove-brain-gate0-helper` process remains.

## Occupied-slot path

1. Reopen from the newly occupied slot.
2. Confirm action returns `SLOT_OCCUPIED` and creates no second clip or notes.

## Failure injection path

1. Run the Extension Host in development with `GROOVE_BRAIN_GATE0_INJECT=after_create`.
2. Use another disposable empty slot and run the probe once.
3. Confirm receipt is `partial` with `INJECTED_AFTER_CREATE`.
4. Confirm exactly one empty partial clip exists, no retry occurred, and no automatic delete claimed rollback.
5. Undo manually in Live.

## Crash paths

- Kill helper while modal is open; close the broken modal manually; verify diagnostic and no retry/write.
- Kill the Extension Host/Live in the disposable Set; verify stdin EOF terminates helper.
- Repeat normal invocation after restart; verify new port/token and no stale target reuse.
```

- [ ] **Step 3: Run focused static and local gates before opening Live**

```powershell
cd AbletonMCPServer_Extension
npm run gate0:test
npm run gate0:typecheck
npm run gate0:build
npm run gate0:package
npm run build
cd ..
.\.venv-win\Scripts\python.exe -m pytest tests\test_groove_brain_gate0_package.py tests\test_extension_loopback.py -q
```

Expected: all PASS.

- [ ] **Step 4: Run the happy, occupied, injection, helper-kill, and host-kill paths**

Use the runbook exactly. Persist screenshots, receipt JSON, process snapshots, package verification JSON, and operator notes under the external run directory. A failed row stays failed; do not edit the report into PASS.

- [ ] **Step 5: Commit the collector and runbook, not generated evidence**

```powershell
git add scripts/gate0/collect_gate0_evidence.ps1 docs/groove-brain/gate0-runbook.md
git commit -m "docs: add Groove Brain Gate 0 runbook"
```

## Task 9: Clean-machine offline, update, uninstall, and concurrency matrix

**Files:**
- Modify: `docs/groove-brain/gate0-runbook.md`
- External evidence only: `C:\Users\Usuario\repos\_release-artifacts\groove-brain-gate0\<run-id>`

- [ ] **Step 1: Build two package versions from identical source**

```powershell
cd AbletonMCPServer_Extension
npm run gate0:build
npx tsx groove-brain-gate0\package.ts --version 0.1.0
npx tsx groove-brain-gate0\package.ts --version 0.1.1
```

Expected: two `.ablx` files with different manifest versions and package hashes; runtime helper hashes are identical.

- [ ] **Step 2: Verify both inventories before transfer**

```powershell
cd ..
.\.venv-win\Scripts\python.exe scripts\gate0\verify_groove_brain_ablx.py AbletonMCPServer_Extension\build\groove-brain-gate0\Groove-Brain-Gate-0-0.1.0.ablx
.\.venv-win\Scripts\python.exe scripts\gate0\verify_groove_brain_ablx.py AbletonMCPServer_Extension\build\groove-brain-gate0\Groove-Brain-Gate-0-0.1.1.ablx
```

Expected: both PASS and contain exactly the required runtime/UI/entry surface plus harmless zip directory entries.

- [ ] **Step 3: Prove clean-machine single-install and offline operation**

On a Windows x64 machine/VM without the repository, Python, Rust, developer Node, MCP Server, or Remote Script:

1. copy only `0.1.0.ablx` plus the non-installed evidence collector;
2. disconnect network or use an auditable deny-all outbound rule for Live/Extension Host/helper;
3. install only the `.ablx`;
4. run happy and occupied paths;
5. capture attempted connections with Windows Firewall logs or an equivalent local monitor;
6. require zero egress attempts and successful local operation.

If any runtime/toolchain installation is required, mark `single_install=FAIL` and stop.

- [ ] **Step 4: Prove update and persistent storage behavior**

1. Preserve the `0.1.0` receipt in Extension storage.
2. Install `0.1.1.ablx` over the same Extension identity.
3. Run another happy path.
4. Verify both receipts remain and the new receipt records version `0.1.1` after adding manifest version to the receipt contract.
5. Verify no old executable remains running or discoverable outside the installed Extension resources.

If Live treats the version as a separate Extension or loses storage, record actual behavior and fail the update row; do not rename folders manually to manufacture success.

- [ ] **Step 5: Prove concurrency isolation outside the modal limitation**

The Node integration test already starts two helpers simultaneously. On the clean machine, additionally start two `HelperSession` invocations through the Extension Host test runner when supported and record distinct ports/tokens. If Live serializes modal actions, record `live_modal_concurrency=HOST_SERIALIZED` and require the process-level concurrency test to PASS; do not claim two simultaneous Live modals.

- [ ] **Step 6: Prove uninstall cleanup**

1. Close Live normally and capture zero helpers.
2. Remove the Extension through the supported Live UI.
3. Verify no executable is running and no executable copy remains outside Ableton-managed install resources.
4. Record whether Extension storage receipts remain or are removed; either is acceptable only if documented and contains no executable/token.

- [ ] **Step 7: Extend and commit only runbook clarifications discovered during the run**

```powershell
git add docs/groove-brain/gate0-runbook.md
git commit -m "docs: clarify Gate 0 clean-machine matrix"
```

Do not commit machine-specific paths, screenshots, receipt files, firewall logs, or artifacts.

## Task 10: Full verification, evidence packet, and binary stop/go decision

**Files:**
- Create: `docs/reports/2026-08-30-groove-brain-gate0-result.md`
- Modify: `tasks/groove-brain-gate0-plan/EXECUTION.md`

- [ ] **Step 1: Run the complete automated verification from fresh generated outputs**

```powershell
cd C:\Users\Usuario\repos\ableton-mcp-server\AbletonMCPServer_Extension
$extensionRoot = (Resolve-Path -LiteralPath .).Path
$allowedBuildRoot = [IO.Path]::GetFullPath((Join-Path $extensionRoot 'build')) + [IO.Path]::DirectorySeparatorChar
$gateBuild = [IO.Path]::GetFullPath((Join-Path $extensionRoot 'build\groove-brain-gate0'))
if (-not $gateBuild.StartsWith($allowedBuildRoot, [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe Gate 0 build path' }
Remove-Item -LiteralPath $gateBuild -Recurse -Force -ErrorAction SilentlyContinue
npm run gate0:test
npm run gate0:typecheck
npm run gate0:build
npm run gate0:package
npm run build
cargo test --target-dir build/groove-brain-gate0/cargo-target --manifest-path groove-brain-gate0\helper\Cargo.toml
cargo clippy --target-dir build/groove-brain-gate0/cargo-target --manifest-path groove-brain-gate0\helper\Cargo.toml --all-targets -- -D warnings
cd ..
.\.venv-win\Scripts\python.exe -m pytest tests\test_groove_brain_gate0_package.py tests\test_extension_loopback.py -q
.\.venv-win\Scripts\python.exe -m ruff check scripts\gate0\verify_groove_brain_ablx.py tests\test_groove_brain_gate0_package.py
.\.venv-win\Scripts\python.exe scripts\gate0\verify_groove_brain_ablx.py AbletonMCPServer_Extension\build\groove-brain-gate0\Groove-Brain-Gate-0-0.1.0.ablx
git diff --check
```

Expected: every command PASS. Do not substitute a previous run.

- [ ] **Step 2: Create the result report from observed evidence**

Use this exact table and fill each Result with `PASS` or `FAIL`; `HOST_SERIALIZED` is allowed only for simultaneous Live modals and does not replace process-level PASS:

```markdown
# Groove Brain Gate 0 Result

| Gate | Result | Evidence path/hash |
|---|---|---|
| Exact compatibility matrix captured |  |  |
| `.ablx` inventory/hash/size verified |  |  |
| Clean machine requires only `.ablx` |  |  |
| Installed resource discovery independent of CWD |  |  |
| Bundled helper hash verified before spawn |  |  |
| Loopback port allocated atomically |  |  |
| Secret absent from argv/server requests/logs; fragment cleared before health |  |  |
| Contextual modal loads local UI |  |  |
| Explicit empty-slot confirmation |  |  |
| Session create/set/readback matches |  |  |
| Occupied slot fails before mutation |  |  |
| Failure after create reports partial/no retry |  |  |
| Normal close leaves zero helper |  |  |
| Helper crash leaves Set unmodified |  |  |
| Host/Live crash leaves zero helper |  |  |
| Two helper sessions isolate port/token |  |  |
| Update preserves permitted storage |  |  |
| Uninstall leaves no executable process/copy |  |  |
| Offline run makes zero egress attempt |  |  |
| Existing MCP Extension build/regressions pass |  |  |

**Decision:** STOP or GO LIMITED
**Disabled capabilities:** Arrangement, global persistent panel, SD3 mapping, inference, corpus, model training.
```

`GO LIMITED` requires every row except explicitly documented host-modal concurrency to PASS. Any required FAIL produces `STOP`.

- [ ] **Step 3: Update the execution packet with exact evidence and remaining risks**

Mark the task acceptance rows only from fresh evidence. Record commit IDs, artifact SHA-256, external evidence directory, test counts, Gate result, unrelated work preserved, and the next allowed plan. Do not claim the repository is clean while unrelated prototype changes remain.

- [ ] **Step 4: Review exact diff and commit the result separately**

```powershell
git status --short
git diff --check
git diff -- docs/reports/2026-08-30-groove-brain-gate0-result.md tasks/groove-brain-gate0-plan/EXECUTION.md
git add docs/reports/2026-08-30-groove-brain-gate0-result.md tasks/groove-brain-gate0-plan/EXECUTION.md
git diff --cached --check
git commit -m "docs: record Groove Brain Gate 0 result"
git show --format=fuller --no-patch HEAD
```

- [ ] **Step 5: Stop at the gate**

If `STOP`, return to architecture design with the failed rows. If `GO LIMITED`, the next separate plan may begin the rights-cleared dataset/retriever work or a minimal UI/product slice. Do not begin ONNX or training inside this plan.

## Spec coverage

| Approved design requirement | Implemented/proven by |
|---|---|
| One `.ablx`, no hidden installer | Tasks 3, 7, 9 |
| Contextual/modal SDK lifecycle | Tasks 5, 8 |
| Local web UI | Tasks 2–5 |
| Native helper outside Extension Host | Tasks 2, 4 |
| Random loopback endpoint and session secret | Tasks 2, 4 |
| No token in argv/logs | Tasks 2, 4, 8 |
| Session-first safe write/readback | Task 6 |
| Occupied/stale target fails closed | Tasks 6, 8 |
| No rollback/retry fiction | Tasks 6, 8 |
| Machine-clean/offline proof | Task 9 |
| Crash, concurrency, update, uninstall | Tasks 8–9 |
| Package and runtime budgets | Tasks 3, 7 |
| No corpus/model work before packaging proof | Hard stop and Task 10 |
| Existing MCP Extension preserved | Tasks 5, 7, 10 |

## Self-Review

Spec coverage review: PASS. Every Gate 0 requirement maps to a task above. Full dashboard, Arrangement, mapping, data, retrieval, and neural work are intentionally excluded and explicitly disabled in the result report.

Placeholder scan: PASS after replacing design uncertainty with binary gates. The blank `Result` cells in the future evidence template are operator output fields, not implementation placeholders; they must become `PASS` or `FAIL` in Task 10.

Type consistency review: PASS. Protocol version is numeric `1` in Rust, TypeScript, UI, runtime manifest, modal result, and tests. Runtime helper path is `runtime/windows-x64/groove-brain-gate0-helper.exe` everywhere. Receipt status/code/count/hash fields are consistent across implementation, tests, storage, and result UI.

Execution Consistency Audit evidence:

- PASS Test/implementation trace: Task 1 path assertion maps to `path.resolve(entryDir, '..')`; Task 2 protocol/auth/asset assertions map to exact parser functions; Task 4 readiness/concurrency assertions map to `parseHelperReady` and `HelperSession`; Task 6 mutation assertions map to each state-machine branch; Task 7 archive assertions map to exact inventory/hash checks.
- PASS Per-task command executability: Task 1 uses the existing `tsx`/`tsc`; Rust files exist before Cargo commands; Task 3 defers real package success until the Extension entry exists; Task 4 explicitly creates a temporary generated entry for its integration test; all later npm/Python commands target files created earlier.
- PASS File usage audit: every created source file has an importer, command, route, archive path, test, or operator consumer in the ownership map; UI files are served by exact Rust routes and included by the CLI staging command.
- PASS Spec lifecycle audit: one mutable `activeHelper` belongs to the Extension invocation; modal close sends shutdown; stdin EOF handles parent death; helper crash never triggers Live write; target is re-resolved only after explicit modal result; partial create is recorded and never retried/deleted automatically.
- PASS Time source audit: receipts use Unix epoch milliseconds from `Date.now()` only for filenames/audit and monotonic milliseconds from `performance.now()` only for duration; no cross-clock comparison exists.
- PASS State scope audit: helper token/port/process are per invocation, Rust shutdown flag is per helper process, `activeHelper` is Extension-process state enforcing one modal, receipts are immutable persistent files, generated build state is outside Git, and two helper sessions are tested for isolation.
- PASS Environment audit: every runtime URL is desktop-only `http://localhost:<random-port>` backed by `127.0.0.1`; no QR, LAN, mobile, cloud, CDN, or external endpoint exists; clean-machine tests require zero egress.
- PASS Browser event audit: the UI and operator both use the real checkbox `change` and button `click` handlers; there is no fake drag/touch test. Task 8 proves the observable result through the exact production event path: modal result, Live clip, and receipt.
- PASS Lint/import audit: TypeScript uses NodeNext strict typecheck and existing dependencies; Rust uses locked dependencies plus Clippy `-D warnings`; Python uses repository Ruff and pytest. The SDK adapter uses `MidiClip` directly and forbids unchecked casts.
- PASS Non-obvious API audit: contextual command arguments, `showModalDialog`, `ClipSlot.createMidiClip`, `MidiClip.notes`, and grouped-undo limits were verified against vendored SDK types; helper readiness uses an observable JSON handshake and authenticated HTTP polling with timeouts, never `sleep` plus bare assertion.

## Execution handoff

When implementation is authorized, use one of these modes:

1. **Subagent-Driven (recommended):** fresh implementation worker per task, followed by spec review and code-quality review before the next task.
2. **Inline Execution:** execute this plan in order with `superpowers:executing-plans`, stopping at review checkpoints and at Task 10.

No implementation mode is selected by this document. The owner chooses after reviewing the plan.
