import assert from 'node:assert/strict';
import path from 'node:path';
import test from 'node:test';
import { resourceRootFromEntryDir } from '../src/resource-path.js';

test('resource root is the parent of installed dist and ignores cwd', () => {
  const installedRoot = path.resolve('C:/Gate0 Installed/Groove Brain');
  const entryDir = path.join(installedRoot, 'dist');
  assert.equal(resourceRootFromEntryDir(entryDir), installedRoot);
});
