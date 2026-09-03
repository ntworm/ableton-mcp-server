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
      JSON.stringify(bad),
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

test('clear needs no groove but write does', () => {
  const cleared = parseCommand(
    JSON.stringify({ op: 'clear', trackIndex: 0, slotIndex: 1, replace: true }),
  );
  assert.equal(cleared.grooveId, null);
  assert.throws(
    () => parseCommand(JSON.stringify({ ...VALID, grooveId: null })),
    /INVALID_COMMAND/,
  );
});

test('malformed input is refused rather than half-read', () => {
  for (const bad of ['not json', '[]', 'null', '"a string"', '{}']) {
    assert.throws(() => parseCommand(bad), /INVALID_COMMAND/, bad);
  }
});

test('a seed that is not a whole number is refused', () => {
  // The seed is what makes a result reproducible; a float would replay as a
  // different clip on a host that rounds differently.
  assert.throws(() => parseCommand(JSON.stringify({ ...VALID, seed: 1.5 })), /INVALID_COMMAND/);
});
