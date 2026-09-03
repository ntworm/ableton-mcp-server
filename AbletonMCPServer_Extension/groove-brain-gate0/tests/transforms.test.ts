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
  assert.deepEqual(applyTransforms(STRAIGHT, {}, 5), STRAIGHT);
});

test('positive density adds notes and negative density removes them', () => {
  assert.ok(applyTransforms(STRAIGHT, { density: 0.5 }, 5).length > STRAIGHT.length);
  assert.ok(applyTransforms(STRAIGHT, { density: -0.5 }, 5).length < STRAIGHT.length);
});

test('energy moves velocity and stays inside the MIDI range', () => {
  const loud = applyTransforms(STRAIGHT, { energy: 1 }, 5);
  const quiet = applyTransforms(STRAIGHT, { energy: -1 }, 5);
  assert.ok(loud[0].velocity > 100);
  assert.ok(quiet[0].velocity < 100);
  for (const note of [...loud, ...quiet]) {
    assert.ok(note.velocity >= 1 && note.velocity <= 127, `velocity ${note.velocity}`);
  }
});

test('a negative timing transform never pulls a note before zero', () => {
  for (const axis of ['swing', 'microtiming', 'syncopation', 'polyrhythm'] as const) {
    const moved = applyTransforms(STRAIGHT, { [axis]: -1 }, 5);
    for (const note of moved) assert.ok(note.startTime >= 0, `${axis} went negative`);
  }
});

test('every axis on its own changes something', () => {
  // A knob that does nothing is worse than a missing knob: the user turns it
  // and concludes the tool is broken.
  for (const axis of [
    'density', 'syncopation', 'swing', 'microtiming', 'energy', 'complexity', 'polyrhythm',
  ] as const) {
    const moved = applyTransforms(STRAIGHT, { [axis]: 0.8 }, 5);
    assert.notDeepEqual(moved, STRAIGHT, `${axis} did nothing`);
  }
});

test('the same seed gives the same result', () => {
  const options = { density: 0.4, polyrhythm: 0.6, energy: 0.2 };
  assert.deepEqual(applyTransforms(STRAIGHT, options, 7), applyTransforms(STRAIGHT, options, 7));
});

test('different seeds differ where a transform draws on chance', () => {
  const options = { density: -0.5 };
  assert.notDeepEqual(
    applyTransforms(STRAIGHT, options, 1),
    applyTransforms(STRAIGHT, options, 99),
  );
});

test('a transform outside the range is refused rather than clamped silently', () => {
  // The panel is a UI and a slider can be dragged past its label; a value the
  // engine never promised to honour must not be applied as if it had been.
  assert.throws(() => applyTransforms(STRAIGHT, { swing: 2 }, 5), /TRANSFORM_OUT_OF_RANGE/);
  assert.throws(() => applyTransforms(STRAIGHT, { density: -3 }, 5), /TRANSFORM_OUT_OF_RANGE/);
});

test('an unknown axis is refused rather than ignored', () => {
  assert.throws(
    () => applyTransforms(STRAIGHT, { loudness: 0.5 } as never, 5),
    /UNKNOWN_TRANSFORM_AXIS/,
  );
});

test('the input notes are never mutated', () => {
  const before = JSON.stringify(STRAIGHT);
  applyTransforms(STRAIGHT, { density: 0.9, energy: 1, swing: 1 }, 5);
  assert.equal(JSON.stringify(STRAIGHT), before);
});

test('an empty groove survives every axis', () => {
  for (const axis of ['density', 'swing', 'energy', 'complexity'] as const) {
    assert.deepEqual(applyTransforms([], { [axis]: 1 }, 5), []);
  }
});
