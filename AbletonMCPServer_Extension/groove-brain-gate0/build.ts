import * as esbuild from 'esbuild';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.dirname(fileURLToPath(import.meta.url));
const manifest = JSON.parse(fs.readFileSync(path.join(root, 'manifest.json'), 'utf8')) as {
  entry: string;
};

await esbuild.build({
  entryPoints: [path.join(root, 'src', 'extension.ts')],
  outfile: path.join(root, manifest.entry),
  bundle: true,
  format: 'cjs',
  platform: 'node',
  target: 'node24',
  sourcesContent: false,
  sourcemap: false,
  logLevel: 'info',
});
