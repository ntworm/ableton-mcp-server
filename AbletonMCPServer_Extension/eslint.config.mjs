// Structure ratchet for the Extension sources.
//
// The limits are fixed and must not be raised: complexity 10, 60 lines per
// function and 500 lines per file, counting comments and blank lines, the same
// three limits as scripts/quality_gate.py for the Python code. Debt recorded in
// eslint-suppressions.json only goes down: run `npm run lint:prune` after the
// code improves, never `--suppress-all` again.
//
// The TypeScript parser reads syntax only; no type information is used, so the
// type checking stays with `tsc --noEmit` in `npm run build`.

import tsParser from '@typescript-eslint/parser';

const limits = {
  complexity: ['error', { max: 10 }],
  'max-lines': ['error', { max: 500, skipBlankLines: false, skipComments: false }],
  'max-lines-per-function': ['error', { max: 60, skipBlankLines: false, skipComments: false }],
};

export default [
  {
    ignores: ['**/node_modules/**', '**/dist/**', 'vendor/**'],
  },
  {
    files: ['**/*.{js,mjs,cjs}'],
    rules: limits,
  },
  {
    files: ['**/*.ts'],
    languageOptions: { parser: tsParser },
    rules: limits,
  },
];
