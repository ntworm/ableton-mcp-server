# Groove Brain Gate 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Install one `.ablx`, open it on an empty Session slot, search the 4,000-groove seed by genre and BPM, pick a result, and get that groove's real notes written into the clip.

**Architecture:** The seed is exported at build time into a single JSON file that ships inside the `.ablx`. The Rust helper loads it once at startup and answers two endpoints over the loopback HTTP server it already runs — one to search, one to fetch a groove's notes. The extension converts ticks to beats and writes the clip through the SDK path Gate 0 already proved. Nothing at runtime needs Python, SQLite, or the MCP server.

**Tech Stack:** Rust (serde, serde_json — no new crates), TypeScript with the `@ableton-extensions/sdk`, plain-DOM UI, Python only at build time to produce the export.

---

## Why this shape and not another

Three ways to get the seed in front of the extension were on the table.

**Put SQLite in the helper.** The helper is 258 KB, has three dependencies, `panic = "abort"`, and a hand-rolled HTTP parser with an exact-match token check. Adding `rusqlite` with bundled SQLite plus a MIDI parser makes it a different kind of binary, and it would still have to reimplement the ranker, facet normalisation and cursors that live in Python.

**Proxy to the Python MCP server.** Correct in the long run and it reuses the real ranker, but it means the user installs and runs a second thing. The whole point of Gate 1 is one install.

**Ship an export.** Measured, not guessed: all 4,000 grooves with their facets and every note event serialise to **6.73 MB**, which deflates to **2.07 MB** inside the `.ablx`. The package goes from 155 KB to roughly 2.2 MB. The helper needs no new dependency, because it already has `serde_json`.

The export is what this plan builds. The cost is honest and stated in the non-goals: this is a snapshot with exact facet matching, not the ranker.

## What Gate 1 is not

- **Not the ranker.** Exact facet matching only, ordered by artifact id. No scoring, no free-text query, no cursors. `groove_search` in the MCP server keeps all of that; the extension gets the subset that answers "does this groove fit".
- **No preview or audition.** The candidate list shows facets and note count. Listening happens after the clip is written.
- **No generation, no transforms, no comparison.** Retrieval and insert only.
- **No Arrangement target.** Session slot only, the one that opened the panel, exactly as Gate 0.
- **No live seed reload.** The export is fixed at package time. Regenerating the seed means rebuilding the `.ablx`.

## Blocking owner decisions

### D1 — how many grooves ship

The whole seed is 4,000 grooves at 2.07 MB packaged. A 1,000-groove subset would be about 520 KB. **The plan ships all 4,000** unless the owner says otherwise; 2 MB is not a size worth optimising against, and a subset would make "the search found nothing" ambiguous between a bad query and a thin export.

### D2 — what happens to a groove longer than the clip

A groove can be 1, 2, 4 or 8 bars. **The plan creates the clip at the groove's own length** rather than a fixed 4 beats, so nothing is truncated. If the owner wants a fixed length with truncation instead, say so before Task 5.

## File Structure

| File | Responsibility |
| --- | --- |
| `scripts/export_groove_index.py` | Build-time: read the packaged seed, write `grooves.json`. The only Python in this feature. |
| `AbletonMCPServer_Extension/groove-brain-gate0/data/grooves.json` | Generated, git-ignored. The export the helper loads. |
| `.../helper/src/catalog.rs` | Parse the export, hold it in memory, answer facet queries. No I/O beyond the initial read. |
| `.../helper/src/server.rs` | Two new routes wired to `catalog.rs`. Existing auth, origin and bounds untouched. |
| `.../helper/src/protocol.rs` | The bootstrap line gains the export path. |
| `.../src/groove-client.ts` | Typed fetches against the two new endpoints. |
| `.../src/groove-writer.ts` | Ticks to beats, and the clip write. Split from `session-clip-probe.ts` so the Gate 0 probe stays intact. |
| `.../src/protocol.ts` | The modal result gains the chosen groove id. |
| `.../ui/app.js`, `index.html`, `styles.css` | Two inputs, a result list, a pick. |
| `.../package.ts` | Stage the export into the `.ablx`. |
| `.../tests/*.test.ts` | Node tests for the client, the writer and the UI events. |

---

### Task 1: Export the seed to a file the helper can read

**Files:**
- Create: `scripts/export_groove_index.py`
- Create: `tests/test_groove_export.py`
- Modify: `.gitignore`

- [ ] **Step 1: Write the failing test**

Create `tests/test_groove_export.py`:

```python
"""The export is the extension's whole view of the seed, so its shape is pinned."""

from __future__ import annotations

import json

from scripts.export_groove_index import build_export


def test_export_carries_facets_notes_and_timing(tmp_path) -> None:
    from tests.fixtures.groove_runtime import make_pilot_runtime

    runtime = make_pilot_runtime(tmp_path)
    export = build_export(runtime)

    assert export["schema"] == "groove.export.v1"
    assert export["grooves"], "an export with no grooves is a build failure, not an empty result"
    groove = export["grooves"][0]
    assert set(groove) == {"id", "genre", "bpm", "kit", "bars", "meter", "ppq", "notes"}
    assert isinstance(groove["ppq"], int) and groove["ppq"] > 0
    for note in groove["notes"]:
        pitch, start, duration, velocity = note
        assert 0 <= pitch <= 127
        assert start >= 0
        assert duration > 0
        assert 1 <= velocity <= 127


def test_export_is_deterministic(tmp_path) -> None:
    # The file lands in a shipped package. Two builds of one seed must not
    # produce two different bytes, or the package digest means nothing.
    from tests.fixtures.groove_runtime import make_pilot_runtime

    first = json.dumps(build_export(make_pilot_runtime(tmp_path / "a")), sort_keys=True)
    second = json.dumps(build_export(make_pilot_runtime(tmp_path / "b")), sort_keys=True)
    assert first == second


def test_export_carries_no_path_or_payload(tmp_path) -> None:
    # The seed is path-free by contract and the export must not reintroduce one.
    from tests.fixtures.groove_runtime import make_pilot_runtime

    blob = json.dumps(build_export(make_pilot_runtime(tmp_path)))
    for forbidden in ("C:\\\\", "/Users/", "payload", "blob", ".mid"):
        assert forbidden not in blob
```

- [ ] **Step 2: Run it to see it fail**

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_groove_export.py -q
```

Expected: `ModuleNotFoundError: No module named 'scripts.export_groove_index'`.

- [ ] **Step 3: Write the exporter**

Create `scripts/export_groove_index.py`:

```python
"""Export the packaged seed as a single file the Gate 1 helper can load.

The extension ships without Python, SQLite or a network dependency, so the seed
has to reach it as data inside the package. Measured on the 4,000-groove seed
this file is 6.7 MB, which deflates to 2.1 MB inside the .ablx.

Only what the extension can act on is exported: the three searchable axes, the
timing needed to place notes on a grid, and the notes themselves. No path, no
payload, no digest.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ableton_mcp_server.groove_intelligence.midi_lossless import decompress_bounded, parse_smf

DEFAULT_OUT = (
    Path(__file__).resolve().parents[1]
    / "AbletonMCPServer_Extension/groove-brain-gate0/data/grooves.json"
)

# Enough to identify a groove in a list of a few thousand without carrying a
# 64-character digest four thousand times.
ID_PREFIX_LENGTH = 16


def build_export(runtime: Any) -> dict[str, Any]:
    grooves: list[dict[str, Any]] = []
    for artifact_id in sorted(str(item) for item in runtime.index.manifest.artifact_ids):
        card = runtime.card(artifact_id)
        payload = runtime.store.get(artifact_id).payload
        parsed = parse_smf(
            decompress_bounded(payload.blob, codec=payload.codec, raw_size=payload.raw_size)
        )
        grooves.append(
            {
                "id": artifact_id[:ID_PREFIX_LENGTH],
                "genre": sorted(card.facets.get("genre", [])),
                "bpm": sorted(card.facets.get("bpm", [])),
                "kit": sorted(card.facets.get("kit", [])),
                "bars": card.summary.get("bars"),
                "meter": card.summary.get("meter"),
                "ppq": parsed.format.ppq,
                "notes": [
                    [note.pitch, note.start_ticks, note.duration_ticks, note.velocity]
                    for note in parsed.note_events
                ],
            }
        )
    return {"schema": "groove.export.v1", "grooves": grooves}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    from ableton_mcp_server.server import get_groove_runtime

    export = build_export(get_groove_runtime())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(export, separators=(",", ":")), encoding="utf-8")

    notes = sum(len(groove["notes"]) for groove in export["grooves"])
    print(f"[*] {len(export['grooves'])} grooves, {notes} notes")
    print(f"[*] {args.out} ({args.out.stat().st_size / 1024 / 1024:.2f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests until they pass**

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_groove_export.py -q
```

Expected: `3 passed`.

- [ ] **Step 5: Ignore the generated file**

Append to `.gitignore`:

```
AbletonMCPServer_Extension/groove-brain-gate0/data/
```

- [ ] **Step 6: Generate the real export and check the measured size**

```bash
.\.venv\Scripts\python.exe scripts\export_groove_index.py
```

Expected: `4000 grooves`, and a file of roughly 6.7 MB. A number far from that means the seed changed and the packaging estimate in Task 8 needs rechecking.

- [ ] **Step 7: Commit**

```bash
git add scripts/export_groove_index.py tests/test_groove_export.py .gitignore
git commit -m "feat(groove): export the seed as a file the extension can carry"
```

---

### Task 2: Teach the helper to load and query the export

**Files:**
- Create: `AbletonMCPServer_Extension/groove-brain-gate0/helper/src/catalog.rs`
- Modify: `AbletonMCPServer_Extension/groove-brain-gate0/helper/src/main.rs`

- [ ] **Step 1: Write the failing tests**

Create `catalog.rs` containing only its tests first, so `cargo test` fails for a reason you chose:

```rust
//! The exported seed, held in memory and queried by exact facet match.
//!
//! This is deliberately not the ranker. The Python `groove_search` scores,
//! normalises aliases and pages with cursors; reproducing that here would mean
//! maintaining it twice. Exact matching answers the question Gate 1 asks, and
//! the plan says so out loud rather than implying parity.

#[cfg(test)]
mod tests {
    use super::*;

    const SAMPLE: &str = r#"{
        "schema": "groove.export.v1",
        "grooves": [
            {"id":"a1","genre":["metal"],"bpm":["bpm_140_159"],"kit":["kick","snare"],
             "bars":4,"meter":"4/4","ppq":480,"notes":[[36,0,120,100]]},
            {"id":"b2","genre":["rock","pop_rock_country"],"bpm":["bpm_120_139"],
             "kit":["kick","hat_open"],"bars":2,"meter":"4/4","ppq":480,
             "notes":[[36,0,120,90],[42,240,60,70]]}
        ]
    }"#;

    fn catalog() -> Catalog {
        Catalog::from_str(SAMPLE).expect("sample parses")
    }

    #[test]
    fn rejects_an_export_of_the_wrong_schema() {
        let wrong = r#"{"schema":"groove.export.v2","grooves":[]}"#;
        assert!(Catalog::from_str(wrong).is_err());
    }

    #[test]
    fn an_empty_filter_returns_everything() {
        let hits = catalog().search(&Query::default());
        assert_eq!(hits.len(), 2);
    }

    #[test]
    fn filters_combine_as_and_across_axes() {
        let query = Query {
            genre: Some("rock".into()),
            bpm: Some("bpm_140_159".into()),
            kit: None,
        };
        assert!(catalog().search(&query).is_empty());
    }

    #[test]
    fn a_groove_matches_any_of_its_own_values_on_one_axis() {
        // The genre axis carries both vocabularies at once, so a groove filed
        // as rock and pop_rock_country has to answer to either.
        let by_path = Query { genre: Some("rock".into()), ..Query::default() };
        let by_vendor = Query { genre: Some("pop_rock_country".into()), ..Query::default() };
        assert_eq!(catalog().search(&by_path)[0].id, "b2");
        assert_eq!(catalog().search(&by_vendor)[0].id, "b2");
    }

    #[test]
    fn results_are_ordered_by_id_so_two_runs_agree() {
        let hits = catalog().search(&Query::default());
        assert_eq!(hits[0].id, "a1");
        assert_eq!(hits[1].id, "b2");
    }

    #[test]
    fn a_groove_is_fetched_by_its_id_and_missing_ids_are_none() {
        assert_eq!(catalog().groove("b2").unwrap().notes.len(), 2);
        assert!(catalog().groove("nope").is_none());
    }
}
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd AbletonMCPServer_Extension\groove-brain-gate0\helper
cargo test
```

Expected: compile errors — `cannot find type Catalog`, `cannot find type Query`.

- [ ] **Step 3: Write the implementation above the test module**

Insert at the top of `catalog.rs`, before `#[cfg(test)]`:

```rust
use serde::Deserialize;
use std::collections::HashMap;
use std::fs;
use std::path::Path;

pub const EXPORT_SCHEMA: &str = "groove.export.v1";

/// One note as the export writes it: pitch, start tick, duration in ticks, velocity.
pub type ExportedNote = [i64; 4];

#[derive(Debug, Deserialize, Clone)]
pub struct Groove {
    pub id: String,
    pub genre: Vec<String>,
    pub bpm: Vec<String>,
    pub kit: Vec<String>,
    pub bars: u32,
    pub meter: String,
    pub ppq: u32,
    pub notes: Vec<ExportedNote>,
}

#[derive(Debug, Deserialize)]
struct Export {
    schema: String,
    grooves: Vec<Groove>,
}

#[derive(Debug, Default, Clone)]
pub struct Query {
    pub genre: Option<String>,
    pub bpm: Option<String>,
    pub kit: Option<String>,
}

pub struct Catalog {
    grooves: Vec<Groove>,
    by_id: HashMap<String, usize>,
}

fn matches(values: &[String], wanted: &Option<String>) -> bool {
    match wanted {
        None => true,
        Some(value) => values.iter().any(|held| held == value),
    }
}

impl Catalog {
    pub fn from_str(raw: &str) -> Result<Self, &'static str> {
        let export: Export = serde_json::from_str(raw).map_err(|_| "EXPORT_MALFORMED")?;
        if export.schema != EXPORT_SCHEMA {
            return Err("EXPORT_SCHEMA_UNSUPPORTED");
        }
        let mut grooves = export.grooves;
        // Ordered once, at load, so every search answers in the same order
        // without sorting per request.
        grooves.sort_by(|left, right| left.id.cmp(&right.id));
        let by_id = grooves
            .iter()
            .enumerate()
            .map(|(index, groove)| (groove.id.clone(), index))
            .collect();
        Ok(Self { grooves, by_id })
    }

    pub fn load(path: &Path) -> Result<Self, &'static str> {
        let raw = fs::read_to_string(path).map_err(|_| "EXPORT_UNREADABLE")?;
        Self::from_str(&raw)
    }

    pub fn search(&self, query: &Query) -> Vec<&Groove> {
        self.grooves
            .iter()
            .filter(|groove| {
                matches(&groove.genre, &query.genre)
                    && matches(&groove.bpm, &query.bpm)
                    && matches(&groove.kit, &query.kit)
            })
            .collect()
    }

    pub fn groove(&self, id: &str) -> Option<&Groove> {
        self.by_id.get(id).map(|index| &self.grooves[*index])
    }

    pub fn len(&self) -> usize {
        self.grooves.len()
    }

    pub fn is_empty(&self) -> bool {
        self.grooves.is_empty()
    }
}
```

- [ ] **Step 4: Declare the module**

In `helper/src/main.rs`, add below `mod protocol;`:

```rust
mod catalog;
```

- [ ] **Step 5: Run the tests**

```bash
cd AbletonMCPServer_Extension\groove-brain-gate0\helper
cargo test
```

Expected: `test result: ok. 6 passed`.

- [ ] **Step 6: Commit**

```bash
git add AbletonMCPServer_Extension/groove-brain-gate0/helper/src/catalog.rs AbletonMCPServer_Extension/groove-brain-gate0/helper/src/main.rs
git commit -m "feat(gate1): load and query the exported seed in the helper"
```

---

### Task 3: Pass the export path through the bootstrap line

**Files:**
- Modify: `AbletonMCPServer_Extension/groove-brain-gate0/helper/src/protocol.rs`
- Modify: `AbletonMCPServer_Extension/groove-brain-gate0/helper/src/main.rs`
- Modify: `AbletonMCPServer_Extension/groove-brain-gate0/src/helper-process.ts`

The helper already receives a bootstrap JSON line on stdin carrying `ui_dir`, `token` and `parent_pid`. The export path joins it, so the helper never has to guess where the package put the file.

- [ ] **Step 1: Write the failing Rust test**

Append to the `#[cfg(test)]` module in `helper/src/protocol.rs`:

```rust
#[test]
fn bootstrap_carries_the_export_path() {
    let line = r#"{"protocol":1,"ui_dir":"C:/ui","token":"aaaa","parent_pid":42,"export_path":"C:/data/grooves.json"}"#;
    let bootstrap = parse_bootstrap(line).expect("parses");
    assert_eq!(bootstrap.export_path.to_string_lossy(), "C:/data/grooves.json");
}

#[test]
fn bootstrap_without_an_export_path_is_refused() {
    // Starting without it would leave a helper that serves the UI and answers
    // every search with nothing, which reads as an empty seed rather than a
    // broken launch.
    let line = r#"{"protocol":1,"ui_dir":"C:/ui","token":"aaaa","parent_pid":42}"#;
    assert!(parse_bootstrap(line).is_err());
}
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd AbletonMCPServer_Extension\groove-brain-gate0\helper
cargo test bootstrap
```

Expected: compile error — no field `export_path` on the bootstrap struct.

- [ ] **Step 3: Add the field**

In `helper/src/protocol.rs`, add `export_path` to the bootstrap struct beside `ui_dir`, with the same `PathBuf` type and the same required-field handling `ui_dir` already uses. Do not give it a default: the two tests above pin that an absent path is a refusal, not an empty catalog.

- [ ] **Step 4: Load the catalog at startup**

In `helper/src/main.rs`, after the UI asset check and before `server::bind_loopback()`:

```rust
    let catalog = catalog::Catalog::load(&bootstrap.export_path)
        .map_err(|code| code.to_owned())?;
    if catalog.is_empty() {
        return Err("EXPORT_EMPTY".into());
    }
```

Then pass `catalog` into `server::run(...)` as a new final argument, wrapped in `Arc`:

```rust
    server::run(listener, bootstrap.ui_dir, bootstrap.token, shutdown, Arc::new(catalog))?;
```

- [ ] **Step 5: Send the path from TypeScript**

In `groove-brain-gate0/src/helper-process.ts`, the runtime manifest already resolves `helper` relative to the runtime root. Add a sibling constant beside `HELPER_RELATIVE_PATH`:

```typescript
const EXPORT_RELATIVE_PATH = 'data/grooves.json';
```

Validate it the same way `manifest.helper` is validated, resolve it against the runtime root, and include it in the bootstrap object written to the child's stdin as `export_path`.

- [ ] **Step 6: Run both test suites**

```bash
cd AbletonMCPServer_Extension\groove-brain-gate0\helper
cargo test
cd ..\..\
npm run gate0:test
```

Expected: Rust green; the Node suite green, with `helper-process.test.ts` still passing because the bootstrap it asserts on gained a field rather than changing one.

- [ ] **Step 7: Commit**

```bash
git add AbletonMCPServer_Extension/groove-brain-gate0/helper/src AbletonMCPServer_Extension/groove-brain-gate0/src/helper-process.ts
git commit -m "feat(gate1): hand the helper the path to its exported seed"
```

---

### Task 4: Two HTTP routes

**Files:**
- Modify: `AbletonMCPServer_Extension/groove-brain-gate0/helper/src/server.rs`

`POST /api/search` takes `{genre?, bpm?, kit?, limit?}` and returns matches without their notes. `POST /api/groove` takes `{id}` and returns one groove with its notes. Notes are excluded from search results because a query matching a thousand grooves would otherwise return megabytes to render a list.

- [ ] **Step 1: Write the failing tests**

Append to the `#[cfg(test)]` module in `helper/src/server.rs`:

```rust
#[test]
fn search_route_is_recognised_and_health_still_is() {
    assert!(is_api_route("/api/search"));
    assert!(is_api_route("/api/groove"));
    assert!(is_api_route("/api/health"));
    assert!(!is_api_route("/api/../secret"));
    assert!(!is_api_route("/app.js"));
}

#[test]
fn a_search_body_becomes_a_query() {
    let query = parse_search_body(r#"{"genre":"metal","bpm":"bpm_140_159"}"#).unwrap();
    assert_eq!(query.genre.as_deref(), Some("metal"));
    assert_eq!(query.bpm.as_deref(), Some("bpm_140_159"));
    assert_eq!(query.kit, None);
}

#[test]
fn an_absent_body_is_an_empty_query_not_an_error() {
    assert_eq!(parse_search_body("{}").unwrap().genre, None);
}

#[test]
fn a_malformed_search_body_is_refused() {
    assert!(parse_search_body("not json").is_err());
    assert!(parse_search_body(r#"{"genre":42}"#).is_err());
}

#[test]
fn search_results_are_capped() {
    // A query matching everything must not return the whole export as one
    // response; the list is a picker, not a dump.
    let body = parse_search_body(r#"{"limit":9999}"#).unwrap();
    assert!(body.limit <= MAX_SEARCH_RESULTS);
}
```

- [ ] **Step 2: Run to verify failure**

```bash
cd AbletonMCPServer_Extension\groove-brain-gate0\helper
cargo test
```

Expected: `cannot find function is_api_route`, `cannot find function parse_search_body`.

- [ ] **Step 3: Implement the routes**

In `helper/src/server.rs`, add above `handle_connection`:

```rust
use crate::catalog::{Catalog, Groove, Query};
use std::sync::Arc;

/// A picker shows a page, not a corpus. Everything above this is the user's
/// filter being too broad, and a narrower filter is the answer.
pub const MAX_SEARCH_RESULTS: usize = 100;

pub fn is_api_route(path: &str) -> bool {
    matches!(path, "/api/health" | "/api/search" | "/api/groove")
}

#[derive(Debug, serde::Deserialize)]
pub struct SearchBody {
    #[serde(default)]
    pub genre: Option<String>,
    #[serde(default)]
    pub bpm: Option<String>,
    #[serde(default)]
    pub kit: Option<String>,
    #[serde(default = "default_limit")]
    pub limit: usize,
}

fn default_limit() -> usize {
    MAX_SEARCH_RESULTS
}

pub fn parse_search_body(raw: &str) -> Result<SearchBody, &'static str> {
    let mut body: SearchBody = serde_json::from_str(raw).map_err(|_| "INVALID_SEARCH_BODY")?;
    body.limit = body.limit.min(MAX_SEARCH_RESULTS);
    Ok(body)
}

impl SearchBody {
    pub fn query(&self) -> Query {
        Query {
            genre: self.genre.clone(),
            bpm: self.bpm.clone(),
            kit: self.kit.clone(),
        }
    }
}

#[derive(serde::Serialize)]
struct SearchHit<'a> {
    id: &'a str,
    genre: &'a [String],
    bpm: &'a [String],
    kit: &'a [String],
    bars: u32,
    meter: &'a str,
    note_count: usize,
}

pub fn search_response(catalog: &Catalog, body: &SearchBody) -> String {
    let hits = catalog.search(&body.query());
    let total = hits.len();
    let items: Vec<SearchHit> = hits
        .into_iter()
        .take(body.limit)
        .map(|groove| SearchHit {
            id: &groove.id,
            genre: &groove.genre,
            bpm: &groove.bpm,
            kit: &groove.kit,
            bars: groove.bars,
            meter: &groove.meter,
            note_count: groove.notes.len(),
        })
        .collect();
    serde_json::json!({"total": total, "returned": items.len(), "items": items}).to_string()
}

pub fn groove_response(catalog: &Catalog, id: &str) -> Option<String> {
    catalog.groove(id).map(|groove| {
        serde_json::to_string(&serde_json::json!({
            "id": groove.id,
            "bars": groove.bars,
            "meter": groove.meter,
            "ppq": groove.ppq,
            "notes": groove.notes,
        }))
        .unwrap_or_else(|_| "{}".to_string())
    })
}
```

- [ ] **Step 4: Wire them into `handle_connection`**

The existing `/api/health` arm already checks `request.method != "POST"`, the `Origin` header and the bearer token. Extend that same arm to cover all three API paths using `is_api_route`, then branch on `request.path` after the checks — so `/api/search` and `/api/groove` inherit every guard `/api/health` has rather than repeating them. A `/api/groove` with an unknown id returns 404, not an empty groove: the caller asked for a specific thing.

`handle_connection` and `run` both take the new `Arc<Catalog>` argument.

- [ ] **Step 5: Run the tests**

```bash
cd AbletonMCPServer_Extension\groove-brain-gate0\helper
cargo test
```

Expected: all green, including the pre-existing `parses_exact_local_request`, `token_comparison_is_exact` and `only_known_assets_resolve`.

- [ ] **Step 6: Commit**

```bash
git add AbletonMCPServer_Extension/groove-brain-gate0/helper/src/server.rs
git commit -m "feat(gate1): serve search and groove fetch from the helper"
```

---

### Task 5: Convert ticks to beats and write the clip

**Files:**
- Create: `AbletonMCPServer_Extension/groove-brain-gate0/src/groove-writer.ts`
- Create: `AbletonMCPServer_Extension/groove-brain-gate0/tests/groove-writer.test.ts`

Gate 0 writes `startTime: 0..3, duration: 0.25` — the SDK takes **beats**, while the export carries **ticks**. This is where that conversion lives, kept out of `session-clip-probe.ts` so the Gate 0 probe keeps working unchanged.

- [ ] **Step 1: Write the failing test**

Create `tests/groove-writer.test.ts`:

```typescript
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { clipLengthBeats, toClipNotes } from '../src/groove-writer.js';

const GROOVE = {
  id: 'a1',
  bars: 2,
  meter: '4/4',
  ppq: 480,
  notes: [
    [36, 0, 120, 100],
    [42, 240, 60, 70],
    [38, 960, 120, 110],
  ] as [number, number, number, number][],
};

test('ticks become beats at the groove own resolution', () => {
  const notes = toClipNotes(GROOVE);
  assert.deepEqual(notes[0], { pitch: 36, startTime: 0, duration: 0.25, velocity: 100 });
  assert.deepEqual(notes[1], { pitch: 42, startTime: 0.5, duration: 0.125, velocity: 70 });
  assert.deepEqual(notes[2], { pitch: 38, startTime: 2, duration: 0.25, velocity: 110 });
});

test('a zero or negative duration is lifted to the shortest audible note', () => {
  // A drum hit exported with a zero-length duration is still a hit. Writing a
  // zero-length note produces a clip Live shows as empty at that position.
  const notes = toClipNotes({ ...GROOVE, notes: [[36, 0, 0, 100]] });
  assert.ok(notes[0].duration > 0);
});

test('the clip is long enough for the whole groove', () => {
  assert.equal(clipLengthBeats(GROOVE), 8);
});

test('an odd meter still gets a clip that fits', () => {
  // 6/8 at two bars is six eighth-notes twice: three beats, not eight.
  assert.equal(clipLengthBeats({ ...GROOVE, bars: 2, meter: '6/8' }), 6);
});

test('an unreadable meter falls back to four four rather than throwing', () => {
  assert.equal(clipLengthBeats({ ...GROOVE, meter: 'nonsense' }), 8);
});

test('a groove whose notes run past its stated bars is not truncated', () => {
  // The bar count is metadata; the notes are the groove. A clip shorter than
  // the last note silently drops it.
  const long = { ...GROOVE, bars: 1, notes: [[36, 0, 120, 100], [38, 3840, 120, 100]] as [number, number, number, number][] };
  assert.ok(clipLengthBeats(long) >= 9);
});
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd AbletonMCPServer_Extension
npx tsx --test groove-brain-gate0/tests/groove-writer.test.ts
```

Expected: `Cannot find module '../src/groove-writer.js'`.

- [ ] **Step 3: Implement**

Create `src/groove-writer.ts`:

```typescript
/**
 * The export speaks ticks; the SDK speaks beats. This is the only place that
 * conversion happens, so a rounding decision is made once.
 */

export interface ExportedGroove {
  id: string;
  bars: number;
  meter: string;
  ppq: number;
  notes: [number, number, number, number][];
}

export interface ClipNote {
  pitch: number;
  startTime: number;
  duration: number;
  velocity: number;
}

// A thirty-second note at 4/4. Shorter than this and Live renders nothing
// visible, so a hit exported with no length still has to become one.
const MIN_DURATION_BEATS = 0.125;

function beatsPerBar(meter: string): number {
  const [numerator, denominator] = meter.split('/').map((part) => Number.parseInt(part, 10));
  if (!Number.isFinite(numerator) || !Number.isFinite(denominator) || denominator === 0) {
    return 4;
  }
  return (numerator * 4) / denominator;
}

export function toClipNotes(groove: ExportedGroove): ClipNote[] {
  const ppq = groove.ppq > 0 ? groove.ppq : 480;
  return groove.notes.map(([pitch, startTicks, durationTicks, velocity]) => ({
    pitch,
    startTime: startTicks / ppq,
    duration: Math.max(MIN_DURATION_BEATS, durationTicks / ppq),
    velocity,
  }));
}

export function clipLengthBeats(groove: ExportedGroove): number {
  const stated = groove.bars * beatsPerBar(groove.meter);
  const notes = toClipNotes(groove);
  const lastEnd = notes.reduce((furthest, note) => Math.max(furthest, note.startTime + note.duration), 0);
  // Whichever is longer. The bar count is metadata and can disagree with the
  // notes; a clip shorter than the last note silently drops it.
  return Math.max(stated, Math.ceil(lastEnd));
}
```

- [ ] **Step 4: Run the tests**

```bash
cd AbletonMCPServer_Extension
npx tsx --test groove-brain-gate0/tests/groove-writer.test.ts
```

Expected: `pass 6`.

- [ ] **Step 5: Commit**

```bash
git add AbletonMCPServer_Extension/groove-brain-gate0/src/groove-writer.ts AbletonMCPServer_Extension/groove-brain-gate0/tests/groove-writer.test.ts
git commit -m "feat(gate1): convert exported ticks to the beats the SDK writes"
```

---

### Task 6: A typed client for the two endpoints

**Files:**
- Create: `AbletonMCPServer_Extension/groove-brain-gate0/src/groove-client.ts`
- Create: `AbletonMCPServer_Extension/groove-brain-gate0/tests/groove-client.test.ts`

- [ ] **Step 1: Write the failing test**

Create `tests/groove-client.test.ts`:

```typescript
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { parseGrooveResponse, parseSearchResponse } from '../src/groove-client.js';

test('a search response becomes typed hits', () => {
  const parsed = parseSearchResponse(JSON.stringify({
    total: 103,
    returned: 1,
    items: [{ id: 'a1', genre: ['metal'], bpm: ['bpm_140_159'], kit: ['kick'], bars: 4, meter: '4/4', note_count: 12 }],
  }));
  assert.equal(parsed.total, 103);
  assert.equal(parsed.items[0].id, 'a1');
  assert.equal(parsed.items[0].noteCount, 12);
});

test('a groove response becomes a writable groove', () => {
  const parsed = parseGrooveResponse(JSON.stringify({
    id: 'a1', bars: 2, meter: '4/4', ppq: 480, notes: [[36, 0, 120, 100]],
  }));
  assert.equal(parsed.ppq, 480);
  assert.equal(parsed.notes.length, 1);
});

test('a malformed payload is refused rather than half-read', () => {
  assert.throws(() => parseSearchResponse('not json'), /INVALID_SEARCH_RESPONSE/);
  assert.throws(() => parseSearchResponse('{"total":1}'), /INVALID_SEARCH_RESPONSE/);
  assert.throws(() => parseGrooveResponse('{"id":"a1"}'), /INVALID_GROOVE_RESPONSE/);
});

test('a note that is not four numbers is refused', () => {
  // The notes go straight into Live. A short tuple would write a NaN start.
  assert.throws(
    () => parseGrooveResponse('{"id":"a1","bars":1,"meter":"4/4","ppq":480,"notes":[[36,0]]}'),
    /INVALID_GROOVE_RESPONSE/,
  );
});
```

- [ ] **Step 2: Run to verify failure**

```bash
cd AbletonMCPServer_Extension
npx tsx --test groove-brain-gate0/tests/groove-client.test.ts
```

Expected: `Cannot find module '../src/groove-client.js'`.

- [ ] **Step 3: Implement**

Create `src/groove-client.ts`:

```typescript
/**
 * Parsing for the two helper endpoints.
 *
 * The helper is local and authenticated, but its output still goes straight
 * into Live, so a malformed field is refused here rather than written as NaN.
 */

import type { ExportedGroove } from './groove-writer.js';

export interface SearchHit {
  id: string;
  genre: string[];
  bpm: string[];
  kit: string[];
  bars: number;
  meter: string;
  noteCount: number;
}

export interface SearchResponse {
  total: number;
  items: SearchHit[];
}

function object(raw: string, code: string): Record<string, unknown> {
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    throw new Error(code);
  }
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error(code);
  return value as Record<string, unknown>;
}

function strings(value: unknown, code: string): string[] {
  if (!Array.isArray(value) || value.some((item) => typeof item !== 'string')) throw new Error(code);
  return value as string[];
}

export function parseSearchResponse(raw: string): SearchResponse {
  const code = 'INVALID_SEARCH_RESPONSE';
  const candidate = object(raw, code);
  if (typeof candidate.total !== 'number' || !Array.isArray(candidate.items)) throw new Error(code);
  const items = candidate.items.map((entry) => {
    if (!entry || typeof entry !== 'object') throw new Error(code);
    const hit = entry as Record<string, unknown>;
    if (
      typeof hit.id !== 'string'
      || typeof hit.bars !== 'number'
      || typeof hit.meter !== 'string'
      || typeof hit.note_count !== 'number'
    ) {
      throw new Error(code);
    }
    return {
      id: hit.id,
      genre: strings(hit.genre, code),
      bpm: strings(hit.bpm, code),
      kit: strings(hit.kit, code),
      bars: hit.bars,
      meter: hit.meter,
      noteCount: hit.note_count,
    };
  });
  return { total: candidate.total, items };
}

export function parseGrooveResponse(raw: string): ExportedGroove {
  const code = 'INVALID_GROOVE_RESPONSE';
  const candidate = object(raw, code);
  if (
    typeof candidate.id !== 'string'
    || typeof candidate.bars !== 'number'
    || typeof candidate.meter !== 'string'
    || typeof candidate.ppq !== 'number'
    || !Array.isArray(candidate.notes)
  ) {
    throw new Error(code);
  }
  const notes = candidate.notes.map((note) => {
    if (!Array.isArray(note) || note.length !== 4 || note.some((n) => typeof n !== 'number')) {
      throw new Error(code);
    }
    return note as [number, number, number, number];
  });
  return {
    id: candidate.id,
    bars: candidate.bars,
    meter: candidate.meter,
    ppq: candidate.ppq,
    notes,
  };
}
```

- [ ] **Step 4: Run the tests**

```bash
cd AbletonMCPServer_Extension
npx tsx --test groove-brain-gate0/tests/groove-client.test.ts
```

Expected: `pass 4`.

- [ ] **Step 5: Commit**

```bash
git add AbletonMCPServer_Extension/groove-brain-gate0/src/groove-client.ts AbletonMCPServer_Extension/groove-brain-gate0/tests/groove-client.test.ts
git commit -m "feat(gate1): parse the helper responses before they reach Live"
```

---

### Task 7: The picker UI and the chosen groove

**Files:**
- Modify: `AbletonMCPServer_Extension/groove-brain-gate0/ui/index.html`
- Modify: `AbletonMCPServer_Extension/groove-brain-gate0/ui/app.js`
- Modify: `AbletonMCPServer_Extension/groove-brain-gate0/ui/styles.css`
- Modify: `AbletonMCPServer_Extension/groove-brain-gate0/src/protocol.ts`
- Modify: `AbletonMCPServer_Extension/groove-brain-gate0/tests/modal-result.test.ts`
- Modify: `AbletonMCPServer_Extension/groove-brain-gate0/src/session-clip-probe.ts`
- Modify: `AbletonMCPServer_Extension/groove-brain-gate0/src/extension.ts`

- [ ] **Step 1: Write the failing protocol test**

Replace the `run_session_probe` cases in `tests/modal-result.test.ts` with:

```typescript
test('an insert result carries the groove the user picked', () => {
  const result = parseModalResult(JSON.stringify({
    protocol: 1, action: 'insert_groove', confirmed: true, groove_id: 'a1b2c3d4e5f60718',
  }));
  assert.equal(result.action, 'insert_groove');
  assert.equal(result.confirmed, true);
  assert.equal(result.grooveId, 'a1b2c3d4e5f60718');
});

test('an insert without a groove id is refused', () => {
  // Confirming without a selection would write whatever happened to be first.
  assert.throws(
    () => parseModalResult(JSON.stringify({ protocol: 1, action: 'insert_groove', confirmed: true })),
    /INVALID_MODAL_RESULT/,
  );
});

test('cancel still needs no groove', () => {
  const result = parseModalResult(JSON.stringify({ protocol: 1, action: 'cancel', confirmed: false }));
  assert.equal(result.action, 'cancel');
});
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd AbletonMCPServer_Extension
npx tsx --test groove-brain-gate0/tests/modal-result.test.ts
```

Expected: failures on the two `insert_groove` cases.

- [ ] **Step 3: Extend the modal result**

In `src/protocol.ts`, replace the `ModalResult` union and the matching branch in `parseModalResult`:

```typescript
export type ModalResult =
  | { action: 'cancel'; confirmed: false; protocol: 1 }
  | { action: 'insert_groove'; confirmed: true; protocol: 1; grooveId: string };
```

and in `parseModalResult`, after the cancel branch:

```typescript
  if (
    candidate.action === 'insert_groove'
    && candidate.confirmed === true
    && typeof candidate.groove_id === 'string'
    && candidate.groove_id.length > 0
  ) {
    return {
      action: 'insert_groove',
      confirmed: true,
      protocol: GATE0_PROTOCOL,
      grooveId: candidate.groove_id,
    };
  }
```

- [ ] **Step 4: Rewrite the panel body**

In `ui/index.html`, replace the `<section id="controls">` block:

```html
      <section id="controls" hidden>
        <div class="filters">
          <label>Gênero <input id="genre" list="genres" placeholder="metal" autocomplete="off"></label>
          <label>BPM <select id="bpm">
            <option value="">qualquer</option>
            <option value="bpm_60_79">60–79</option>
            <option value="bpm_80_99">80–99</option>
            <option value="bpm_100_119">100–119</option>
            <option value="bpm_120_139">120–139</option>
            <option value="bpm_140_159">140–159</option>
            <option value="bpm_160_179">160–179</option>
            <option value="bpm_180_plus">180+</option>
          </select></label>
          <button id="search">Buscar</button>
        </div>
        <datalist id="genres"></datalist>
        <p id="count" class="count"></p>
        <ul id="results"></ul>
        <p>O groove escolhido será escrito no slot vazio que abriu este painel.</p>
        <button id="insert" disabled>Inserir groove</button>
        <button id="cancel" class="secondary">Cancelar</button>
      </section>
```

- [ ] **Step 5: Rewrite the panel behaviour**

Two things about the current `ui/app.js` that this step depends on. The token is
read from `window.location.hash` inside `bootstrap()` and never leaves that
scope, so it has to be hoisted before any other request can send it. And the old
handlers reference `confirmNode` and `runNode`, which the new markup no longer
has, so leaving them in place throws on a null element before the panel renders.

Keep `closeAndSend`, `showTerminalError`, `submit` and the whole health
handshake. Hoist the token, and replace the three handlers at the bottom of the
file:

```javascript
const genreNode = document.querySelector('#genre');
const bpmNode = document.querySelector('#bpm');
const searchNode = document.querySelector('#search');
const resultsNode = document.querySelector('#results');
const countNode = document.querySelector('#count');
const insertNode = document.querySelector('#insert');

// Hoisted out of bootstrap(): the search calls need it too, and the URL it
// arrived in is erased on the first line of the handshake.
let bearer = null;
let selectedId = null;

async function api(path, body) {
  const response = await fetch(path, {
    method: 'POST',
    headers: { Authorization: `Bearer ${bearer}`, 'Content-Type': 'application/json' },
    cache: 'no-store',
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`HELPER_${path.replace(/\W/g, '_').toUpperCase()}_${response.status}`);
  return response.json();
}

function select(id, node) {
  selectedId = id;
  for (const li of resultsNode.children) li.classList.toggle('selected', li === node);
  insertNode.disabled = false;
}

function render(payload) {
  selectedId = null;
  insertNode.disabled = true;
  resultsNode.replaceChildren();
  countNode.textContent = `${payload.total} encontrados, mostrando ${payload.items.length}`;
  for (const item of payload.items) {
    const li = document.createElement('li');
    li.textContent = `${item.bars} compassos ${item.meter} · ${item.note_count} notas · ${item.kit.join(' ')}`;
    li.addEventListener('click', () => select(item.id, li));
    resultsNode.append(li);
  }
}

searchNode.addEventListener('click', () => {
  const body = {};
  if (genreNode.value.trim()) body.genre = genreNode.value.trim();
  if (bpmNode.value) body.bpm = bpmNode.value;
  api('/api/search', body).then(render).catch(showTerminalError);
});

insertNode.addEventListener('click', () => {
  if (!selectedId) return;
  submit({ protocol: 1, action: 'insert_groove', confirmed: true, groove_id: selectedId });
});

document.querySelector('#cancel').addEventListener('click', () => {
  submit({ action: 'cancel', confirmed: false, protocol: 1 });
});
```

In `bootstrap()`, replace `const token = window.location.hash.slice(1);` with
`bearer = window.location.hash.slice(1);`, change the two later uses of `token`
to `bearer`, and keep the `history.replaceState` and the format check exactly as
they are.

`insertNode` starts disabled in the markup and is only enabled by `select`,
which is what the "an insert without a groove id is refused" test pins from the
other side of the boundary.

- [ ] **Step 6: Write the groove instead of the fixed probe**

In `src/session-clip-probe.ts`, change `runSessionClipProbe` to take the notes and clip length as arguments rather than reading the module-level `NOTES`, keeping every existing guard, the readback and the hash comparison. The Gate 0 tests keep passing by passing the same `NOTES` and `4`.

In `src/extension.ts`, after `parseModalResult` returns an `insert_groove`, fetch `/api/groove` with the id, run it through `parseGrooveResponse`, then `toClipNotes` and `clipLengthBeats`, and hand both to the probe.

- [ ] **Step 7: Run the whole Node suite and the typechecker**

```bash
cd AbletonMCPServer_Extension
npm run gate0:typecheck
npm run gate0:test
```

Expected: typecheck clean, every test green including `session-clip-probe.test.ts` and `ui-events.test.ts`.

- [ ] **Step 8: Commit**

```bash
git add AbletonMCPServer_Extension/groove-brain-gate0/ui AbletonMCPServer_Extension/groove-brain-gate0/src AbletonMCPServer_Extension/groove-brain-gate0/tests
git commit -m "feat(gate1): search, pick and insert a real groove"
```

---

### Task 8: Package the export into the .ablx

**Files:**
- Modify: `AbletonMCPServer_Extension/groove-brain-gate0/package.ts`
- Modify: `AbletonMCPServer_Extension/groove-brain-gate0/tests/package-safety.test.ts`
- Modify: `AbletonMCPServer_Extension/package.json`

- [ ] **Step 1: Write the failing test**

Append to `tests/package-safety.test.ts` a case asserting that the staged package contains `data/grooves.json`, that its parsed `schema` is `groove.export.v1`, and that the staged tree contains no `.sqlite` file — the export ships, the seed database does not.

- [ ] **Step 2: Run it to verify it fails**

```bash
cd AbletonMCPServer_Extension
npx tsx --test groove-brain-gate0/tests/package-safety.test.ts
```

Expected: the new case fails because nothing stages `data/grooves.json`.

- [ ] **Step 3: Stage the export**

In `package.ts`, beside the existing `fs.copyFileSync(helperSource, helperTarget)`, copy `data/grooves.json` into `data/grooves.json` under the staging root, creating the directory first. Fail the build with a named error if the file is absent rather than shipping a package whose every search returns nothing.

- [ ] **Step 4: Add the export step to the package script**

In `AbletonMCPServer_Extension/package.json`, change the `gate0:package` script so the export is regenerated before the package is built:

```json
    "gate0:export": "python ../.venv/Scripts/python.exe ../scripts/export_groove_index.py",
    "gate0:package": "npm run gate0:build && tsx groove-brain-gate0/package.ts --version 0.2.0"
```

Run `gate0:export` by hand before `gate0:package`; wiring Python into an npm script that also runs on a machine without the venv would make the package build depend on a Python install.

- [ ] **Step 5: Build the package and check its size**

```bash
cd C:\Users\Usuario\repos\ableton-mcp-server
.\.venv\Scripts\python.exe scripts\export_groove_index.py
cd AbletonMCPServer_Extension
npm run gate0:package
```

Expected: `Groove-Brain-Gate-0-0.2.0.ablx` of roughly **2.2 MB**, against the 155 KB of 0.1.3. A package near 155 KB means the export was not staged.

- [ ] **Step 6: Commit**

```bash
git add AbletonMCPServer_Extension/groove-brain-gate0/package.ts AbletonMCPServer_Extension/groove-brain-gate0/tests/package-safety.test.ts AbletonMCPServer_Extension/package.json
git commit -m "feat(gate1): ship the exported seed inside the package"
```

---

### Task 9: Install it and use it

**Files:**
- Create: `docs/superpowers/plans/2026-09-02-groove-brain-gate-1-result.md`

- [ ] **Step 1: Install**

Install `AbletonMCPServer_Extension/build/groove-brain-gate0/Groove-Brain-Gate-0-0.2.0.ablx` in Live, restart, and open the panel on an **empty** Session slot.

- [ ] **Step 2: Search**

Type `metal` in the genre field, pick `140–159`, press Buscar.

Expected: a count near **103**, which is what the same query returns from the Python side. A very different number means the export and the seed disagree.

- [ ] **Step 3: Insert and listen**

Pick a result, press Inserir groove. The clip appears in the slot with that groove's real notes.

Expected: the hi-hats are audible as hi-hats. This is the whole point of the seed regeneration and it has never been heard.

- [ ] **Step 4: Check the same query on both sides**

```bash
cd C:\Users\Usuario\repos\ableton-mcp-server && .\.venv\Scripts\python.exe -c "from ableton_mcp_server.server import get_groove_runtime; from ableton_mcp_server.groove_intelligence.mcp_models import SearchRequestV1; from ableton_mcp_server.groove_intelligence.search import search; r=get_groove_runtime(); print(search(r, SearchRequestV1(schema_version='groove.search.request.v1', query=None, facets={'genre':['metal'],'bpm':['bpm_140_159']}, limit=1, cursor=None)).total_hint)"
```

Expected: the same total the panel showed. They filter the same facets, so a difference is a bug in the export, not a ranking difference — the ranker only reorders.

- [ ] **Step 5: Write the result document**

Record the package size, the counts on both sides, how long the helper took to load the export, and — the only thing that matters — whether the grooves sounded like their facets said they would.

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/plans/2026-09-02-groove-brain-gate-1-result.md
git commit -m "docs: record the Gate 1 result"
```

---

## Stop condition

Gate 1 is done when one `.ablx` install lets someone search by genre and BPM inside Live and hear the chosen groove in a clip, without Python, without the MCP server, and without a second install.

It is **not** done if the panel works but the counts disagree with `groove_search` for the same facets: that means the export is not the seed, and everything measured about the seed stops applying to what the user hears.
