import { createHash } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

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
const normalizedBuildRoot = path.normalize(path.resolve(buildRoot));
const normalizedStage = path.normalize(path.resolve(stage));
if (
  normalizedStage === normalizedBuildRoot
  || !normalizedStage.startsWith(`${normalizedBuildRoot}${path.sep}`)
) {
  throw new Error('UNSAFE_STAGE_PATH');
}
fs.rmSync(normalizedStage, { recursive: true, force: true });
fs.mkdirSync(path.join(stage, 'dist'), { recursive: true });
fs.mkdirSync(path.join(stage, 'runtime', 'windows-x64'), { recursive: true });

const cargo = spawnSync(
  'cargo',
  ['build', '--release', '--locked', '--manifest-path', path.join(sourceRoot, 'helper', 'Cargo.toml')],
  { stdio: 'inherit', shell: false, env: { ...process.env, CARGO_TARGET_DIR: cargoTarget } },
);
if (cargo.status !== 0) throw new Error(`CARGO_BUILD_FAILED:${cargo.status}`);

const helperName = 'groove-brain-gate0-helper.exe';
const helperSource = path.join(cargoTarget, 'release', helperName);
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

const output = path.join(buildRoot, `Groove-Brain-Gate-0-${version}.ablx`);
const cli = path.join(extensionRoot, 'node_modules', '@ableton-extensions', 'cli', 'dist', 'cli.mjs');
const packaged = spawnSync(
  process.execPath,
  [cli, 'package', stage, '-i', 'ui', '-i', 'runtime', '-o', output],
  { stdio: 'inherit', shell: false },
);
if (packaged.status !== 0) throw new Error(`ABLx_PACKAGE_FAILED:${packaged.status}`);
console.log(JSON.stringify({ output, stage, helperSha256, node: process.version }));
