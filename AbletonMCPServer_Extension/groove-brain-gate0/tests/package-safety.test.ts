import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import {
  assertSpawnSucceeded,
  normalizeStageMetadata,
  prepareStage,
  promotePackage,
  validateBuildEnvironment,
} from '../package.js';

test('promotePackage refuses to replace an existing final output', (t) => {
  const sandbox = fs.mkdtempSync(path.join(os.tmpdir(), 'gate0-promote-'));
  const buildRoot = path.join(sandbox, 'build-root');
  const temporary = path.join(buildRoot, 'temporary.ablx');
  const output = path.join(buildRoot, 'final.ablx');
  fs.mkdirSync(buildRoot, { recursive: true });
  fs.writeFileSync(temporary, 'new package', 'utf8');
  fs.writeFileSync(output, 'existing package', 'utf8');
  t.after(() => fs.rmSync(sandbox, { recursive: true, force: true }));

  assert.throws(() => promotePackage(buildRoot, temporary, output), /OUTPUT_ALREADY_EXISTS/);
  assert.equal(fs.readFileSync(temporary, 'utf8'), 'new package');
  assert.equal(fs.readFileSync(output, 'utf8'), 'existing package');
});

test('promotePackage atomically renames a complete temporary package', (t) => {
  const sandbox = fs.mkdtempSync(path.join(os.tmpdir(), 'gate0-promote-'));
  const buildRoot = path.join(sandbox, 'build-root');
  const temporary = path.join(buildRoot, 'temporary.ablx');
  const output = path.join(buildRoot, 'final.ablx');
  fs.mkdirSync(buildRoot, { recursive: true });
  fs.writeFileSync(temporary, 'complete package', 'utf8');
  t.after(() => fs.rmSync(sandbox, { recursive: true, force: true }));

  promotePackage(buildRoot, temporary, output);

  assert.equal(fs.existsSync(temporary), false);
  assert.equal(fs.readFileSync(output, 'utf8'), 'complete package');
});

test('normalizeStageMetadata rejects traversal outside the build root', (t) => {
  const sandbox = fs.mkdtempSync(path.join(os.tmpdir(), 'gate0-metadata-'));
  const buildRoot = path.join(sandbox, 'build-root');
  const outside = path.join(sandbox, 'outside');
  fs.mkdirSync(buildRoot, { recursive: true });
  fs.mkdirSync(outside, { recursive: true });
  t.after(() => fs.rmSync(sandbox, { recursive: true, force: true }));

  assert.throws(() => normalizeStageMetadata(buildRoot, outside), /UNSAFE_STAGE_PATH/);
});

test('normalizeStageMetadata rejects symlinks without touching their targets', (t) => {
  const sandbox = fs.mkdtempSync(path.join(os.tmpdir(), 'gate0-metadata-'));
  const external = fs.mkdtempSync(path.join(os.tmpdir(), 'gate0-metadata-external-'));
  const buildRoot = path.join(sandbox, 'build-root');
  const stage = path.join(buildRoot, 'staging', '0.1.0');
  const link = path.join(stage, 'external-link');
  const sentinel = path.join(external, 'sentinel.txt');
  fs.mkdirSync(stage, { recursive: true });
  fs.writeFileSync(sentinel, 'preserve', 'utf8');
  fs.symlinkSync(external, link, process.platform === 'win32' ? 'junction' : 'dir');

  t.after(() => {
    if (fs.existsSync(link)) fs.unlinkSync(link);
    fs.rmSync(sandbox, { recursive: true, force: true });
    assert.equal(fs.readFileSync(sentinel, 'utf8'), 'preserve');
    fs.rmSync(external, { recursive: true, force: true });
  });

  assert.throws(() => normalizeStageMetadata(buildRoot, stage), /UNSAFE_STAGE_CONTENT/);
  assert.equal(fs.readFileSync(sentinel, 'utf8'), 'preserve');
});

test('normalizeStageMetadata applies one ZIP-safe timestamp to files and directories', (t) => {
  const sandbox = fs.mkdtempSync(path.join(os.tmpdir(), 'gate0-metadata-'));
  const buildRoot = path.join(sandbox, 'build-root');
  const stage = path.join(buildRoot, 'staging', '0.1.0');
  const ui = path.join(stage, 'ui');
  const nested = path.join(ui, 'nested');
  const index = path.join(ui, 'index.html');
  const asset = path.join(nested, 'asset.txt');
  fs.mkdirSync(nested, { recursive: true });
  fs.writeFileSync(index, 'index', 'utf8');
  fs.writeFileSync(asset, 'asset', 'utf8');
  t.after(() => fs.rmSync(sandbox, { recursive: true, force: true }));

  normalizeStageMetadata(buildRoot, stage);

  for (const candidate of [stage, ui, nested, index, asset]) {
    assert.equal(fs.statSync(candidate).mtime.toISOString(), '1980-01-01T00:00:00.000Z');
  }
});

test('assertSpawnSucceeded accepts status zero', () => {
  assert.doesNotThrow(() => assertSpawnSucceeded(
    { status: 0, signal: null },
    'TEST_STAGE',
    'v24.14.1',
  ));
});

test('assertSpawnSucceeded reports spawn errors distinctly', () => {
  assert.throws(
    () => assertSpawnSucceeded(
      { status: null, signal: null, error: new Error('missing executable') },
      'TEST_STAGE',
      'v24.14.1',
      'stage=C:/safe-stage',
    ),
    /TEST_STAGE_SPAWN_ERROR:missing executable:stage=C:\/safe-stage:node=v24\.14\.1/,
  );
});

test('assertSpawnSucceeded reports termination signals distinctly', () => {
  assert.throws(
    () => assertSpawnSucceeded(
      { status: null, signal: 'SIGTERM' },
      'TEST_STAGE',
      'v24.14.1',
    ),
    /TEST_STAGE_SIGNAL:SIGTERM:node=v24\.14\.1/,
  );
});

test('assertSpawnSucceeded reports a missing status distinctly', () => {
  assert.throws(
    () => assertSpawnSucceeded(
      { status: null, signal: null },
      'TEST_STAGE',
      'v24.14.1',
    ),
    /TEST_STAGE_NO_STATUS:node=v24\.14\.1/,
  );
});

test('assertSpawnSucceeded reports nonzero exits distinctly', () => {
  assert.throws(
    () => assertSpawnSucceeded(
      { status: 7, signal: null },
      'TEST_STAGE',
      'v24.14.1',
    ),
    /TEST_STAGE_FAILED:7:node=v24\.14\.1/,
  );
});

test('validateBuildEnvironment accepts the supported Windows x64 Node minimum', () => {
  assert.doesNotThrow(() => validateBuildEnvironment('win32', 'x64', 'v24.14.1'));
});

test('validateBuildEnvironment rejects unsupported platform and architecture pairs', () => {
  assert.throws(
    () => validateBuildEnvironment('win32', 'arm64', 'v24.14.1'),
    /UNSUPPORTED_BUILD_PLATFORM:win32-arm64/,
  );
  assert.throws(
    () => validateBuildEnvironment('linux', 'x64', 'v24.14.1'),
    /UNSUPPORTED_BUILD_PLATFORM:linux-x64/,
  );
});

test('validateBuildEnvironment rejects Node below the documented CLI minimum', () => {
  assert.throws(
    () => validateBuildEnvironment('win32', 'x64', 'v24.13.1'),
    /NODE_VERSION_UNSUPPORTED:v24\.13\.1:requires>=24\.14\.1/,
  );
});

test('prepareStage rejects a junction escape without deleting the external target', (t) => {
  const sandbox = fs.mkdtempSync(path.join(os.tmpdir(), 'gate0-stage-'));
  const external = fs.mkdtempSync(path.join(os.tmpdir(), 'gate0-external-'));
  const buildRoot = path.join(sandbox, 'build-root');
  const stage = path.join(buildRoot, 'staging', '0.1.0');
  const sentinel = path.join(external, 'sentinel.txt');
  fs.mkdirSync(path.dirname(stage), { recursive: true });
  fs.writeFileSync(sentinel, 'preserve', 'utf8');
  fs.symlinkSync(external, stage, process.platform === 'win32' ? 'junction' : 'dir');

  t.after(() => {
    if (fs.existsSync(stage)) {
      assert.equal(fs.lstatSync(stage).isSymbolicLink(), true);
      fs.unlinkSync(stage);
    }
    fs.rmSync(sandbox, { recursive: true, force: true });
    assert.equal(fs.readFileSync(sentinel, 'utf8'), 'preserve');
    fs.rmSync(external, { recursive: true, force: true });
  });

  assert.throws(() => prepareStage(buildRoot, stage), /UNSAFE_STAGE_PATH/);
  assert.equal(fs.readFileSync(sentinel, 'utf8'), 'preserve');
});

test('a packaged extension carries the exported seed and no database', async () => {
  // The export is what every search reads. A package built without it is
  // byte-valid and answers every query with nothing.
  const { execFileSync } = await import('node:child_process');
  const zip = path.resolve('build/groove-brain-gate0/Groove-Brain-Gate-0-0.2.0.ablx');
  if (!fs.existsSync(zip)) {
    // The package is built by `npm run gate0:package`, not by the test suite.
    return;
  }
  const listing = execFileSync('tar', ['-tf', zip], { encoding: 'utf8' });
  assert.match(listing, /data\/grooves\.json/u);
  assert.doesNotMatch(listing, /\.sqlite/u);

  const staged = execFileSync('tar', ['-xOf', zip, 'data/grooves.json'], {
    encoding: 'utf8',
    maxBuffer: 64 * 1024 * 1024,
  });
  assert.equal(JSON.parse(staged).schema, 'groove.export.v1');
});
