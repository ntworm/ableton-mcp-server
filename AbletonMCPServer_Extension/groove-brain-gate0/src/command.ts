/**
 * What the panel is allowed to ask for.
 *
 * The panel is a page on someone's phone reached over a local network. Its
 * requests index directly into the Live set, so every field is checked at this
 * edge rather than deeper in, where a bad index would already have picked a
 * track.
 */

import { TRANSFORM_AXES, type Transforms } from './transforms.js';

export type CommandOp = 'write' | 'clear';

export interface Command {
  op: CommandOp;
  trackIndex: number;
  slotIndex: number;
  grooveId: string | null;
  transforms: Transforms;
  seed: number;
  replace: boolean;
}

const CODE = 'INVALID_COMMAND';

function wholeNumber(value: unknown, field: string): number {
  if (typeof value !== 'number' || !Number.isInteger(value) || value < 0) {
    throw new Error(`${CODE}:${field}`);
  }
  return value;
}

function parseTransformAxis(axis: string, raw: unknown): number {
  if (!(TRANSFORM_AXES as readonly string[]).includes(axis)) {
    throw new Error(`${CODE}:transforms.${axis}`);
  }
  if (typeof raw !== 'number' || !Number.isFinite(raw) || raw < -1 || raw > 1) {
    throw new Error(`${CODE}:transforms.${axis}`);
  }
  return raw;
}

function parseTransforms(value: unknown): Transforms {
  if (value === undefined) return {};
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`${CODE}:transforms`);
  }
  const out: Transforms = {};
  for (const [axis, raw] of Object.entries(value as Record<string, unknown>)) {
    out[axis as (typeof TRANSFORM_AXES)[number]] = parseTransformAxis(axis, raw);
  }
  return out;
}

function parseOp(value: unknown): CommandOp {
  if (value !== 'write' && value !== 'clear') throw new Error(`${CODE}:op`);
  return value as CommandOp;
}

function parseGrooveId(op: CommandOp, value: unknown): string | null {
  const grooveId: unknown = value ?? null;
  if (op === 'write' && (typeof grooveId !== 'string' || grooveId.length === 0)) {
    throw new Error(`${CODE}:grooveId`);
  }
  if (grooveId !== null && typeof grooveId !== 'string') throw new Error(`${CODE}:grooveId`);
  return grooveId as string | null;
}

function parseSeed(value: unknown): number {
  const seed: unknown = value ?? 0;
  if (typeof seed !== 'number' || !Number.isInteger(seed)) throw new Error(`${CODE}:seed`);
  return seed;
}

export function parseCommand(raw: string): Command {
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    throw new Error(`${CODE}:json`);
  }
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error(`${CODE}:shape`);
  const candidate = value as Record<string, unknown>;

  const op = parseOp(candidate.op);
  const grooveId = parseGrooveId(op, candidate.grooveId);
  const seed = parseSeed(candidate.seed);

  return {
    op,
    trackIndex: wholeNumber(candidate.trackIndex, 'trackIndex'),
    slotIndex: wholeNumber(candidate.slotIndex, 'slotIndex'),
    grooveId: op === 'write' ? (grooveId as string) : null,
    transforms: parseTransforms(candidate.transforms),
    seed,
    // Defaulted false on purpose: a filled slot must never be overwritten
    // because a field was left out.
    replace: candidate.replace === true,
  };
}
