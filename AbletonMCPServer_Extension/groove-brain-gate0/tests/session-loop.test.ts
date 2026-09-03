import assert from 'node:assert/strict';
import { test } from 'node:test';
import { serveSession, MAX_CONSECUTIVE_FAILURES } from '../src/session-loop.js';
import type { KitProfile } from '../src/kit-profile.js';

const PROFILE: KitProfile = {
  kit: 'Test',
  notes: { '36': { name: 'Kick', piece: 'kick', loaded: true } },
};

const GROOVE = JSON.stringify({
  id: 'g1', bars: 1, meter: '4/4', ppq: 480, notes: [[36, 0, 120, 100]],
});

function clock() {
  let now = 0;
  return { nowMs: () => now, sleep: async (ms: number) => { now += ms; } };
}

function fakeSong() {
  const created: { length: number; notes: unknown[]; name: string }[] = [];
  const slot = {
    clip: null as { name?: string } | null,
    async createMidiClip(length: number) {
      const made = { length, notes: [] as unknown[], name: '' };
      created.push(made);
      slot.clip = made;
      return made;
    },
    async deleteClip() { slot.clip = null; },
  };
  return { created, song: { tempo: 120, tracks: [{ name: 'Drums', clipSlots: [slot] }] } };
}

const WRITE = JSON.stringify({
  op: 'write', trackIndex: 0, slotIndex: 0, grooveId: 'g1', transforms: {}, seed: 1,
});

test('a queued write reaches the clip and the receipt says so', async () => {
  const { song, created } = fakeSong();
  const commands = [WRITE];
  const published: unknown[] = [];
  const receipts: unknown[] = [];
  let active = true;

  await serveSession({
    helper: {
      async publishSnapshot(s) { published.push(s); },
      async takeCommand() {
        const next = commands.shift() ?? null;
        if (next === null) active = false;
        return next;
      },
      async fetchGroove() { return GROOVE; },
    },
    song: song as never,
    profile: PROFILE,
    stillActive: () => active,
    onReceipt: (r) => receipts.push(r),
    ...clock(),
  });

  assert.equal(created.length, 1);
  assert.ok(published.length >= 1);
  assert.equal((receipts[0] as { status: string }).status, 'ok');
});

test('the snapshot is republished only when it changed', async () => {
  // The panel polls on its own clock; an identical snapshot is noise.
  const { song } = fakeSong();
  const published: unknown[] = [];
  let turns = 0;

  await serveSession({
    helper: {
      async publishSnapshot(s) { published.push(s); },
      async takeCommand() { turns += 1; return null; },
      async fetchGroove() { return GROOVE; },
    },
    song: song as never,
    profile: PROFILE,
    stillActive: () => turns < 4,
    ...clock(),
  });

  assert.ok(turns >= 4);
  assert.equal(published.length, 1);
});

test('one failed request does not end the session', async () => {
  // Gate 2 let a single failure stop the helper, and the page died with a
  // refused connection while the user was still holding it.
  const { song, created } = fakeSong();
  const script: (string | null | 'boom')[] = ['boom', WRITE];
  let active = true;

  await serveSession({
    helper: {
      async publishSnapshot() {},
      async takeCommand() {
        const next = script.shift();
        if (next === undefined) { active = false; return null; }
        if (next === 'boom') throw new Error('TRANSIENT');
        return next;
      },
      async fetchGroove() { return GROOVE; },
    },
    song: song as never,
    profile: PROFILE,
    stillActive: () => active,
    ...clock(),
  });

  assert.equal(created.length, 1);
});

test('a run of failures does end it', async () => {
  const { song } = fakeSong();
  let attempts = 0;

  await serveSession({
    helper: {
      async publishSnapshot() {},
      async takeCommand() { attempts += 1; throw new Error('DEAD'); },
      async fetchGroove() { return GROOVE; },
    },
    song: song as never,
    profile: PROFILE,
    stillActive: () => true,
    ...clock(),
  });

  assert.equal(attempts, MAX_CONSECUTIVE_FAILURES);
});

test('a malformed command is survived, not fatal', async () => {
  const { song, created } = fakeSong();
  const script = ['{"op":"nonsense"}', WRITE];
  let active = true;

  await serveSession({
    helper: {
      async publishSnapshot() {},
      async takeCommand() {
        const next = script.shift();
        if (next === undefined) { active = false; return null; }
        return next;
      },
      async fetchGroove() { return GROOVE; },
    },
    song: song as never,
    profile: PROFILE,
    stillActive: () => active,
    ...clock(),
  });

  assert.equal(created.length, 1);
});

test('deactivating stops the loop without another request', async () => {
  const { song } = fakeSong();
  let calls = 0;
  await serveSession({
    helper: {
      async publishSnapshot() {},
      async takeCommand() { calls += 1; return null; },
      async fetchGroove() { return GROOVE; },
    },
    song: song as never,
    profile: PROFILE,
    stillActive: () => false,
    ...clock(),
  });
  assert.equal(calls, 0);
});
