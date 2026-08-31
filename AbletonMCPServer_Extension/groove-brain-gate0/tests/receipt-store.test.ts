import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import type { ExtensionContext } from '@ableton-extensions/sdk';
import { storeReceipt } from '../src/receipt-store.js';
import type { ProbeReceipt } from '../src/session-clip-probe.js';

const receipt: ProbeReceipt = {
  receiptId: '8a5130f9-6dd1-4a76-a98c-0b8e819b5961',
  extensionVersion: '0.1.1',
  status: 'ok',
  code: 'READBACK_MATCH',
  startedAtEpochMs: 1000,
  durationMs: 4,
  slotHandle: 'slot-7',
  clipHandle: 'clip-9',
  intendedCount: 4,
  readbackCount: 4,
  intendedHash: 'a'.repeat(64),
  readbackHash: 'a'.repeat(64),
  retryAttempted: false,
  rollbackClaimed: false,
};

function fakeContext(storageDirectory: string | undefined): ExtensionContext<'1.0.0'> {
  return { environment: { storageDirectory } } as unknown as ExtensionContext<'1.0.0'>;
}

test('receipt is written once under private storage without note or token payloads', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'gate0-receipt-'));
  try {
    const destination = storeReceipt(fakeContext(root), receipt);
    const relative = path.relative(root, destination);
    const serialized = fs.readFileSync(destination, 'utf8');

    assert.equal(relative, path.join('gate0', 'receipts', '1000-8a5130f9-6dd1-4a76-a98c-0b8e819b5961.json'));
    assert.deepEqual(JSON.parse(serialized), receipt);
    assert.doesNotMatch(serialized, /notes|token|project/i);
    assert.throws(() => storeReceipt(fakeContext(root), receipt), /RECEIPT_ALREADY_EXISTS/u);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test('receipt storage must be available and absolute', () => {
  assert.throws(() => storeReceipt(fakeContext(undefined), receipt), /STORAGE_DIRECTORY_UNAVAILABLE/u);
  assert.throws(() => storeReceipt(fakeContext('relative-storage'), receipt), /STORAGE_DIRECTORY_NOT_ABSOLUTE/u);
});

test('filesystem failures are reduced to a path-free error code', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'gate0-receipt-error-'));
  const notDirectory = path.join(root, 'file');
  fs.writeFileSync(notDirectory, 'occupied', 'utf8');
  try {
    assert.throws(
      () => storeReceipt(fakeContext(notDirectory), receipt),
      (error: unknown) => error instanceof Error && error.message === 'RECEIPT_STORAGE_FAILED',
    );
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});
