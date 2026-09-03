/**
 * The seven deterministic transform axes, in beats.
 *
 * Ported from `groove_intelligence/deterministic.py`, which is the reference.
 * The order the axes are applied in is part of the result, so it is preserved
 * here rather than reordered for readability.
 *
 * One honest difference: the Python side draws from `random.Random(seed)`, and
 * no JavaScript generator reproduces that sequence. A negative density picks a
 * different subset here than it would there. Both are deterministic for a given
 * seed; they are not bit-identical to each other, and this says so rather than
 * implying a parity that does not exist.
 */

export interface ClipNote {
  pitch: number;
  startTime: number;
  duration: number;
  velocity: number;
}

export const TRANSFORM_AXES = [
  'density',
  'syncopation',
  'swing',
  'microtiming',
  'energy',
  'complexity',
  'polyrhythm',
] as const;

export type TransformAxis = (typeof TRANSFORM_AXES)[number];
export type Transforms = Partial<Record<TransformAxis, number>>;

/** Above this a note reads as an accent rather than a ghost or a filler hit. */
const ACCENT_VELOCITY = 80;
/** A thirty-second note: shorter and Live renders nothing visible. */
const MIN_DURATION_BEATS = 0.125;

/** Seeded and independent of the host's Math.random, which would break replay. */
function mulberry32(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function clampVelocity(value: number): number {
  return Math.max(1, Math.min(127, Math.round(value)));
}

function validate(transforms: Transforms): void {
  for (const [axis, value] of Object.entries(transforms)) {
    if (!(TRANSFORM_AXES as readonly string[]).includes(axis)) {
      throw new Error(`UNKNOWN_TRANSFORM_AXIS:${axis}`);
    }
    if (typeof value !== 'number' || !Number.isFinite(value) || value < -1 || value > 1) {
      throw new Error(`TRANSFORM_OUT_OF_RANGE:${axis}`);
    }
  }
}

export function applyTransforms(
  notes: ClipNote[],
  transforms: Transforms,
  seed: number,
  beatsPerBar = 4,
): ClipNote[] {
  validate(transforms);
  const random = mulberry32(seed);
  let result = notes.map((note) => ({ ...note }));
  if (result.length === 0) return result;

  // A deliberate divergence from the Python reference, which nudges velocity
  // from the seed unconditionally. There, every call is generating a derived
  // artifact; here, all knobs at zero means "insert this performance", and
  // preserving velocity and microtiming untouched is an explicit product goal.
  const touched = TRANSFORM_AXES.some((axis) => (transforms[axis] ?? 0) !== 0);
  if (!touched) return result;

  // With any knob turned, the seed also nudges velocity, so two seeds never
  // produce the same clip from the same source.
  const seedVariation = (seed % 5) - 2;
  if (seedVariation !== 0) {
    result = result.map((n) => ({ ...n, velocity: clampVelocity(n.velocity + seedVariation) }));
  }

  const density = transforms.density ?? 0;
  if (density > 0) {
    const extra = Math.max(1, Math.round(result.length * 0.5 * density));
    const source = [...result];
    for (let index = 0; index < extra; index += 1) {
      const from = source[index % source.length];
      result.push({
        ...from,
        velocity: clampVelocity(from.velocity - 1),
        startTime: from.startTime + 0.125 * (index + 1),
      });
    }
  } else if (density < 0 && result.length > 1) {
    const keep = Math.max(1, Math.round(result.length * (1 + density * 0.5)));
    result = result
      .map((note, order) => ({ note, order, roll: random() }))
      .sort((a, b) => a.roll - b.roll || a.order - b.order)
      .slice(0, keep)
      .sort((a, b) => a.order - b.order)
      .map((entry) => entry.note);
  }
  if (density < 0) {
    // A one-hit groove has nothing to remove, so density stays observable by
    // shortening instead. Positive density already changed the note count.
    result = result.map((note) => {
      const duration = Math.max(MIN_DURATION_BEATS, note.duration * (1 + density * 0.25));
      return {
        ...note,
        duration,
        velocity: duration === note.duration ? clampVelocity(note.velocity - 1) : note.velocity,
      };
    });
  }

  const energy = transforms.energy ?? 0;
  if (energy !== 0) {
    const delta = Math.max(1, Math.round(Math.abs(energy) * 16));
    const direction = energy > 0 ? 1 : -1;
    result = result.map((note) => {
      const wanted = note.velocity + direction * delta;
      const velocity = wanted < 1 || wanted > 127 ? note.velocity - direction * delta : wanted;
      return { ...note, velocity: clampVelocity(velocity) };
    });
  }

  const microtiming = transforms.microtiming ?? 0;
  if (microtiming !== 0) {
    const amount = Math.max(1 / 128, Math.abs(microtiming) / 32);
    const direction = microtiming > 0 ? 1 : -1;
    result = result.map((note) => ({
      ...note,
      startTime: Math.max(0, note.startTime + amount * direction),
    }));
  }

  const swing = transforms.swing ?? 0;
  if (swing !== 0) {
    const amount = Math.max(1 / 128, Math.abs(swing) / 16);
    const direction = swing > 0 ? 1 : -1;
    result = result.map((note) => {
      // Off-beat eighths move; downbeats hold, which is what makes it swing
      // rather than shift the whole part.
      const offBeat = Math.floor(note.startTime / 0.5) % 2 !== 0;
      const moves = offBeat || (note.startTime === 0 && direction > 0);
      return {
        ...note,
        startTime: moves ? Math.max(0, note.startTime + amount * direction) : note.startTime,
      };
    });
  }

  const syncopation = transforms.syncopation ?? 0;
  if (syncopation !== 0) {
    const amount = Math.max(1 / 128, Math.abs(syncopation) / 8);
    const direction = syncopation > 0 ? 1 : -1;
    result = result.map((note) => {
      const onBar = note.startTime % beatsPerBar === 0;
      return {
        ...note,
        startTime: onBar ? Math.max(0, note.startTime + amount * direction) : note.startTime,
      };
    });
  }

  const polyrhythm = transforms.polyrhythm ?? 0;
  if (polyrhythm !== 0) {
    // A 3-over-4 feel: accents move onto the triplet grid while the rest hold
    // the straight one, which is what makes both grids audible at once.
    const shift = (1 / 3) * (polyrhythm > 0 ? 1 : -1);
    const polyRandom = mulberry32(seed ^ 0x504f4c59);
    result = result.map((note) => ({
      ...note,
      startTime:
        note.velocity > ACCENT_VELOCITY && polyRandom() < Math.abs(polyrhythm)
          ? Math.max(0, note.startTime + shift)
          : note.startTime,
    }));
  }

  const complexity = transforms.complexity ?? 0;
  if (complexity !== 0) {
    const step = complexity > 0 ? 1 : -1;
    const durationDelta = Math.max(1 / 128, Math.abs(complexity) / 16);
    result = result.map((note) => {
      const shifted = note.pitch + step;
      return {
        ...note,
        pitch: shifted > 0 && shifted < 127 ? shifted : note.pitch - step,
        duration: Math.max(MIN_DURATION_BEATS, note.duration + durationDelta * step),
      };
    });
  }

  return result;
}
