import assert from 'node:assert/strict';
import test from 'node:test';
import { receiptModalDataUrl, sanitizeErrorMessage } from '../src/extension.js';
import { parseModalResult } from '../src/protocol.js';
import type { ProbeReceipt } from '../src/session-clip-probe.js';

test('modal parser accepts only explicit cancel or confirmed probe', () => {
  assert.deepEqual(
    parseModalResult('{"action":"cancel","confirmed":false,"protocol":1}'),
    { action: 'cancel', confirmed: false, protocol: 1 },
  );
  assert.deepEqual(
    parseModalResult('{"action":"run_session_probe","confirmed":true,"protocol":1}'),
    { action: 'run_session_probe', confirmed: true, protocol: 1 },
  );
  assert.throws(
    () => parseModalResult('{"action":"run_session_probe","confirmed":false,"protocol":1}'),
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

test('receipt modal escapes receipt text and does not expose a storage path', () => {
  const receipt: ProbeReceipt = {
    receiptId: '8a5130f9-6dd1-4a76-a98c-0b8e819b5961',
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
