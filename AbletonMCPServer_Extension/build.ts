import * as esbuild from 'esbuild';
import * as fs from 'node:fs';

const manifest = JSON.parse(fs.readFileSync('manifest.json', 'utf8'));
const production = process.argv.includes('--production');
const watch = process.argv.includes('--watch');

if (watch) {
  const ctx = await esbuild.context({
    entryPoints: ['src/extension.ts'],
    outfile: manifest.entry,
    bundle: true,
    format: 'cjs',
    platform: 'node',
    sourcesContent: false,
    logLevel: 'info',
    minify: false,
    sourcemap: true,
  });
  await ctx.watch();
  console.log('esbuild is watching src/ for changes...');
} else {
  await esbuild.build({
    entryPoints: ['src/extension.ts'],
    outfile: manifest.entry,
    bundle: true,
    format: 'cjs',
    platform: 'node',
    sourcesContent: false,
    logLevel: production ? 'silent' : 'info',
    sourcemap: !production,
  });
}
