import path from 'node:path';

export function resourceRootFromEntryDir(entryDir: string): string {
  if (!path.isAbsolute(entryDir)) {
    throw new Error('ENTRY_DIR_NOT_ABSOLUTE');
  }
  return path.resolve(entryDir, '..');
}
