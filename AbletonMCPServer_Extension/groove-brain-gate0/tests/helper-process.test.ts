import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import http from 'node:http';
import type { AddressInfo } from 'node:net';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { HelperSession, loadRuntime } from '../src/helper-process.js';
import { parseHelperReady, parseModalResult } from '../src/protocol.js';

const stage = path.resolve('build/groove-brain-gate0/staging/0.1.0');

function writeRuntimeFixture(
  root: string,
  helperRelative = 'windows-x64/groove-brain-gate0-helper.exe',
  runtimeVersion = '0.1.0',
  extensionVersion = '0.1.0',
) {
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
      version: runtimeVersion,
      helper: helperRelative,
      sha256,
    }, null, 2)}\n`,
    'utf8',
  );
  fs.writeFileSync(
    path.join(root, 'manifest.json'),
    `${JSON.stringify({ entry: 'dist/extension.js', version: extensionVersion }, null, 2)}\n`,
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
    parseModalResult('{"action":"handoff","confirmed":true,"protocol":1}'),
    { action: 'handoff', confirmed: true, protocol: 1 },
  );
  assert.throws(
    () => parseModalResult('{"action":"handoff","confirmed":false,"protocol":1}'),
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
      version: '0.1.0',
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
      version: '0.1.0',
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

test('runtime loader rejects an invalid package version', (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'gate0-runtime-'));
  writeRuntimeFixture(root);
  const manifestPath = path.join(root, 'runtime', 'manifest.json');
  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8')) as Record<string, unknown>;
  manifest.version = '../invalid';
  fs.writeFileSync(manifestPath, JSON.stringify(manifest), 'utf8');
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));

  assert.throws(() => loadRuntime(root), /INVALID_RUNTIME_MANIFEST/);
});

test('runtime loader rejects a version different from the extension manifest', (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'gate0-runtime-'));
  writeRuntimeFixture(
    root,
    'windows-x64/groove-brain-gate0-helper.exe',
    '0.1.1',
    '0.1.0',
  );
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));

  assert.throws(() => loadRuntime(root), /RUNTIME_VERSION_MISMATCH/);
});

test('health probe works when the Extension Host omits global AbortSignal', async (t) => {
  const token = 'gate0-health-token';
  let requestSeen: { method?: string; authorization?: string; origin?: string } | null = null;
  const server = http.createServer((request, response) => {
    requestSeen = {
      method: request.method,
      authorization: request.headers.authorization,
      origin: request.headers.origin,
    };
    response.writeHead(200, { 'Content-Type': 'application/json' });
    response.end('{"status":"ok","protocol":1}');
  });
  await new Promise<void>((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, 'localhost', resolve);
  });
  t.after(() => new Promise<void>((resolve, reject) => {
    server.close((error) => (error ? reject(error) : resolve()));
  }));

  const address = server.address() as AddressInfo;
  const session = Object.create(HelperSession.prototype) as HelperSession;
  Object.assign(session as unknown as Record<string, unknown>, {
    ready: {
      type: 'ready',
      protocol: 1,
      host: '127.0.0.1',
      port: address.port,
      parent_pid: process.pid,
    },
    token,
    extensionVersion: '0.1.1',
  });

  const originalAbortSignal = Object.getOwnPropertyDescriptor(globalThis, 'AbortSignal');
  assert.ok(originalAbortSignal);
  Object.defineProperty(globalThis, 'AbortSignal', {
    ...originalAbortSignal,
    value: undefined,
  });
  try {
    await session.assertHealthy();
  } finally {
    Object.defineProperty(globalThis, 'AbortSignal', originalAbortSignal);
  }

  assert.deepEqual(requestSeen, {
    method: 'POST',
    authorization: `Bearer ${token}`,
    origin: `http://localhost:${address.port}`,
  });
});

test('two sessions use distinct endpoints, authenticate, and stop', {
  skip: fs.existsSync(stage) ? false : 'Gate 0 package stage is created in Task 5',
}, async () => {
  const first = await HelperSession.start(stage);
  const second = await HelperSession.start(stage);
  try {
    assert.equal(first.extensionVersion, '0.1.0');
    assert.notEqual(first.ready.port, second.ready.port);
    assert.notEqual(first.modalUrl, second.modalUrl);
    await Promise.all([first.assertHealthy(), second.assertHealthy()]);
  } finally {
    await Promise.all([first.stop(), second.stop()]);
  }
});
