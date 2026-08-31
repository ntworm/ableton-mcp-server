import { createHash, randomUUID } from 'node:crypto';

export interface Gate0Note {
  pitch: number;
  startTime: number;
  duration: number;
  velocity: number;
}

export interface ClipPort {
  handleId: string;
  name: string;
  notes: Gate0Note[];
}

export interface SlotPort {
  handleId: string;
  getClip(): { handleId: string } | null;
  createMidiClip(lengthBeats: number): Promise<ClipPort>;
}

export interface ProbeReceipt {
  receiptId: string;
  status: 'ok' | 'blocked' | 'failed' | 'partial';
  code: string;
  startedAtEpochMs: number;
  durationMs: number;
  slotHandle: string;
  clipHandle: string | null;
  intendedCount: number;
  readbackCount: number;
  intendedHash: string;
  readbackHash: string | null;
  retryAttempted: false;
  rollbackClaimed: false;
}

export interface ProbeOptions {
  nowEpochMs: () => number;
  nowMonotonicMs: () => number;
  injectFailure?: 'after_create';
}

const NOTES: Gate0Note[] = [0, 1, 2, 3].map((startTime) => ({
  pitch: 36,
  startTime,
  duration: 0.25,
  velocity: 100,
}));

function canonical(notes: Gate0Note[]): Gate0Note[] {
  return notes
    .map(({ pitch, startTime, duration, velocity }) => ({
      pitch,
      startTime,
      duration,
      velocity,
    }))
    .sort((a, b) => a.startTime - b.startTime || a.pitch - b.pitch);
}

function hashNotes(notes: Gate0Note[]): string {
  return createHash('sha256').update(JSON.stringify(canonical(notes))).digest('hex');
}

function safeErrorCode(error: unknown): string {
  if (!(error instanceof Error)) return 'UNKNOWN_WRITE_ERROR';
  return /^[A-Z][A-Z0-9_:-]{0,79}$/u.test(error.message)
    ? error.message
    : 'UNKNOWN_WRITE_ERROR';
}

function elapsedMs(options: ProbeOptions, startedMono: number): number {
  return Math.max(0, options.nowMonotonicMs() - startedMono);
}

export async function runSessionClipProbe(
  slot: SlotPort,
  options: ProbeOptions,
): Promise<ProbeReceipt> {
  const startedAtEpochMs = options.nowEpochMs();
  const startedMono = options.nowMonotonicMs();
  const base = {
    receiptId: randomUUID(),
    startedAtEpochMs,
    slotHandle: slot.handleId,
    intendedCount: NOTES.length,
    intendedHash: hashNotes(NOTES),
    retryAttempted: false as const,
    rollbackClaimed: false as const,
  };

  try {
    if (slot.getClip() !== null) {
      return {
        ...base,
        status: 'blocked',
        code: 'SLOT_OCCUPIED',
        durationMs: elapsedMs(options, startedMono),
        clipHandle: null,
        readbackCount: 0,
        readbackHash: null,
      };
    }
  } catch {
    return {
      ...base,
      status: 'failed',
      code: 'SLOT_INSPECTION_FAILED',
      durationMs: elapsedMs(options, startedMono),
      clipHandle: null,
      readbackCount: 0,
      readbackHash: null,
    };
  }

  let clip: ClipPort | null = null;
  try {
    clip = await slot.createMidiClip(4);
    if (options.injectFailure === 'after_create') throw new Error('INJECTED_AFTER_CREATE');

    clip.name = 'Groove Brain Gate 0 Probe';
    clip.notes = NOTES.map((note) => ({ ...note }));

    const readback = canonical(clip.notes);
    const readbackHash = hashNotes(readback);
    const matched = readbackHash === base.intendedHash;
    return {
      ...base,
      status: matched ? 'ok' : 'failed',
      code: matched ? 'READBACK_MATCH' : 'READBACK_MISMATCH',
      durationMs: elapsedMs(options, startedMono),
      clipHandle: clip.handleId,
      readbackCount: readback.length,
      readbackHash,
    };
  } catch (error) {
    let readback: Gate0Note[] | null = null;
    if (clip) {
      try {
        readback = canonical(clip.notes);
      } catch {
        readback = null;
      }
    }
    return {
      ...base,
      status: clip ? 'partial' : 'failed',
      code: safeErrorCode(error),
      durationMs: elapsedMs(options, startedMono),
      clipHandle: clip?.handleId ?? null,
      readbackCount: readback?.length ?? 0,
      readbackHash: readback ? hashNotes(readback) : null,
    };
  }
}
