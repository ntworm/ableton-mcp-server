/**
 * Apply one command to the Live set.
 *
 * Every precondition is checked and reported rather than thrown: the caller is
 * a page on a phone, and a stack trace there tells the user nothing. A refusal
 * carries a code the panel can render as a sentence.
 */

import type { Command } from './command.js';
import { resolveNote, summariseCoverage, type Coverage, type KitProfile } from './kit-profile.js';
import type { ClipNote } from './transforms.js';

interface WritableClip {
  name: string;
  notes: unknown;
}

interface WritableSlot {
  clip: { name?: string } | null;
  createMidiClip(length: number): Promise<WritableClip>;
  deleteClip(): Promise<void>;
}

interface WritableTrack {
  name: string;
  clipSlots?: WritableSlot[];
}

export interface WritableSong {
  tempo: number;
  tracks: WritableTrack[];
}

export interface Receipt {
  status: 'ok' | 'refused';
  code: string;
  trackName: string | null;
  slotIndex: number;
  noteCount: number;
  coverage?: Coverage;
}

function refuse(code: string, command: Command, trackName: string | null = null): Receipt {
  return { status: 'refused', code, trackName, slotIndex: command.slotIndex, noteCount: 0 };
}

export async function applyCommand(
  song: WritableSong,
  command: Command,
  notes: ClipNote[],
  lengthBeats: number,
  profile: KitProfile,
): Promise<Receipt> {
  const track = song.tracks[command.trackIndex];
  const slot = track?.clipSlots?.[command.slotIndex];
  if (!track || !slot) return refuse('INDEX_OUT_OF_RANGE', command, track?.name ?? null);

  if (command.op === 'clear') {
    if (!slot.clip) return refuse('SLOT_ALREADY_EMPTY', command, track.name);
    await slot.deleteClip();
    return { status: 'ok', code: 'CLEARED', trackName: track.name, slotIndex: command.slotIndex, noteCount: 0 };
  }

  if (slot.clip && !command.replace) return refuse('SLOT_NOT_EMPTY', command, track.name);

  // Resolved before anything is created. A note the kit cannot play is dropped
  // rather than written: an inaudible note in the clip is one the user will
  // move around wondering why it makes no sound.
  const coverage = summariseCoverage(profile, notes.map((note) => note.pitch));
  const audible: ClipNote[] = [];
  for (const note of notes) {
    const resolved = resolveNote(profile, note.pitch);
    if (resolved.status === 'silent') continue;
    audible.push({ ...note, pitch: resolved.pitch });
  }
  if (audible.length === 0) {
    return { ...refuse('NOTHING_AUDIBLE', command, track.name), coverage };
  }

  // Captured before the delete, which clears it: reading it afterwards
  // would report every replace as a fresh create.
  const replaced = slot.clip !== null;
  if (replaced) await slot.deleteClip();
  const clip = await slot.createMidiClip(lengthBeats);
  clip.name = `Groove Brain ${command.grooveId ?? ''}`.trim();
  clip.notes = audible;

  return {
    status: 'ok',
    code: replaced ? 'REPLACED' : 'CREATED',
    trackName: track.name,
    slotIndex: command.slotIndex,
    noteCount: audible.length,
    coverage,
  };
}
