import assert from 'node:assert/strict';
import test from 'node:test';
import { runSessionClipProbe, type ClipPort, type SlotPort } from '../src/session-clip-probe.js';

function fakeSlot(initial: ClipPort | null = null): {
  slot: SlotPort;
  clips: ClipPort[];
  createLengths: number[];
} {
  const clips: ClipPort[] = initial ? [initial] : [];
  const createLengths: number[] = [];
  return {
    clips,
    createLengths,
    slot: {
      handleId: 'slot-7',
      getClip: () => clips.at(-1) ?? null,
      createMidiClip: async (lengthBeats) => {
        createLengths.push(lengthBeats);
        const clip: ClipPort = { handleId: 'clip-9', name: '', notes: [] };
        clips.push(clip);
        return clip;
      },
    },
  };
}

const clocks = {
  nowEpochMs: () => 1000,
  nowMonotonicMs: () => 5,
};

test('occupied slot is blocked before mutation', async () => {
  const existing: ClipPort = { handleId: 'old', name: 'Keep', notes: [] };
  const { slot, clips, createLengths } = fakeSlot(existing);

  const receipt = await runSessionClipProbe(slot, clocks);

  assert.equal(receipt.status, 'blocked');
  assert.equal(receipt.code, 'SLOT_OCCUPIED');
  assert.equal(receipt.clipHandle, null);
  assert.equal(clips.length, 1);
  assert.deepEqual(createLengths, []);
  assert.equal(existing.name, 'Keep');
});

test('successful write creates four beats and is read back exactly', async () => {
  const { slot, clips, createLengths } = fakeSlot();

  const receipt = await runSessionClipProbe(slot, clocks);

  assert.equal(receipt.status, 'ok');
  assert.equal(receipt.code, 'READBACK_MATCH');
  assert.equal(receipt.intendedCount, 4);
  assert.equal(receipt.readbackCount, 4);
  assert.equal(receipt.intendedHash, receipt.readbackHash);
  assert.deepEqual(createLengths, [4]);
  assert.equal(clips[0]?.name, 'Groove Brain Gate 0 Probe');
  assert.deepEqual(clips[0]?.notes.map((note) => note.startTime), [0, 1, 2, 3]);
  assert.ok(clips[0]?.notes.every((note) => note.pitch === 36));
});

test('failure before create reports failed without retry or rollback claim', async () => {
  let calls = 0;
  const slot: SlotPort = {
    handleId: 'slot-7',
    getClip: () => null,
    createMidiClip: async () => {
      calls += 1;
      throw new Error('CREATE_FAILED');
    },
  };

  const receipt = await runSessionClipProbe(slot, clocks);

  assert.equal(receipt.status, 'failed');
  assert.equal(receipt.code, 'CREATE_FAILED');
  assert.equal(receipt.clipHandle, null);
  assert.equal(receipt.retryAttempted, false);
  assert.equal(receipt.rollbackClaimed, false);
  assert.equal(calls, 1);
});

test('slot inspection failure is reported without attempting creation', async () => {
  let createCalls = 0;
  const slot: SlotPort = {
    handleId: 'slot-7',
    getClip: () => {
      throw new Error('host details must not escape');
    },
    createMidiClip: async () => {
      createCalls += 1;
      throw new Error('UNREACHABLE');
    },
  };

  const receipt = await runSessionClipProbe(slot, clocks);

  assert.equal(receipt.status, 'failed');
  assert.equal(receipt.code, 'SLOT_INSPECTION_FAILED');
  assert.equal(createCalls, 0);
});

test('readback mismatch is explicit and preserves the observed hash', async () => {
  let writtenNotes: ClipPort['notes'] = [];
  const clip: ClipPort = {
    handleId: 'clip-9',
    name: '',
    get notes() {
      return writtenNotes.slice(0, 3);
    },
    set notes(value) {
      writtenNotes = value;
    },
  };
  const slot: SlotPort = {
    handleId: 'slot-7',
    getClip: () => null,
    createMidiClip: async () => clip,
  };

  const receipt = await runSessionClipProbe(slot, clocks);

  assert.equal(receipt.status, 'failed');
  assert.equal(receipt.code, 'READBACK_MISMATCH');
  assert.equal(receipt.readbackCount, 3);
  assert.notEqual(receipt.readbackHash, receipt.intendedHash);
});

test('host error text is reduced to a non-sensitive receipt code', async () => {
  const slot: SlotPort = {
    handleId: 'slot-7',
    getClip: () => null,
    createMidiClip: async () => {
      throw new Error('failed at C:\\Users\\person\\secret.mid');
    },
  };

  const receipt = await runSessionClipProbe(slot, clocks);

  assert.equal(receipt.code, 'UNKNOWN_WRITE_ERROR');
});

test('failure after create reports partial and never retries or deletes', async () => {
  const { slot, clips, createLengths } = fakeSlot();

  const receipt = await runSessionClipProbe(slot, {
    ...clocks,
    injectFailure: 'after_create',
  });

  assert.equal(receipt.status, 'partial');
  assert.equal(receipt.code, 'INJECTED_AFTER_CREATE');
  assert.equal(receipt.retryAttempted, false);
  assert.equal(receipt.rollbackClaimed, false);
  assert.equal(clips.length, 1);
  assert.deepEqual(createLengths, [4]);
});
