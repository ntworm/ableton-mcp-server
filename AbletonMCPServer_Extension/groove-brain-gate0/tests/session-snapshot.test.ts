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
  } as unknown as (typeof song.tracks)[0]['clipSlots'][0];
  const slot = snapshotSession(song).tracks[0].slots[1];
  assert.equal(slot.filled, true);
  assert.equal(slot.noteCount, null);
});

test('a track with no slots is a track with no slots, not a crash', () => {
  const snapshot = snapshotSession({ tempo: 120, tracks: [{ name: 'Empty' }] });
  assert.deepEqual(snapshot.tracks[0].slots, []);
  assert.equal(snapshot.tracks[0].meter, '4/4');
});
