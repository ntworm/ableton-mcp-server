import { createHash, randomUUID } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const ZIP_SAFE_TIMESTAMP = new Date(Date.UTC(1980, 0, 1, 0, 0, 0));

function normalizedPathKey(candidate: string): string {
  const normalized = path.normalize(path.resolve(candidate));
  return process.platform === 'win32' ? normalized.toLowerCase() : normalized;
}

function isStrictDescendant(root: string, candidate: string): boolean {
  const relative = path.relative(root, candidate);
  return relative !== ''
    && relative !== '..'
    && !relative.startsWith(`..${path.sep}`)
    && !path.isAbsolute(relative);
}

function lstatIfPresent(candidate: string) {
  try {
    return fs.lstatSync(candidate);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') return undefined;
    throw error;
  }
}

function assertExistingPathComponentsSafe(target: string): void {
  const resolved = path.normalize(path.resolve(target));
  const parsed = path.parse(resolved);
  const parts = resolved.slice(parsed.root.length).split(path.sep).filter(Boolean);
  let current = parsed.root;
  for (const part of parts) {
    current = path.join(current, part);
    const stats = lstatIfPresent(current);
    if (!stats) return;
    if (stats.isSymbolicLink()) throw new Error('UNSAFE_STAGE_PATH');
    const real = fs.realpathSync.native(current);
    if (normalizedPathKey(real) !== normalizedPathKey(current)) {
      throw new Error('UNSAFE_STAGE_PATH');
    }
  }
}

function nearestExistingAncestor(candidate: string): string {
  let current = path.normalize(path.resolve(candidate));
  while (!lstatIfPresent(current)) {
    const parent = path.dirname(current);
    if (parent === current) throw new Error('UNSAFE_STAGE_PATH');
    current = parent;
  }
  return current;
}

export function validateBuildEnvironment(
  platform: NodeJS.Platform,
  arch: string,
  nodeVersion: string,
): void {
  if (platform !== 'win32' || arch !== 'x64') {
    throw new Error(`UNSUPPORTED_BUILD_PLATFORM:${platform}-${arch}`);
  }
  const match = /^v?(\d+)\.(\d+)\.(\d+)$/.exec(nodeVersion);
  const actual = match?.slice(1).map(Number);
  const required = [24, 14, 1];
  const supported = actual !== undefined && actual.some((value, index) => (
    value > required[index]
    && actual.slice(0, index).every((earlier, earlierIndex) => earlier === required[earlierIndex])
  )) || actual?.every((value, index) => value === required[index]);
  if (!supported) {
    throw new Error(`NODE_VERSION_UNSUPPORTED:${nodeVersion}:requires>=24.14.1`);
  }
}

type SpawnResult = {
  status: number | null;
  signal: NodeJS.Signals | null;
  error?: Error;
};

export function assertSpawnSucceeded(
  result: SpawnResult,
  label: string,
  nodeVersion: string,
  context?: string,
): void {
  const details = [context, `node=${nodeVersion}`].filter(Boolean).join(':');
  if (result.error) {
    throw new Error(`${label}_SPAWN_ERROR:${result.error.message}:${details}`);
  }
  if (result.signal) {
    throw new Error(`${label}_SIGNAL:${result.signal}:${details}`);
  }
  if (result.status === null) {
    throw new Error(`${label}_NO_STATUS:${details}`);
  }
  if (result.status !== 0) {
    throw new Error(`${label}_FAILED:${result.status}:${details}`);
  }
}

function collectStageEntries(stageRoot: string, current: string): string[] {
  const entries: string[] = [];
  for (const entry of fs.readdirSync(current, { withFileTypes: true }).sort((a, b) => (
    a.name < b.name ? -1 : a.name > b.name ? 1 : 0
  ))) {
    const candidate = path.join(current, entry.name);
    if (!isStrictDescendant(stageRoot, candidate)) {
      throw new Error('UNSAFE_STAGE_CONTENT');
    }
    const stats = fs.lstatSync(candidate);
    if (stats.isSymbolicLink()) throw new Error('UNSAFE_STAGE_CONTENT');
    if (stats.isDirectory()) {
      entries.push(...collectStageEntries(stageRoot, candidate));
    } else if (!stats.isFile()) {
      throw new Error('UNSAFE_STAGE_CONTENT');
    }
    entries.push(candidate);
  }
  return entries;
}

export function normalizeStageMetadata(buildRoot: string, stage: string): void {
  const normalizedBuildRoot = path.normalize(path.resolve(buildRoot));
  const normalizedStage = path.normalize(path.resolve(stage));
  if (!isStrictDescendant(normalizedBuildRoot, normalizedStage)) {
    throw new Error('UNSAFE_STAGE_PATH');
  }
  assertExistingPathComponentsSafe(normalizedBuildRoot);
  assertExistingPathComponentsSafe(normalizedStage);
  const realBuildRoot = fs.realpathSync.native(normalizedBuildRoot);
  const realStage = fs.realpathSync.native(normalizedStage);
  if (!isStrictDescendant(realBuildRoot, realStage)) {
    throw new Error('UNSAFE_STAGE_PATH');
  }
  if (!fs.lstatSync(normalizedStage).isDirectory()) {
    throw new Error('UNSAFE_STAGE_CONTENT');
  }
  for (const candidate of collectStageEntries(normalizedStage, normalizedStage)) {
    fs.utimesSync(candidate, ZIP_SAFE_TIMESTAMP, ZIP_SAFE_TIMESTAMP);
  }
  fs.utimesSync(normalizedStage, ZIP_SAFE_TIMESTAMP, ZIP_SAFE_TIMESTAMP);
}

export function promotePackage(buildRoot: string, temporary: string, output: string): void {
  const normalizedBuildRoot = path.normalize(path.resolve(buildRoot));
  const normalizedTemporary = path.normalize(path.resolve(temporary));
  const normalizedOutput = path.normalize(path.resolve(output));
  if (
    !isStrictDescendant(normalizedBuildRoot, normalizedTemporary)
    || !isStrictDescendant(normalizedBuildRoot, normalizedOutput)
    || normalizedPathKey(normalizedTemporary) === normalizedPathKey(normalizedOutput)
    || path.extname(normalizedTemporary).toLowerCase() !== '.ablx'
    || path.extname(normalizedOutput).toLowerCase() !== '.ablx'
  ) {
    throw new Error('UNSAFE_PACKAGE_PATH');
  }
  if (lstatIfPresent(normalizedOutput)) throw new Error('OUTPUT_ALREADY_EXISTS');

  assertExistingPathComponentsSafe(normalizedBuildRoot);
  assertExistingPathComponentsSafe(normalizedTemporary);
  assertExistingPathComponentsSafe(normalizedOutput);
  const temporaryStats = lstatIfPresent(normalizedTemporary);
  if (!temporaryStats?.isFile() || temporaryStats.isSymbolicLink()) {
    throw new Error('PACKAGE_TEMP_INCOMPLETE');
  }

  const realBuildRoot = fs.realpathSync.native(normalizedBuildRoot);
  const realTemporary = fs.realpathSync.native(normalizedTemporary);
  const realOutputParent = fs.realpathSync.native(path.dirname(normalizedOutput));
  if (
    !isStrictDescendant(realBuildRoot, realTemporary)
    || (
      normalizedPathKey(realOutputParent) !== normalizedPathKey(realBuildRoot)
      && !isStrictDescendant(realBuildRoot, realOutputParent)
    )
  ) {
    throw new Error('UNSAFE_PACKAGE_PATH');
  }

  fs.renameSync(normalizedTemporary, normalizedOutput);
}

export function prepareStage(buildRoot: string, stage: string): void {
  const normalizedBuildRoot = path.normalize(path.resolve(buildRoot));
  const normalizedStage = path.normalize(path.resolve(stage));
  if (!isStrictDescendant(normalizedBuildRoot, normalizedStage)) {
    throw new Error('UNSAFE_STAGE_PATH');
  }

  assertExistingPathComponentsSafe(normalizedBuildRoot);
  fs.mkdirSync(normalizedBuildRoot, { recursive: true });
  assertExistingPathComponentsSafe(normalizedBuildRoot);
  assertExistingPathComponentsSafe(normalizedStage);

  const realBuildRoot = fs.realpathSync.native(normalizedBuildRoot);
  const realAncestor = fs.realpathSync.native(nearestExistingAncestor(normalizedStage));
  if (
    normalizedPathKey(realAncestor) !== normalizedPathKey(realBuildRoot)
    && !isStrictDescendant(realBuildRoot, realAncestor)
  ) {
    throw new Error('UNSAFE_STAGE_PATH');
  }

  fs.rmSync(normalizedStage, { recursive: true, force: true });
  fs.mkdirSync(path.join(normalizedStage, 'dist'), { recursive: true });
  fs.mkdirSync(path.join(normalizedStage, 'runtime', 'windows-x64'), { recursive: true });
}

function isMainModule(moduleUrl: string, entryPath = process.argv[1]): boolean {
  if (!entryPath) return false;
  return normalizedPathKey(fileURLToPath(moduleUrl)) === normalizedPathKey(entryPath);
}

function main(): void {
  validateBuildEnvironment(process.platform, process.arch, process.version);
  const sourceRoot = path.dirname(fileURLToPath(import.meta.url));
  const extensionRoot = path.resolve(sourceRoot, '..');
  const versionIndex = process.argv.indexOf('--version');
  const version = versionIndex >= 0 ? process.argv[versionIndex + 1] : undefined;
  if (!version || !/^\d+\.\d+\.\d+$/.test(version)) {
    throw new Error('VERSION_REQUIRED');
  }
  const buildRoot = path.join(extensionRoot, 'build', 'groove-brain-gate0');
  const cargoTarget = path.join(buildRoot, 'cargo-target');
  const stage = path.join(buildRoot, 'staging', version);
  prepareStage(buildRoot, stage);

  const cargo = spawnSync(
    'cargo',
    [
      'build',
      '--release',
      '--locked',
      '--target',
      'x86_64-pc-windows-msvc',
      '--manifest-path',
      path.join(sourceRoot, 'helper', 'Cargo.toml'),
    ],
    { stdio: 'inherit', shell: false, env: { ...process.env, CARGO_TARGET_DIR: cargoTarget } },
  );
  assertSpawnSucceeded(cargo, 'CARGO_BUILD', process.version, 'target=x86_64-pc-windows-msvc');

  const helperName = 'groove-brain-gate0-helper.exe';
  const helperSource = path.join(cargoTarget, 'x86_64-pc-windows-msvc', 'release', helperName);
  const helperTarget = path.join(stage, 'runtime', 'windows-x64', helperName);
  fs.copyFileSync(helperSource, helperTarget);
  const helperSha256 = createHash('sha256').update(fs.readFileSync(helperTarget)).digest('hex');
  fs.writeFileSync(
    path.join(stage, 'runtime', 'manifest.json'),
    JSON.stringify({ protocol: 1, platform: 'win32-x64', helper: `windows-x64/${helperName}`, sha256: helperSha256 }, null, 2) + '\n',
    'utf8',
  );

  fs.cpSync(path.join(sourceRoot, 'ui'), path.join(stage, 'ui'), { recursive: true });
  fs.copyFileSync(path.join(sourceRoot, 'dist', 'extension.js'), path.join(stage, 'dist', 'extension.js'));
  const manifest = JSON.parse(fs.readFileSync(path.join(sourceRoot, 'manifest.json'), 'utf8')) as Record<string, unknown>;
  manifest.version = version;
  fs.writeFileSync(path.join(stage, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n', 'utf8');
  normalizeStageMetadata(buildRoot, stage);

  const output = path.join(buildRoot, `Groove-Brain-Gate-0-${version}.ablx`);
  if (lstatIfPresent(output)) throw new Error('OUTPUT_ALREADY_EXISTS');
  const temporaryOutput = path.join(
    buildRoot,
    `.Groove-Brain-Gate-0-${version}.${process.pid}-${randomUUID()}.tmp.ablx`,
  );
  const cli = path.join(extensionRoot, 'node_modules', '@ableton-extensions', 'cli', 'dist', 'cli.mjs');
  try {
    const packaged = spawnSync(
      process.execPath,
      [cli, 'package', stage, '-i', 'ui', '-i', 'runtime', '-o', temporaryOutput],
      { stdio: 'inherit', shell: false },
    );
    assertSpawnSucceeded(packaged, 'ABLx_PACKAGE', process.version, `stage=${stage}`);
    promotePackage(buildRoot, temporaryOutput, output);
  } finally {
    const temporaryStats = lstatIfPresent(temporaryOutput);
    if (temporaryStats?.isFile() || temporaryStats?.isSymbolicLink()) {
      fs.unlinkSync(temporaryOutput);
    }
  }
  console.log(JSON.stringify({ output, stage, helperSha256, node: process.version }));
}

if (isMainModule(import.meta.url)) main();
