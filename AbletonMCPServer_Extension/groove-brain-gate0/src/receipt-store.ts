import fs from 'node:fs';
import path from 'node:path';
import type { ExtensionContext } from '@ableton-extensions/sdk';
import type { ProbeReceipt } from './session-clip-probe.js';

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/iu;

function receiptFilename(receipt: ProbeReceipt): string {
  if (!Number.isSafeInteger(receipt.startedAtEpochMs) || receipt.startedAtEpochMs < 0) {
    throw new Error('RECEIPT_TIMESTAMP_INVALID');
  }
  if (!UUID_PATTERN.test(receipt.receiptId)) throw new Error('RECEIPT_ID_INVALID');
  return `${receipt.startedAtEpochMs}-${receipt.receiptId}.json`;
}

export function storeReceipt(
  context: ExtensionContext<'1.0.0'>,
  receipt: ProbeReceipt,
): string {
  const root = context.environment.storageDirectory;
  if (!root) throw new Error('STORAGE_DIRECTORY_UNAVAILABLE');
  if (!path.isAbsolute(root)) throw new Error('STORAGE_DIRECTORY_NOT_ABSOLUTE');

  const directory = path.join(root, 'gate0', 'receipts');
  const destination = path.join(directory, receiptFilename(receipt));
  try {
    fs.mkdirSync(directory, { recursive: true });
    fs.writeFileSync(destination, `${JSON.stringify(receipt, null, 2)}\n`, {
      encoding: 'utf8',
      flag: 'wx',
    });
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'EEXIST') {
      throw new Error('RECEIPT_ALREADY_EXISTS');
    }
    throw new Error('RECEIPT_STORAGE_FAILED');
  }
  return destination;
}
