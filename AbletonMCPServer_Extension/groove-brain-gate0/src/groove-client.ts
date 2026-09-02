/**
 * Parsing for the two helper endpoints.
 *
 * The helper is local and authenticated, but its output still goes straight
 * into Live, so a malformed field is refused here rather than written as NaN.
 */

import type { ExportedGroove } from './groove-writer.js';

export interface SearchHit {
  id: string;
  genre: string[];
  bpm: string[];
  kit: string[];
  bars: number;
  meter: string;
  noteCount: number;
}

export interface SearchResponse {
  total: number;
  items: SearchHit[];
}

function object(raw: string, code: string): Record<string, unknown> {
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    throw new Error(code);
  }
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error(code);
  return value as Record<string, unknown>;
}

function strings(value: unknown, code: string): string[] {
  if (!Array.isArray(value) || value.some((item) => typeof item !== 'string')) {
    throw new Error(code);
  }
  return value as string[];
}

export function parseSearchResponse(raw: string): SearchResponse {
  const code = 'INVALID_SEARCH_RESPONSE';
  const candidate = object(raw, code);
  if (typeof candidate.total !== 'number' || !Array.isArray(candidate.items)) throw new Error(code);
  const items = candidate.items.map((entry) => {
    if (!entry || typeof entry !== 'object') throw new Error(code);
    const hit = entry as Record<string, unknown>;
    if (
      typeof hit.id !== 'string'
      || typeof hit.bars !== 'number'
      || typeof hit.meter !== 'string'
      || typeof hit.note_count !== 'number'
    ) {
      throw new Error(code);
    }
    return {
      id: hit.id,
      genre: strings(hit.genre, code),
      bpm: strings(hit.bpm, code),
      kit: strings(hit.kit, code),
      bars: hit.bars,
      meter: hit.meter,
      noteCount: hit.note_count,
    };
  });
  return { total: candidate.total, items };
}

export function parseGrooveResponse(raw: string): ExportedGroove {
  const code = 'INVALID_GROOVE_RESPONSE';
  const candidate = object(raw, code);
  if (
    typeof candidate.id !== 'string'
    || typeof candidate.bars !== 'number'
    || typeof candidate.meter !== 'string'
    || typeof candidate.ppq !== 'number'
    || !Array.isArray(candidate.notes)
  ) {
    throw new Error(code);
  }
  const notes = candidate.notes.map((note) => {
    if (!Array.isArray(note) || note.length !== 4 || note.some((n) => typeof n !== 'number')) {
      throw new Error(code);
    }
    return note as [number, number, number, number];
  });
  return {
    id: candidate.id,
    bars: candidate.bars,
    meter: candidate.meter,
    ppq: candidate.ppq,
    notes,
  };
}
