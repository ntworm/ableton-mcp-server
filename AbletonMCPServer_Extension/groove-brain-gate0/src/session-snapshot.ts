/**
 * The Live set as a plain object the panel can render.
 *
 * Read-only by construction: nothing here creates, deletes or modifies. The
 * panel has to know what exists before it can ask for a change, and a reader
 * that could also write would make every render a risk.
 */

export interface SlotState {
  index: number;
  filled: boolean;
  name: string | null;
  /** Null when the clip exists but its notes cannot be read, as for audio. */
  noteCount: number | null;
}

export interface TrackState {
  index: number;
  name: string;
  armed: boolean;
  hasDrumRack: boolean;
  meter: string;
  slots: SlotState[];
}

export interface SessionSnapshot {
  tempo: number;
  tracks: TrackState[];
}

interface ReadableClip {
  name?: string;
  notes?: unknown;
}

interface ReadableSlot {
  clip: ReadableClip | null;
}

interface ReadableTrack {
  name: string;
  arm?: boolean;
  signatureNumerator?: number;
  signatureDenominator?: number;
  devices?: { className?: string; name?: string }[];
  clipSlots?: ReadableSlot[];
}

export interface ReadableSong {
  tempo: number;
  tracks: ReadableTrack[];
}

function readSlot(slot: ReadableSlot, index: number): SlotState {
  const clip = slot.clip;
  if (!clip) return { index, filled: false, name: null, noteCount: 0 };
  let noteCount: number | null = null;
  try {
    const notes = clip.notes;
    if (Array.isArray(notes)) noteCount = notes.length;
  } catch {
    // An audio clip throws here. The slot is still occupied, and reporting it
    // as empty would invite an overwrite the user did not ask for.
    noteCount = null;
  }
  return { index, filled: true, name: clip.name ?? null, noteCount };
}

function readTrack(track: ReadableTrack, index: number): TrackState {
  // Each field is read defensively. Song.tracks holds return and main tracks
  // as well as the ones the user made, and a getter that throws on one of them
  // must not cost the whole snapshot: the panel would show nothing at all.
  const safely = <T>(read: () => T, fallback: T): T => {
    try {
      return read() ?? fallback;
    } catch {
      return fallback;
    }
  };
  return {
    index,
    name: safely(() => track.name, `Track ${index + 1}`),
    armed: safely(() => track.arm, false) === true,
    hasDrumRack: safely(
      () => (track.devices ?? []).some((device) => device.className === 'DrumRack'),
      false,
    ),
    meter: `${safely(() => track.signatureNumerator, 4)}/${safely(() => track.signatureDenominator, 4)}`,
    slots: safely(() => (track.clipSlots ?? []).map(readSlot), []),
  };
}

export function snapshotSession(song: ReadableSong): SessionSnapshot {
  return {
    tempo: song.tempo,
    tracks: song.tracks.map(readTrack),
  };
}
