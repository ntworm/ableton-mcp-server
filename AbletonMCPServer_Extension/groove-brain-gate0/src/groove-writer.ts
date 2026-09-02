/**
 * The export speaks ticks; the SDK speaks beats. This is the only place that
 * conversion happens, so a rounding decision is made once.
 */

export interface ExportedGroove {
  id: string;
  bars: number;
  meter: string;
  ppq: number;
  notes: [number, number, number, number][];
}

export interface ClipNote {
  pitch: number;
  startTime: number;
  duration: number;
  velocity: number;
}

// A thirty-second note at 4/4. Shorter than this and Live renders nothing
// visible, so a hit exported with no length still has to become one.
const MIN_DURATION_BEATS = 0.125;

function beatsPerBar(meter: string): number {
  const [numerator, denominator] = meter.split('/').map((part) => Number.parseInt(part, 10));
  if (!Number.isFinite(numerator) || !Number.isFinite(denominator) || denominator === 0) {
    return 4;
  }
  return (numerator * 4) / denominator;
}

export function toClipNotes(groove: ExportedGroove): ClipNote[] {
  const ppq = groove.ppq > 0 ? groove.ppq : 480;
  return groove.notes.map(([pitch, startTicks, durationTicks, velocity]) => ({
    pitch,
    startTime: startTicks / ppq,
    duration: Math.max(MIN_DURATION_BEATS, durationTicks / ppq),
    velocity,
  }));
}

export function clipLengthBeats(groove: ExportedGroove): number {
  const stated = groove.bars * beatsPerBar(groove.meter);
  const notes = toClipNotes(groove);
  const lastEnd = notes.reduce(
    (furthest, note) => Math.max(furthest, note.startTime + note.duration),
    0,
  );
  // Whichever is longer. The bar count is metadata and can disagree with the
  // notes; a clip shorter than the last note silently drops it.
  return Math.max(stated, Math.ceil(lastEnd));
}
