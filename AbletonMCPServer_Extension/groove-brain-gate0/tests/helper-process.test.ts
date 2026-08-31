import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { HelperSession, loadRuntime } from '../src/helper-process.js';
import { parseHelperReady, parseModalResult } from '../src/protocol.js';

const stage = path.resolve('build/groove-brain-gate0/staging/0.1.0');

function writeRuntimeFixture(root: string, helperRelative = 'windows-x64/groove-brain-gate0-helper.exe') {
  const runtimeRoot = path.join(root, 'runtime');
  const executable = path.join(runtimeRoot, helperRelative);
  fs.mkdirSync(path.dirname(executable), { recursive: true });
  fs.writeFileSync(executable, 'fixture-helper', 'utf8');
  const sha256 = createHash('sha256').update(fs.readFileSync(executable)).digest('hex');
  fs.writeFileSync(
    path.join(runtimeRoot, 'manifest.json'),
    `${JSON.stringify({
      protocol: 1,
      platform: 'win32-x64',
      helper: helperRelative,
      sha256,
    }, null, 2)}\n`,
    'utf8',
  );
  return { executable, sha256 };
}

test('ready parser rejects malformed JSON, wrong parent, and unsafe port', () => {
  assert.throws(() => parseHelperReady('{', 7), /INVALID_READY/);
  assert.throws(
    () => parseHelperReady(
      '{"type":"ready","protocol":1,"host":"127.0.0.1","port":0,"parent_pid":7}',
      7,
    ),
    /INVALID_READY/,
  );
  assert.throws(
    () => parseHelperReady(
      '{"type":"ready","protocol":1,"host":"127.0.0.1","port":40000,"parent_pid":8}',
      7,
    ),
    /INVALID_READY/,
  );
});

test('ready parser accepts the exact helper handshake', () => {
  assert.deepEqual(
    parseHelperReady(
      '{"type":"ready","protocol":1,"host":"127.0.0.1","port":40000,"parent_pid":7}',
      7,
    ),
    { type: 'ready', protocol: 1, host: '127.0.0.1', port: 40000, parent_pid: 7 },
  );
});

test('modal parser accepts only the two protocol-one outcomes', () => {
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
  assert.throws(
    () => parseModalResult('{"action":"cancel","confirmed":false,"protocol":2}'),
    /INVALID_MODAL_PROTOCOL/,
  );
  assert.throws(() => parseModalResult('{'), /INVALID_MODAL_RESULT/);
});

test('runtime loader verifies the exact bundled helper and hash', (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'gate0-runtime-'));
  const fixture = writeRuntimeFixture(root);
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));

  assert.deepEqual(loadRuntime(root), {
    executable: fs.realpathSync.native(fixture.executable),
    manifest: {
      protocol: 1,
      platform: 'win32-x64',
      helper: 'windows-x64/groove-brain-gate0-helper.exe',
      sha256: fixture.sha256,
    },
  });
});

test('runtime loader rejects traversal and hash mismatch', (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'gate0-runtime-'));
  const outside = path.join(root, 'outside.exe');
  fs.mkdirSync(path.join(root, 'runtime'), { recursive: true });
  fs.writeFileSync(outside, 'outside', 'utf8');
  const outsideHash = createHash('sha256').update(fs.readFileSync(outside)).digest('hex');
  fs.writeFileSync(
    path.join(root, 'runtime', 'manifest.json'),
    JSON.stringify({
      protocol: 1,
      platform: 'win32-x64',
      helper: '../outside.exe',
      sha256: outsideHash,
    }),
    'utf8',
  );
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));

  assert.throws(() => loadRuntime(root), /INVALID_HELPER_PATH/);

  const fixture = writeRuntimeFixture(root);
  fs.writeFileSync(fixture.executable, 'tampered', 'utf8');
  assert.throws(() => loadRuntime(root), /HELPER_HASH_MISMATCH/);
});

test('two sessions use distinct endpoints, authenticate, and stop', {
  skip: fs.existsSync(stage) ? false : 'Gate 0 package stage is created in Task 5',
}, async () => {
  const first = await HelperSession.start(stage);
  const second = await HelperSession.start(stage);
  try {
    assert.notEqual(first.ready.port, second.ready.port);
    assert.notEqual(first.modalUrl, second.modalUrl);
    await Promise.all([first.assertHealthy(), second.assertHealthy()]);
  } finally {
    await Promise.all([first.stop(), second.stop()]);
  }
});
