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

function audibleNotes(profile: KitProfile, notes: ClipNote[]): ClipNote[] {
  const audible: ClipNote[] = [];
  for (const note of notes) {
    const resolved = resolveNote(profile, note.pitch);
    if (resolved.status === 'silent') continue;
    audible.push({ ...note, pitch: resolved.pitch });
  }
  return audible;
}

async function clearSlot(
  slot: WritableSlot,
  command: Command,
  trackName: string,
): Promise<Receipt> {
  if (!slot.clip) return refuse('SLOT_ALREADY_EMPTY', command, trackName);
  await slot.deleteClip();
  return { status: 'ok', code: 'CLEARED', trackName, slotIndex: command.slotIndex, noteCount: 0 };
}

async function writeSlot(
  slot: WritableSlot,
  command: Command,
  audible: ClipNote[],
  lengthBeats: number,
  trackName: string,
): Promise<Receipt> {
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
    trackName,
    slotIndex: command.slotIndex,
    noteCount: audible.length,
  };
}

function slotAt(track: WritableTrack | undefined, index: number): WritableSlot | undefined {
  return track?.clipSlots?.[index];
}

function trackName(track: WritableTrack | undefined): string | null {
  return track?.name ?? null;
}

export async function applyCommand(
  song: WritableSong,
  command: Command,
  notes: ClipNote[],
  lengthBeats: number,
  profile: KitProfile,
): Promise<Receipt> {
  const track = song.tracks[command.trackIndex];
  const slot = slotAt(track, command.slotIndex);
  if (!track || !slot) return refuse('INDEX_OUT_OF_RANGE', command, trackName(track));

  if (command.op === 'clear') {
    return clearSlot(slot, command, track.name);
  }

  if (slot.clip && !command.replace) return refuse('SLOT_NOT_EMPTY', command, track.name);

  // Resolved before anything is created. A note the kit cannot play is dropped
  // rather than written: an inaudible note in the clip is one the user will
  // move around wondering why it makes no sound.
  const coverage = summariseCoverage(profile, notes.map((note) => note.pitch));
  const audible = audibleNotes(profile, notes);
  if (audible.length === 0) {
    return { ...refuse('NOTHING_AUDIBLE', command, track.name), coverage };
  }

  return { ...(await writeSlot(slot, command, audible, lengthBeats, track.name)), coverage };
}
