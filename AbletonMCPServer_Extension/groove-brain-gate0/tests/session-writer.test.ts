import assert from 'node:assert/strict';
import { test } from 'node:test';
import { applyCommand, type WritableSong } from '../src/session-writer.js';
import type { KitProfile } from '../src/kit-profile.js';
import type { Command } from '../src/command.js';

const PROFILE: KitProfile = {
  kit: 'Test Kit',
  notes: {
    '36': { name: 'Kick', piece: 'kick', loaded: true },
    '38': { name: 'Snare', piece: 'snare', loaded: true },
    '68': { name: 'Snare Muted', piece: 'snare', loaded: false },
  },
};

const NOTES = [{ pitch: 36, startTime: 0, duration: 0.25, velocity: 100 }];

function fakeSong(filled = false) {
  const created: { length: number; notes: unknown[]; name: string }[] = [];
  const slot = {
    clip: filled ? { name: 'Verse', notes: [{ pitch: 38 }] } : null,
    async createMidiClip(length: number) {
      const made = { length, notes: [] as unknown[], name: '' };
      created.push(made);
      return made;
    },
    async deleteClip() {
      slot.clip = null;
    },
  };
  return {
    created,
    song: { tempo: 120, tracks: [{ name: 'Drums', clipSlots: [slot] }] } as unknown as WritableSong,
  };
}

function command(over: Partial<Command> = {}): Command {
  return {
    op: 'write', trackIndex: 0, slotIndex: 0, grooveId: 'g1',
    transforms: {}, seed: 1, replace: false, ...over,
  };
}

test('writing into an empty slot creates a clip and fills it', async () => {
  const { song, created } = fakeSong();
  const receipt = await applyCommand(song, command(), NOTES, 4, PROFILE);

  assert.equal(receipt.status, 'ok');
  assert.equal(created.length, 1);
  assert.equal(created[0].length, 4);
  assert.equal((created[0].notes as unknown[]).length, 1);
  assert.equal(receipt.trackName, 'Drums');
});

test('a filled slot is refused unless replace was asked for', async () => {
  // Overwriting someone's take because a tap landed on the wrong row is the
  // one mistake this must not make silently.
  const { song, created } = fakeSong(true);
  const receipt = await applyCommand(song, command(), NOTES, 4, PROFILE);

  assert.equal(receipt.status, 'refused');
  assert.equal(receipt.code, 'SLOT_NOT_EMPTY');
  assert.equal(created.length, 0);
});

test('replace deletes the clip that was there and writes the new one', async () => {
  const { song, created } = fakeSong(true);
  const receipt = await applyCommand(song, command({ replace: true }), NOTES, 4, PROFILE);
  assert.equal(receipt.status, 'ok');
  assert.equal(created.length, 1);
  // Read before the delete clears it, or every replace reports as a create.
  assert.equal(receipt.code, 'REPLACED');
});

test('an index outside the set is refused rather than throwing', async () => {
  const { song } = fakeSong();
  for (const bad of [{ trackIndex: 9 }, { slotIndex: 9 }]) {
    const receipt = await applyCommand(song, command(bad), NOTES, 4, PROFILE);
    assert.equal(receipt.status, 'refused');
    assert.equal(receipt.code, 'INDEX_OUT_OF_RANGE');
  }
});

test('clear empties a slot and says so when it was already empty', async () => {
  const filled = fakeSong(true);
  const cleared = await applyCommand(
    filled.song, command({ op: 'clear', grooveId: null, replace: true }), [], 0, PROFILE);
  assert.equal(cleared.status, 'ok');

  const empty = fakeSong();
  const again = await applyCommand(
    empty.song, command({ op: 'clear', grooveId: null, replace: true }), [], 0, PROFILE);
  assert.equal(again.status, 'refused');
  assert.equal(again.code, 'SLOT_ALREADY_EMPTY');
});

test('the receipt says what the kit could not play', async () => {
  // The panel shows this. A groove that lost a third of its notes to a kit
  // without those articulations must not look like a clean insert.
  const { song, created } = fakeSong();
  const mixed = [
    { pitch: 36, startTime: 0, duration: 0.25, velocity: 100 },
    { pitch: 68, startTime: 1, duration: 0.25, velocity: 100 },
  ];
  const receipt = await applyCommand(song, command(), mixed, 4, PROFILE);

  assert.equal(receipt.status, 'ok');
  assert.equal(receipt.coverage?.plays, 1);
  assert.equal(receipt.coverage?.silent, 1);
  // The silent note is not written: an unplayable note in the clip is a note
  // the user will move around wondering why it makes no sound.
  assert.equal((created[0].notes as unknown[]).length, 1);
});

test('a groove with nothing the kit can play is refused, not written empty', async () => {
  const { song, created } = fakeSong();
  const silent = [{ pitch: 68, startTime: 0, duration: 0.25, velocity: 100 }];
  const receipt = await applyCommand(song, command(), silent, 4, PROFILE);

  assert.equal(receipt.status, 'refused');
  assert.equal(receipt.code, 'NOTHING_AUDIBLE');
  assert.equal(created.length, 0);
});
