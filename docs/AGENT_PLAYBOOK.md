# Agent Playbook

How to compose in someone else's Live Set without breaking it, and without
guessing. Every rule here came from a real failure, and the failure is named so
the rule can be argued with.

## 1. Understand before writing

Run these three reads on any track you are about to touch. They cost nothing and
each one has already saved a wasted round trip:

| Read | Answers |
|---|---|
| `describe_instrument(track)` | what the instrument is, which parameters are automatable, and what the user must still configure |
| `get_midi_chain_report(track)` | which MIDI effects rewrite what you write |
| `get_device_chains(track, device)` | what a rack hides: chains, their volumes, the devices inside |

**Why it matters.** A `Note Length` device makes every written duration
irrelevant — articulation lives in its `Time Length`, and its `Gate` does
nothing while `Sync On` is off. A `Velocity` device with `Out Low 1 / Out Hi
105` is the real dynamic range of that track, whatever velocities the clip
holds. Neither is visible in the notes.

## 2. Ask the user for what only they can do

Some gaps are not bugs and cannot be fixed from code:

- A plugin exposing no automatable parameter needs **Configure** pressed in Live.
- A rack macro must be **mapped and renamed** before it can be addressed; a
  unique name is what makes `create_clip_automation` unambiguous.
- Moving material to the Arrangement is scriptable, but **saving is not**
  automatic — unsaved work dies when Live reopens the file.

`describe_instrument` returns these as `setup_requests`. Relay the sentence,
name the track, and wait: an agent that writes into an unconfigured plugin
produces silence and calls it success.

## 3. Address parameters exactly

Every rack carries a `Macro 1`. A bare name resolves to the first device that
has it, which is how an envelope lands on the wrong device and nothing sounds
wrong until the user looks. Pass `device_index` whenever a track has more than
one rack, and treat `AMBIGUOUS_MATCH` as the server doing its job.

## 3b. Reach inside racks

The controls that decide how a track sounds are usually nested. Pass
`chain_index` (and `chain_device_index` for a device inside the chain) to
`get_parameter_value`, `set_parameter_value` and the automation tools.
`chain_index` on its own addresses the chain mixer, which exposes `volume` and
`panning` — that is the lever for blending several articulations of one
instrument.

Find the addresses first with `get_device_chains`, then write. A real example:
a drum track whose dynamics looked dead turned out to carry a `Velocity` device
at `track:4/device:1/chain:0/device:0` with `Out Low 116, Out Hi 127` — every
written velocity, from 7 to 127, arrived as almost the same value.

## 4. Write in the Session, then place on the timeline

The note tools address Session clip slots only. The path onto the timeline is:

1. `create_clip` in a free Session slot, then `add_notes_to_clip` or
   `add_notes_pattern`.
2. Envelopes with `create_clip_automation_curve` — **before** placing, because
   clip envelopes travel with the copy and editing the source afterwards does
   not update a copy already on the timeline.
3. `duplicate_session_clip_to_arrangement(track, slot, beat)`.
4. `get_arrangement_clips(track)` to verify placement.

Keep the Session clip: it is the reusable source for every later placement.

## 5. Envelopes are stepped, and that is not a bug

Live's clip envelopes accept steps, never interpolated ramps. Two consequences:

- A step must reach the next breakpoint. Zero-length steps produce a comb of
  spikes that sounds like clicks; this was a real defect, fixed in v0.5.5.
- A smooth curve is a dense staircase. Do not hand-roll it: send a handful of
  control points to `create_clip_automation_curve` and let the server expand
  them, and put the resolution where the curve actually moves.

Read back with `get_clip_automation` instead of trusting the write.

## 6. Indexes are positions, not identities

`clip_index` on the Arrangement is a position in `Track.arrangement_clips`. It
shifts after every insertion, move or deletion. Path-ids such as
`track:2/device:1` are session locators, not persistent handles. Re-read after
any structural change; never cache an index across a mutation.

## 7. State that dies quietly

- Live loads a Remote Script **once per launch**. Toggling the Control Surface
  re-instantiates it but does not re-import the module: new server code needs a
  full Live restart.
- Anything created since the last save is lost when Live reopens the Set. Ask
  for `Ctrl+S` before any restart, and prefer working in a `_TESTES` copy.
- A muted Arrangement clip looks like material and produces silence. Check
  `muted` in `get_arrangement_clips` before concluding a part does not exist.

## 8. Measure the composer, do not guess

Before writing in someone's style, measure it: velocity range and distinct
values per track, the grid the part is actually played against (straight or
triplet), and whether the timing is quantized or human. A part that reads as
"flat" is often a `Velocity` device, not a lack of dynamics — and a part that
reads as "sloppy" is often a triplet grid measured against sixteenths.

Bound every measurement to the arranged section. Sets keep discarded takes far
past the end of the song, and those takes are hand-played where the arrangement
is quantized; unbounded, they invert the conclusion.
