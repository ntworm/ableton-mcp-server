import assert from 'node:assert/strict';
import test from 'node:test';
import { sanitizeErrorMessage } from '../src/extension.js';
import { parseModalResult } from '../src/protocol.js';

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
