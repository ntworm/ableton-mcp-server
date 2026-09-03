# Groove Brain Gate 3 — Session Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A panel on the phone that shows the Live set as it is — tracks, tempo, what is already in each clip — and writes a generated or retrieved drum part into the track and slot you choose.

**Architecture:** The extension reads and writes the session directly through the Ableton SDK; no MCP server, no Remote Script, no second process. The helper is a relay: it holds the last session snapshot the extension pushed and the last command the panel posted. Generation runs in the extension, over a groove drawn from the packaged seed.

**Tech Stack:** TypeScript against `@ableton-extensions/sdk`, the existing Rust helper, plain-DOM panel.

---

## What Gate 2 got wrong

Gate 2 shipped a library browser: four thousand grooves, a genre field, a BPM bucket. It never looked at the Live set. It could not say which tracks existed, what was already in a clip, or what tempo the song ran at, and the only thing it could do was drop a groove into the one slot that had been right-clicked.

That is not a production tool, and the owner said so on first contact with it. This plan replaces the panel. The seed and its export stay — four thousand real grooves are the raw material — but they stop being the product.

## The fact that decides the architecture

The SDK already gives the extension everything the panel needs:

| Need | SDK |
| --- | --- |
| Which tracks exist | `Song.tracks`, `Track.name` |
| Which are MIDI, which are armed | `MidiTrack`, `Track.arm` |
| What is in a clip | `ClipSlot.clip`, `MidiClip.notes` |
| Tempo and meter | `Song.tempo`, `MidiTrack.signatureNumerator` |
| Which kit is loaded | `Track.devices`, `DrumRack.chains` |
| Write | `ClipSlot.createMidiClip`, `MidiClip.notes =` |

So the earlier idea of bridging to the MCP server is wrong and this plan does not do it. The MCP server's tools exist to give an *agent* access to Live; the extension has that access natively, and adding a second process would buy nothing and cost an install.

What the SDK does **not** give is a non-blocking window. `Ui` offers exactly `registerContextMenuAction`, `showModalDialog` and `showProgressDialog`. A modal blocks Live while open, which is why the panel lives in a browser. That part of Gate 2 was right and is kept.

## Shape of the thing

```
Live  ──SDK──  extension  ──HTTP──  helper  ──HTTP──  panel (phone)
               reads session          holds:            shows session
               runs generation        - snapshot        posts commands
               writes clips           - command queue
```

The extension pushes a snapshot whenever it changes, and polls for commands. The panel renders the snapshot and posts commands. Neither side blocks the other, and Live stays usable throughout.

## What the mapping investigation changed

This plan was written before the note map was measured. Two of its assumptions
did not survive, and the corrections are load-bearing rather than cosmetic.

**A profile belongs to a kit, not to a plugin.** Reading Settings > MIDI
In/E-Drums twice, with two kits loaded and no edit by the user, gives two
different maps: note 76 moved from Snare Sidestick to Ride Crescendo and note
70's articulation moved to note 4, with every row still reporting `Edited: No`.
Section 12.4 of the design calls the structural signature optional; it is not.
The kit name is in the SD3 header, and the profile is keyed by it.

**A hi-hat is two dimensions.** SD3 spends 35 notes on it: openness runs tight,
closed, then open in six graded steps, and the strike zone is separately pedal,
edge, tip, shank or bell. The `hat_closed` / `hat_open` / `hat_pedal` ontology
cannot represent the half-open hats that make up most of that range.

**What is now measured, and is why the panel is worth building.** With a full
kit loaded, 97.5% to 98.3% of the seed's notes reach the drum they were
recorded for. Under 1% land on the wrong drum. The rest are articulations the
loaded instrument does not have, and those are what Task 4a exists for.

## Blocking owner decisions

### D1 — what "generate" means in this Gate

Two honest options, and the plan takes the first.

**Retrieve and transform.** Draw a groove from the seed that matches the requested genre and feel, then apply the deterministic transforms — density, swing, microtiming, energy, complexity, syncopation, polyrhythm — that already exist in `deterministic.py` and are pinned by tests. Porting those seven to TypeScript is about a hundred lines whose behaviour is already specified.

**Synthesise from scratch.** Build a pattern from a grid and a rule set, the way `music_generate_drum_groove` does. Better in principle, but it means porting a second body of Python and Gate 3 would ship later with nothing to hear.

**The plan does retrieve-and-transform.** It reuses four thousand real performances instead of inventing one, and the knobs are the same knobs the deterministic engine already exposes.

### D2 — where a generated part lands

The panel names both the track and the slot, and writing into a filled slot requires an explicit replace. The old behaviour — write into whatever was right-clicked — disappears, because the panel now knows about every track and the right-click is only how the panel is opened.

## File Structure

| File | Responsibility |
| --- | --- |
| `src/session-snapshot.ts` | Read `Song` into a plain object the panel can render. No writes. |
| `src/session-writer.ts` | Apply one command: create or replace a clip, write notes. |
| `src/transforms.ts` | The seven deterministic transforms, ported from `deterministic.py`. |
| `src/command.ts` | Parse and validate what the panel posts before it reaches Live. |
| `helper/src/relay.rs` | Hold the snapshot and the command queue. Replaces `Selection`. |
| `ui/picker.html`, `picker.js` | Track list, clip state, generation controls. |
| `tests/*` | One test file per module above. |

---

### Task 1: Read the session into something the panel can render

**Files:**
- Create: `AbletonMCPServer_Extension/groove-brain-gate0/src/session-snapshot.ts`
- Create: `AbletonMCPServer_Extension/groove-brain-gate0/tests/session-snapshot.test.ts`

- [ ] **Step 1: Write the failing test**

```typescript
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { snapshotSession } from '../src/session-snapshot.js';

function fakeSong() {
  return {
    tempo: 128,
    tracks: [
      {
        name: 'Superior Drummer 3',
        arm: true,
        signatureNumerator: 4,
        signatureDenominator: 4,
        devices: [{ className: 'DrumRack', name: 'SD3' }],
        clipSlots: [
          { clip: null },
          { clip: { name: 'Verse', notes: [{ pitch: 36, startTime: 0, duration: 0.25 }] } },
        ],
      },
      { name: 'Bass', arm: false, devices: [], clipSlots: [{ clip: null }] },
    ],
  };
}

test('the snapshot names every track and says what is in each slot', () => {
  const snapshot = snapshotSession(fakeSong());
  assert.equal(snapshot.tempo, 128);
  assert.equal(snapshot.tracks.length, 2);

  const drums = snapshot.tracks[0];
  assert.equal(drums.name, 'Superior Drummer 3');
  assert.equal(drums.index, 0);
  assert.equal(drums.armed, true);
  assert.equal(drums.hasDrumRack, true);
  assert.equal(drums.meter, '4/4');
  assert.deepEqual(drums.slots[0], { index: 0, filled: false, name: null, noteCount: 0 });
  assert.deepEqual(drums.slots[1], { index: 1, filled: true, name: 'Verse', noteCount: 1 });
});

test('a track with no drum rack is marked as such rather than omitted', () => {
  // The panel still offers it; writing drums onto a bass track is the user's
  // call, and hiding the track would make the set look wrong.
  const snapshot = snapshotSession(fakeSong());
  assert.equal(snapshot.tracks[1].hasDrumRack, false);
});

test('a clip that cannot be read counts as filled with unknown contents', () => {
  // Reading notes off an audio clip throws. The slot is still occupied, and
  // saying "0 notes" would invite an overwrite the user did not intend.
  const song = fakeSong();
  song.tracks[0].clipSlots[1] = {
    clip: {
      name: 'Audio',
      get notes(): never {
        throw new Error('NOT_A_MIDI_CLIP');
      },
    },
  };
  const slot = snapshotSession(song).tracks[0].slots[1];
  assert.equal(slot.filled, true);
  assert.equal(slot.noteCount, null);
});
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd AbletonMCPServer_Extension && npx tsx --test groove-brain-gate0/tests/session-snapshot.test.ts
```

Expected: `Cannot find module '../src/session-snapshot.js'`.

- [ ] **Step 3: Write the reader**

```typescript
/**
 * The Live set as a plain object the panel can render.
 *
 * Read-only by construction: nothing here creates, deletes or modifies. The
 * panel needs to know what exists before it can ask for a change, and a reader
 * that could also write would make every render a risk.
 */

export interface SlotState {
  index: number;
  filled: boolean;
  name: string | null;
  /** Null when the clip exists but its notes cannot be read, as for audio. */
  noteCount: number | null;
}

export interface TrackState {
  index: number;
  name: string;
  armed: boolean;
  hasDrumRack: boolean;
  meter: string;
  slots: SlotState[];
}

export interface SessionSnapshot {
  tempo: number;
  tracks: TrackState[];
}

interface ReadableClip {
  name?: string;
  notes?: unknown;
}

interface ReadableSlot {
  clip: ReadableClip | null;
}

interface ReadableTrack {
  name: string;
  arm?: boolean;
  signatureNumerator?: number;
  signatureDenominator?: number;
  devices?: { className?: string; name?: string }[];
  clipSlots?: ReadableSlot[];
}

export interface ReadableSong {
  tempo: number;
  tracks: ReadableTrack[];
}

function readSlot(slot: ReadableSlot, index: number): SlotState {
  const clip = slot.clip;
  if (!clip) {
    return { index, filled: false, name: null, noteCount: 0 };
  }
  let noteCount: number | null = null;
  try {
    const notes = clip.notes;
    if (Array.isArray(notes)) noteCount = notes.length;
  } catch {
    // An audio clip throws here. The slot is still occupied, and reporting it
    // as empty would invite an overwrite the user did not ask for.
    noteCount = null;
  }
  return { index, filled: true, name: clip.name ?? null, noteCount };
}

export function snapshotSession(song: ReadableSong): SessionSnapshot {
  return {
    tempo: song.tempo,
    tracks: song.tracks.map((track, index) => ({
      index,
      name: track.name,
      armed: track.arm === true,
      hasDrumRack: (track.devices ?? []).some(
        (device) => device.className === 'DrumRack',
      ),
      meter: `${track.signatureNumerator ?? 4}/${track.signatureDenominator ?? 4}`,
      slots: (track.clipSlots ?? []).map(readSlot),
    })),
  };
}
```

- [ ] **Step 4: Run the tests**

```bash
cd AbletonMCPServer_Extension && npx tsx --test groove-brain-gate0/tests/session-snapshot.test.ts
```

Expected: `pass 3`.

- [ ] **Step 5: Commit**

```bash
git add AbletonMCPServer_Extension/groove-brain-gate0/src/session-snapshot.ts AbletonMCPServer_Extension/groove-brain-gate0/tests/session-snapshot.test.ts
git commit -m "feat(gate3): read the Live set into something the panel can render"
```

---

### Task 2: Port the deterministic transforms

**Files:**
- Create: `AbletonMCPServer_Extension/groove-brain-gate0/src/transforms.ts`
- Create: `AbletonMCPServer_Extension/groove-brain-gate0/tests/transforms.test.ts`
- Reference: `ableton_mcp_server/groove_intelligence/deterministic.py:330-470`

The seven axes are already specified and tested in Python. This ports them so
generation runs where the clip is written, without a second process. Each keeps
its Python semantics, including the clamps, so a groove generated here and one
generated by `groove_generate` are the same idea rather than two dialects.

- [ ] **Step 1: Write the failing tests**

```typescript
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { applyTransforms, type ClipNote } from '../src/transforms.js';

const STRAIGHT: ClipNote[] = [0, 1, 2, 3].map((beat) => ({
  pitch: 36,
  startTime: beat,
  duration: 0.25,
  velocity: 100,
}));

test('no transform leaves the notes exactly as they were', () => {
  assert.deepEqual(applyTransforms(STRAIGHT, {}, 1), STRAIGHT);
});

test('positive density adds notes and negative density removes them', () => {
  assert.ok(applyTransforms(STRAIGHT, { density: 0.5 }, 1).length > STRAIGHT.length);
  assert.ok(applyTransforms(STRAIGHT, { density: -0.5 }, 1).length < STRAIGHT.length);
});

test('energy moves velocity and stays inside the MIDI range', () => {
  const loud = applyTransforms(STRAIGHT, { energy: 1 }, 1);
  const quiet = applyTransforms(STRAIGHT, { energy: -1 }, 1);
  assert.ok(loud[0].velocity > 100);
  assert.ok(quiet[0].velocity < 100);
  for (const note of [...loud, ...quiet]) {
    assert.ok(note.velocity >= 1 && note.velocity <= 127);
  }
});

test('a negative timing transform never pulls a note before zero', () => {
  for (const axis of ['swing', 'microtiming', 'syncopation', 'polyrhythm'] as const) {
    const moved = applyTransforms(STRAIGHT, { [axis]: -1 }, 1);
    for (const note of moved) assert.ok(note.startTime >= 0, `${axis} went negative`);
  }
});

test('the same seed gives the same result', () => {
  const options = { density: 0.4, polyrhythm: 0.6, energy: 0.2 };
  assert.deepEqual(
    applyTransforms(STRAIGHT, options, 7),
    applyTransforms(STRAIGHT, options, 7),
  );
});

test('different seeds give different results where a transform is random', () => {
  const options = { density: -0.5 };
  const a = applyTransforms(STRAIGHT, options, 1);
  const b = applyTransforms(STRAIGHT, options, 99);
  assert.notDeepEqual(a, b);
});

test('a transform outside the range is refused rather than clamped silently', () => {
  // The panel is a UI and a slider can be dragged past its label; a value the
  // engine never promised to honour must not be applied as if it had been.
  assert.throws(() => applyTransforms(STRAIGHT, { swing: 2 }, 1), /TRANSFORM_OUT_OF_RANGE/);
});
```

- [ ] **Step 2: Run to verify failure**

```bash
cd AbletonMCPServer_Extension && npx tsx --test groove-brain-gate0/tests/transforms.test.ts
```

Expected: `Cannot find module '../src/transforms.js'`.

- [ ] **Step 3: Port the transforms**

Read `ableton_mcp_server/groove_intelligence/deterministic.py` from `_transform_notes` to the end of the `complexity` block and port each axis in the same order, in beats rather than ticks. Use a small seeded generator so a seed reproduces; `Math.random` would break the determinism every other part of this system promises.

```typescript
/**
 * The seven deterministic transform axes, in beats.
 *
 * Ported from `groove_intelligence/deterministic.py`, which is the reference:
 * the order the axes are applied in is part of the result, so it is preserved
 * here rather than reordered for readability.
 */

export interface ClipNote {
  pitch: number;
  startTime: number;
  duration: number;
  velocity: number;
}

export type TransformAxis =
  | 'density' | 'syncopation' | 'swing' | 'microtiming'
  | 'energy' | 'complexity' | 'polyrhythm';

export type Transforms = Partial<Record<TransformAxis, number>>;

/** Above this a note reads as an accent rather than a ghost. */
const ACCENT_VELOCITY = 80;

/** Deterministic, seeded, and independent of the host's Math.random. */
function mulberry32(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function applyTransforms(
  notes: ClipNote[],
  transforms: Transforms,
  seed: number,
): ClipNote[] {
  for (const [axis, value] of Object.entries(transforms)) {
    if (typeof value !== 'number' || value < -1 || value > 1) {
      throw new Error(`TRANSFORM_OUT_OF_RANGE:${axis}`);
    }
  }
  // ... port each axis here, in the Python order: density, energy,
  // microtiming, swing, syncopation, polyrhythm, complexity.
  const random = mulberry32(seed);
  let result = notes.map((note) => ({ ...note }));
  // (implementation follows deterministic.py block by block)
  void random;
  return result;
}
```

- [ ] **Step 4: Run the tests until they pass**

```bash
cd AbletonMCPServer_Extension && npx tsx --test groove-brain-gate0/tests/transforms.test.ts
```

Expected: `pass 7`.

- [ ] **Step 5: Commit**

```bash
git add AbletonMCPServer_Extension/groove-brain-gate0/src/transforms.ts AbletonMCPServer_Extension/groove-brain-gate0/tests/transforms.test.ts
git commit -m "feat(gate3): port the deterministic transform axes to the extension"
```

---

### Task 3: Validate what the panel asks for

**Files:**
- Create: `AbletonMCPServer_Extension/groove-brain-gate0/src/command.ts`
- Create: `AbletonMCPServer_Extension/groove-brain-gate0/tests/command.test.ts`

- [ ] **Step 1: Write the failing tests**

```typescript
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { parseCommand } from '../src/command.js';

const VALID = {
  op: 'write',
  trackIndex: 0,
  slotIndex: 2,
  grooveId: 'ga1_0040074f58b0',
  transforms: { density: 0.3 },
  seed: 7,
  replace: false,
};

test('a well formed command survives parsing', () => {
  assert.deepEqual(parseCommand(JSON.stringify(VALID)), VALID);
});

test('an index that is not a whole number is refused', () => {
  // These index into the live set. A float would silently address track zero.
  for (const bad of [{ trackIndex: 1.5 }, { slotIndex: -1 }, { trackIndex: 'a' }]) {
    assert.throws(
      () => parseCommand(JSON.stringify({ ...VALID, ...bad })),
      /INVALID_COMMAND/,
    );
  }
});

test('an unknown operation is refused', () => {
  assert.throws(
    () => parseCommand(JSON.stringify({ ...VALID, op: 'delete_everything' })),
    /INVALID_COMMAND/,
  );
});

test('a transform outside the range is refused at the boundary', () => {
  // Refused here as well as in applyTransforms: this is the edge the panel
  // talks to, and the earlier something untrusted is rejected the better.
  assert.throws(
    () => parseCommand(JSON.stringify({ ...VALID, transforms: { swing: 4 } })),
    /INVALID_COMMAND/,
  );
});

test('an unknown transform axis is refused rather than ignored', () => {
  assert.throws(
    () => parseCommand(JSON.stringify({ ...VALID, transforms: { loudness: 0.5 } })),
    /INVALID_COMMAND/,
  );
});

test('replace defaults to false so a filled slot is never overwritten by omission', () => {
  const { replace, ...withoutReplace } = VALID;
  void replace;
  assert.equal(parseCommand(JSON.stringify(withoutReplace)).replace, false);
});
```

- [ ] **Step 2: Run to verify failure, then implement, then run again**

```bash
cd AbletonMCPServer_Extension && npx tsx --test groove-brain-gate0/tests/command.test.ts
```

Implement `parseCommand` to return `{op, trackIndex, slotIndex, grooveId, transforms, seed, replace}`, rejecting anything else with `INVALID_COMMAND`. Ops for this Gate: `write` and `clear`.

Expected after implementing: `pass 6`.

- [ ] **Step 3: Commit**

```bash
git add AbletonMCPServer_Extension/groove-brain-gate0/src/command.ts AbletonMCPServer_Extension/groove-brain-gate0/tests/command.test.ts
git commit -m "feat(gate3): validate panel commands before they reach the live set"
```

---

### Task 4a: Resolve a note through the loaded kit's profile

**Files:**
- Create: `AbletonMCPServer_Extension/groove-brain-gate0/src/kit-profile.ts`
- Create: `AbletonMCPServer_Extension/groove-brain-gate0/tests/kit-profile.test.ts`
- Reference: `ableton_mcp_server/groove_intelligence/profiles/toontrack-sd3-default-observed.json`

Nothing reaches Live without passing through this. A note whose articulation the
loaded kit does not have is silent, and the panel has to say so rather than write
it and leave the user wondering why the groove sounds thin.

- [ ] **Step 1: Write the failing tests**

```typescript
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { resolveNote, summariseCoverage } from '../src/kit-profile.js';

const PROFILE = {
  kit: 'Ludwig Classic Default',
  notes: {
    '36': { name: 'Kick Open', piece: 'kick', loaded: true },
    '38': { name: 'Snare Center', piece: 'snare', loaded: true },
    '68': { name: 'Snare Muted', piece: 'snare', loaded: false },
    '62': { name: 'Hi-Hat Tight Edge', piece: 'hihat', loaded: true, openness: 0, zone: 'edge' },
    '26': { name: 'Hi-Hat Open Edge 3', piece: 'hihat', loaded: true, openness: 0.76, zone: 'edge' },
    '122': { name: 'Hi-Hat Open Bell 2', piece: 'hihat', loaded: false, openness: 0.64, zone: 'bell' },
    '99': { name: 'Cymbal 3 Bow Shank', piece: 'cymbal', loaded: null },
  },
};

test('a loaded note passes through unchanged', () => {
  assert.deepEqual(resolveNote(PROFILE, 36), { status: 'plays', pitch: 36 });
});

test('an unloaded hi-hat falls back to the nearest openness that plays', () => {
  // A bell hit the kit lacks is still a hi-hat at that openness. Dropping it
  // loses the pattern; moving it to the nearest playable one keeps the part.
  const out = resolveNote(PROFILE, 122);
  assert.equal(out.status, 'substituted');
  assert.equal(out.pitch, 26);
});

test('an unloaded note with no playable relative is silent and says so', () => {
  const out = resolveNote(PROFILE, 68);
  assert.equal(out.status, 'silent');
  assert.equal(out.pitch, null);
});

test('a note the profile never observed is reported, not guessed', () => {
  // Null means nobody looked. Calling it playable writes a note that may be
  // silent; calling it silent drops one that may be fine.
  assert.equal(resolveNote(PROFILE, 99).status, 'unknown');
});

test('a note absent from the profile is unknown, not silent', () => {
  assert.equal(resolveNote(PROFILE, 7).status, 'unknown');
});

test('coverage counts what the user will actually hear', () => {
  const summary = summariseCoverage(PROFILE, [36, 36, 38, 68, 122, 99]);
  assert.equal(summary.plays, 3);
  assert.equal(summary.substituted, 1);
  assert.equal(summary.silent, 1);
  assert.equal(summary.unknown, 1);
});
```

- [ ] **Step 2: Run to verify failure**

```bash
cd AbletonMCPServer_Extension && npx tsx --test groove-brain-gate0/tests/kit-profile.test.ts
```

Expected: `Cannot find module '../src/kit-profile.js'`.

- [ ] **Step 3: Implement**

```typescript
/**
 * What the loaded kit will actually play.
 *
 * SD3 marks an articulation "(not loaded)" when the mapping exists but the kit
 * has no sample behind it. Such a note is not a wrong drum, it is no drum, and
 * a measurement made against a note map alone cannot see it. Everything written
 * to Live passes through here first.
 */

export interface ProfileNote {
  name: string;
  piece: string;
  /** True plays, false is mapped but silent, null was never observed. */
  loaded: boolean | null;
  openness?: number;
  zone?: string;
}

export interface KitProfile {
  kit: string;
  notes: Record<string, ProfileNote>;
}

export type Resolution =
  | { status: 'plays'; pitch: number }
  | { status: 'substituted'; pitch: number }
  | { status: 'silent'; pitch: null }
  | { status: 'unknown'; pitch: number };

export function resolveNote(profile: KitProfile, pitch: number): Resolution {
  const entry = profile.notes[String(pitch)];
  if (!entry || entry.loaded === null) return { status: 'unknown', pitch };
  if (entry.loaded) return { status: 'plays', pitch };

  // Nearest playable relative: same piece, and for a hi-hat the closest
  // openness, because openness is what the part is made of while the strike
  // zone is a colour on top of it.
  let best: { pitch: number; distance: number } | null = null;
  for (const [key, candidate] of Object.entries(profile.notes)) {
    if (candidate.loaded !== true || candidate.piece !== entry.piece) continue;
    const distance = entry.openness !== undefined && candidate.openness !== undefined
      ? Math.abs(entry.openness - candidate.openness)
      : Number.POSITIVE_INFINITY;
    if (best === null || distance < best.distance) best = { pitch: Number(key), distance };
  }
  if (best === null || !Number.isFinite(best.distance)) return { status: 'silent', pitch: null };
  return { status: 'substituted', pitch: best.pitch };
}

export interface Coverage {
  plays: number;
  substituted: number;
  silent: number;
  unknown: number;
}

export function summariseCoverage(profile: KitProfile, pitches: number[]): Coverage {
  const summary: Coverage = { plays: 0, substituted: 0, silent: 0, unknown: 0 };
  for (const pitch of pitches) summary[resolveNote(profile, pitch).status] += 1;
  return summary;
}
```

- [ ] **Step 4: Run the tests**

```bash
cd AbletonMCPServer_Extension && npx tsx --test groove-brain-gate0/tests/kit-profile.test.ts
```

Expected: `pass 6`.

- [ ] **Step 5: Commit**

```bash
git add AbletonMCPServer_Extension/groove-brain-gate0/src/kit-profile.ts AbletonMCPServer_Extension/groove-brain-gate0/tests/kit-profile.test.ts
git commit -m "feat(gate3): resolve every note through the loaded kit's profile"
```

---


### Task 4: Write into the track and slot the panel named

**Files:**
- Create: `AbletonMCPServer_Extension/groove-brain-gate0/src/session-writer.ts`
- Create: `AbletonMCPServer_Extension/groove-brain-gate0/tests/session-writer.test.ts`
- Modify: `AbletonMCPServer_Extension/groove-brain-gate0/src/session-clip-probe.ts`

- [ ] **Step 1: Write the failing tests**

```typescript
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { applyCommand } from '../src/session-writer.js';

function fakeSong(filled = false) {
  const created: { length: number; notes: unknown[]; name: string }[] = [];
  const clip = filled ? { name: 'Verse', notes: [{ pitch: 38 }] } : null;
  return {
    created,
    song: {
      tempo: 120,
      tracks: [
        {
          name: 'Drums',
          clipSlots: [
            {
              clip,
              async createMidiClip(length: number) {
                const made = { length, notes: [] as unknown[], name: '' };
                created.push(made);
                return made;
              },
              async deleteClip() {
                this.clip = null;
              },
            },
          ],
        },
      ],
    },
  };
}

const NOTES = [{ pitch: 36, startTime: 0, duration: 0.25, velocity: 100 }];

test('writing into an empty slot creates a clip and fills it', async () => {
  const { song, created } = fakeSong();
  const receipt = await applyCommand(song, {
    op: 'write', trackIndex: 0, slotIndex: 0,
    grooveId: 'g1', transforms: {}, seed: 1, replace: false,
  }, NOTES, 4);

  assert.equal(receipt.status, 'ok');
  assert.equal(created.length, 1);
  assert.equal(created[0].length, 4);
  assert.deepEqual(created[0].notes, NOTES);
});

test('a filled slot is refused unless replace was asked for', async () => {
  // Overwriting someone's take because a tap landed on the wrong row is the
  // one mistake this must not make silently.
  const { song, created } = fakeSong(true);
  const receipt = await applyCommand(song, {
    op: 'write', trackIndex: 0, slotIndex: 0,
    grooveId: 'g1', transforms: {}, seed: 1, replace: false,
  }, NOTES, 4);

  assert.equal(receipt.status, 'refused');
  assert.equal(receipt.code, 'SLOT_NOT_EMPTY');
  assert.equal(created.length, 0);
});

test('replace deletes the clip that was there and writes the new one', async () => {
  const { song, created } = fakeSong(true);
  const receipt = await applyCommand(song, {
    op: 'write', trackIndex: 0, slotIndex: 0,
    grooveId: 'g1', transforms: {}, seed: 1, replace: true,
  }, NOTES, 4);

  assert.equal(receipt.status, 'ok');
  assert.equal(created.length, 1);
});

test('an index outside the set is refused rather than throwing', async () => {
  const { song } = fakeSong();
  for (const bad of [{ trackIndex: 9 }, { slotIndex: 9 }]) {
    const receipt = await applyCommand(song, {
      op: 'write', trackIndex: 0, slotIndex: 0,
      grooveId: 'g1', transforms: {}, seed: 1, replace: false, ...bad,
    }, NOTES, 4);
    assert.equal(receipt.status, 'refused');
    assert.equal(receipt.code, 'INDEX_OUT_OF_RANGE');
  }
});

test('clear empties a slot and says so when it was already empty', async () => {
  const filledSet = fakeSong(true);
  const cleared = await applyCommand(filledSet.song, {
    op: 'clear', trackIndex: 0, slotIndex: 0,
    grooveId: null, transforms: {}, seed: 1, replace: true,
  }, [], 0);
  assert.equal(cleared.status, 'ok');

  const emptySet = fakeSong();
  const again = await applyCommand(emptySet.song, {
    op: 'clear', trackIndex: 0, slotIndex: 0,
    grooveId: null, transforms: {}, seed: 1, replace: true,
  }, [], 0);
  assert.equal(again.status, 'refused');
  assert.equal(again.code, 'SLOT_ALREADY_EMPTY');
});
```

- [ ] **Step 2: Run to verify failure, implement, run again**

`applyCommand` returns `{status: 'ok' | 'refused', code: string, trackName, slotIndex, noteCount}` and never throws for a bad index: the panel is a remote surface and a stack trace there is useless.

Expected after implementing: `pass 5`.

- [ ] **Step 3: Commit**

```bash
git add AbletonMCPServer_Extension/groove-brain-gate0/src/session-writer.ts AbletonMCPServer_Extension/groove-brain-gate0/tests/session-writer.test.ts
git commit -m "feat(gate3): write into the track and slot the panel named"
```

---

### Task 5: Turn the helper's selection slot into a relay

**Files:**
- Modify: `AbletonMCPServer_Extension/groove-brain-gate0/helper/src/server.rs`

`Selection` becomes `Relay`: it holds the last snapshot the extension pushed and
the last command the panel posted. Two new routes, and `/api/select` and
`/api/selection` go away with the browsing panel they served.

- [ ] **Step 1: Write the failing tests**

```rust
    #[test]
    fn a_snapshot_is_read_many_times_and_a_command_is_taken_once() {
        // The panel re-renders whenever it likes, so the snapshot has to stay.
        // A command is work to be done, so taking it twice would do it twice.
        let relay = Relay::default();
        assert_eq!(relay.snapshot(), None);
        relay.publish(r#"{"tempo":120}"#.to_owned());
        assert_eq!(relay.snapshot().as_deref(), Some(r#"{"tempo":120}"#));
        assert_eq!(relay.snapshot().as_deref(), Some(r#"{"tempo":120}"#));

        relay.enqueue(r#"{"op":"write"}"#.to_owned());
        assert_eq!(relay.take_command().as_deref(), Some(r#"{"op":"write"}"#));
        assert_eq!(relay.take_command(), None);
    }

    #[test]
    fn a_newer_snapshot_replaces_the_older_one() {
        let relay = Relay::default();
        relay.publish("a".to_owned());
        relay.publish("b".to_owned());
        assert_eq!(relay.snapshot().as_deref(), Some("b"));
    }
```

- [ ] **Step 2: Implement, wire the routes, run**

Routes after this task: `/api/health`, `/api/panel`, `/api/search`, `/api/groove`, `/api/snapshot` (POST publishes, GET-shaped POST reads), `/api/command` (panel posts, extension takes).

```bash
cd AbletonMCPServer_Extension/groove-brain-gate0/helper && cargo test
```

Expected: every existing test still green, plus the two above.

- [ ] **Step 3: Commit**

```bash
git add AbletonMCPServer_Extension/groove-brain-gate0/helper/src/server.rs
git commit -m "feat(gate3): relay a session snapshot and a command queue"
```

---

### Task 6: The panel

**Files:**
- Modify: `AbletonMCPServer_Extension/groove-brain-gate0/ui/picker.html`, `picker.js`, `styles.css`
- Modify: `AbletonMCPServer_Extension/groove-brain-gate0/tests/ui-events.test.ts`

What it shows, top to bottom:

1. **Session** — tempo, and every track as a row: name, armed, whether it has a drum rack. Tapping a track selects it.
2. **Slots** — for the selected track, the slots as a strip: empty ones plain, filled ones showing the clip name and note count. Tapping selects the target.
3. **Source** — genre and BPM, and the count of matching grooves. One "surprise me" button that takes a random match, because naming a genre and getting one groove is the common case.
4. **Knobs** — density, energy, swing, complexity, polyrhythm as sliders from −1 to 1, all starting at 0.
5. **Write** — disabled until a track and slot are chosen. Says "Substituir" and turns red when the chosen slot is filled.

The result of a write appears as a line under the button: which track, which slot, how many notes.

- [ ] **Step 1: Rewrite the tests first, then the page**

The existing harness in `ui-events.test.ts` already runs a page in a VM with a fake DOM; extend its fetch mock with `/api/snapshot` and `/api/command` and keep the structure.

Cases to cover: the track list renders from the snapshot; selecting a track shows its slots; write is disabled until both are chosen; the button says replace for a filled slot; the posted command carries the chosen indices and the slider values.

- [ ] **Step 2: Commit**

```bash
git add AbletonMCPServer_Extension/groove-brain-gate0/ui AbletonMCPServer_Extension/groove-brain-gate0/tests/ui-events.test.ts
git commit -m "feat(gate3): a panel that shows the session and writes to it"
```

---

### Task 7: Join it up in the extension

**Files:**
- Modify: `AbletonMCPServer_Extension/groove-brain-gate0/src/extension.ts`
- Modify: `AbletonMCPServer_Extension/groove-brain-gate0/src/actions.ts`
- Modify: `AbletonMCPServer_Extension/groove-brain-gate0/src/helper-process.ts`

- [ ] **Step 1: Publish, poll, apply, republish**

After the handoff, the extension loops: publish a snapshot, poll for a command, apply it, publish again. Three things this must get right, each of which Gate 2 got wrong:

- **A failed poll is not fatal.** Gate 2 let one failure fall through to the `finally` that stopped the helper, which is exactly the connection-refused the owner saw. Count consecutive failures and give up only after several.
- **The context menu opens on more than a clip slot.** Register on `MidiTrack` too, since the panel no longer needs a slot to start.
- **A stale page says so.** Include the helper's start time in `/api/health`; when the panel sees it change, it tells the user to scan again rather than failing on a refused connection.

- [ ] **Step 2: Full verification**

```bash
cd AbletonMCPServer_Extension && npm run gate0:typecheck && npm run gate0:test
cd groove-brain-gate0/helper && cargo test
```

- [ ] **Step 3: Commit and package**

```bash
git add AbletonMCPServer_Extension/groove-brain-gate0/src
git commit -m "feat(gate3): drive the session panel from the extension"
```

---

### Task 8: Make the modal's URL clickable and the page honest

**Files:**
- Modify: `AbletonMCPServer_Extension/groove-brain-gate0/ui/index.html`, `app.js`

- [ ] **Step 1:** The URL becomes an `<a>` so it opens with a click when the panel is on the same machine. Reported directly by the owner.
- [ ] **Step 2:** The handoff page keeps showing the QR after the button is pressed for the seconds it takes to scan, rather than closing instantly.
- [ ] **Step 3: Commit**

---

## Stop condition

Gate 3 is done when, from a phone, you can see the tracks in your set, see what
is already in their slots, pick a track and an empty slot, turn density and
swing, and hear the result in Live without the modal ever blocking you.

It is **not** done if the panel can still overwrite a filled slot without being
asked, or if a single failed request kills the session the way Gate 2's did.
