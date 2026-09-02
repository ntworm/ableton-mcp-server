import assert from 'node:assert/strict';
import test from 'node:test';
import { receiptModalDataUrl, sanitizeErrorMessage } from '../src/extension.js';
import { parseModalResult } from '../src/protocol.js';
import type { ProbeReceipt } from '../src/session-clip-probe.js';

test('cancel still needs no groove', () => {
  assert.deepEqual(
    parseModalResult('{"action":"cancel","confirmed":false,"protocol":1}'),
    { action: 'cancel', confirmed: false, protocol: 1 },
  );
});

test('a handoff closes the modal without carrying a groove', () => {
  // The choice arrives later, from the phone, through the helper. The modal's
  // only job now is to free Live.
  assert.deepEqual(
    parseModalResult('{"action":"handoff","confirmed":true,"protocol":1}'),
    { action: 'handoff', confirmed: true, protocol: 1 },
  );
});

test('an unconfirmed handoff is refused', () => {
  assert.throws(
    () => parseModalResult('{"action":"handoff","confirmed":false,"protocol":1}'),
    /INVALID_MODAL_RESULT/,
  );
});

test('the old insert action is no longer accepted', () => {
  assert.throws(
    () =>
      parseModalResult(
        '{"action":"insert_groove","confirmed":true,"protocol":1,"groove_id":"a1"}',
      ),
    /INVALID_MODAL_RESULT/,
  );
});

test('extension diagnostics redact a bootstrap token', () => {
  const token = 'a'.repeat(64);
  assert.equal(
    sanitizeErrorMessage(new Error(`failed URL http://localhost:1234/#${token}`)),
    'failed URL http://localhost:1234/#[redacted]',
  );
});

test('probe clock returns a finite timestamp without global performance', async () => {
  const extensionModule = await import('../src/extension.js');
  const monotonicNow = (extensionModule as unknown as {
    monotonicNow?: () => number;
  }).monotonicNow;
  const originalPerformance = Object.getOwnPropertyDescriptor(globalThis, 'performance');
  assert.ok(originalPerformance);
  Object.defineProperty(globalThis, 'performance', {
    configurable: true,
    enumerable: originalPerformance.enumerable,
    writable: true,
    value: undefined,
  });

  let timestamp: number | undefined;
  try {
    assert.doesNotThrow(() => {
      timestamp = monotonicNow?.();
    });
  } finally {
    Object.defineProperty(globalThis, 'performance', originalPerformance);
  }

  assert.ok(timestamp !== undefined);
  assert.equal(Number.isFinite(timestamp), true);
  assert.ok(timestamp >= 0);
});

test('receipt modal escapes receipt text and does not expose a storage path', () => {
  const receipt: ProbeReceipt = {
    receiptId: '8a5130f9-6dd1-4a76-a98c-0b8e819b5961',
    extensionVersion: '0.1.1',
    status: 'failed',
    code: '<script>&',
    startedAtEpochMs: 1000,
    durationMs: 4,
    slotHandle: 'slot-7',
    clipHandle: null,
    intendedCount: 4,
    readbackCount: 0,
    intendedHash: 'a'.repeat(64),
    readbackHash: null,
    retryAttempted: false,
    rollbackClaimed: false,
  };

  const html = decodeURIComponent(receiptModalDataUrl(receipt).split(',', 2)[1] ?? '');

  assert.match(html, /&lt;script&gt;&amp;/u);
  assert.doesNotMatch(html, /<script>/u);
  assert.match(html, /"receiptSaved": true/u);
  assert.doesNotMatch(html, /receiptPath|storageDirectory/u);
});
