import assert from 'node:assert/strict';
import { test } from 'node:test';
import { resolveNote, summariseCoverage, type KitProfile } from '../src/kit-profile.js';

const PROFILE: KitProfile = {
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
