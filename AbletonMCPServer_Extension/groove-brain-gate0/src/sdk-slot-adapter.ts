import {
  ClipSlot,
  type ExtensionContext,
  type Handle,
  type MidiClip,
  type NoteDescription,
} from '@ableton-extensions/sdk';
import type { ClipPort, Gate0Note, SlotPort } from './session-clip-probe.js';

function adaptNotes(notes: NoteDescription[]): Gate0Note[] {
  return notes.map((note) => ({
    pitch: note.pitch,
    startTime: note.startTime,
    duration: note.duration,
    velocity: note.velocity ?? 100,
  }));
}

function adaptClip(clip: MidiClip<'1.0.0'>): ClipPort {
  return {
    handleId: clip.handle.id.toString(),
    get name() {
      return clip.name;
    },
    set name(value: string) {
      clip.name = value;
    },
    get notes() {
      return adaptNotes(clip.notes);
    },
    set notes(value: Gate0Note[]) {
      clip.notes = value;
    },
  };
}

export function adaptClipSlot(
  context: ExtensionContext<'1.0.0'>,
  handle: Handle,
): SlotPort {
  const slot = context.getObjectFromHandle(handle, ClipSlot);
  return {
    handleId: slot.handle.id.toString(),
    getClip: () => {
      const clip = slot.clip;
      if (!clip) return null;
      return { handleId: clip.handle.id.toString() };
    },
    createMidiClip: async (lengthBeats: number) => {
      const created = await slot.createMidiClip(lengthBeats);
      return adaptClip(created);
    },
  };
}
