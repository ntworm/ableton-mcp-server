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
  // 6/8 at two bars is six eighth-notes twice: six beats, not eight.
  assert.equal(clipLengthBeats({ ...GROOVE, bars: 2, meter: '6/8' }), 6);
});

test('an unreadable meter falls back to four four rather than throwing', () => {
  assert.equal(clipLengthBeats({ ...GROOVE, meter: 'nonsense' }), 8);
});

test('a groove whose notes run past its stated bars is not truncated', () => {
  // The bar count is metadata; the notes are the groove. A clip shorter than
  // the last note silently drops it.
  const long = {
    ...GROOVE,
    bars: 1,
    notes: [
      [36, 0, 120, 100],
      [38, 3840, 120, 100],
    ] as [number, number, number, number][],
  };
  assert.ok(clipLengthBeats(long) >= 9);
});
