/**
 * What the loaded kit will actually play.
 *
 * SD3 marks an articulation "(not loaded)" when the mapping exists but the kit
 * has no sample behind it. Such a note is not a wrong drum, it is no drum, and
 * a measurement made against a note map alone cannot see it: reading the same
 * settings page with two kits loaded gives two different answers, with no edit
 * by the user. Everything written to Live passes through here first.
 */

export interface ProfileNote {
  name: string;
  piece: string;
  /** True plays, false is mapped but silent, null was never observed. */
  loaded: boolean | null;
  openness?: number;
  zone?: string;
}

export interface KitProfile {
  kit: string;
  notes: Record<string, ProfileNote>;
}

export type Resolution =
  | { status: 'plays'; pitch: number }
  | { status: 'substituted'; pitch: number }
  | { status: 'silent'; pitch: null }
  | { status: 'unknown'; pitch: number };

export function resolveNote(profile: KitProfile, pitch: number): Resolution {
  const entry = profile.notes[String(pitch)];
  if (!entry || entry.loaded === null) return { status: 'unknown', pitch };
  if (entry.loaded) return { status: 'plays', pitch };

  // Nearest playable relative: the same piece, and for a hi-hat the closest
  // openness, because openness is what the part is made of while the strike
  // zone is a colour on top of it.
  let best: { pitch: number; distance: number } | null = null;
  for (const [key, candidate] of Object.entries(profile.notes)) {
    if (candidate.loaded !== true || candidate.piece !== entry.piece) continue;
    const distance = entry.openness !== undefined && candidate.openness !== undefined
      ? Math.abs(entry.openness - candidate.openness)
      : Number.POSITIVE_INFINITY;
    if (best === null || distance < best.distance) best = { pitch: Number(key), distance };
  }
  if (best === null || !Number.isFinite(best.distance)) return { status: 'silent', pitch: null };
  return { status: 'substituted', pitch: best.pitch };
}

export interface Coverage {
  plays: number;
  substituted: number;
  silent: number;
  unknown: number;
}

export function summariseCoverage(profile: KitProfile, pitches: number[]): Coverage {
  const summary: Coverage = { plays: 0, substituted: 0, silent: 0, unknown: 0 };
  for (const pitch of pitches) summary[resolveNote(profile, pitch).status] += 1;
  return summary;
}
