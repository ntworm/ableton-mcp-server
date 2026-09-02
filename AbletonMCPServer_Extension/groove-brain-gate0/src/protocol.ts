export const GATE0_PROTOCOL = 1 as const;

export interface HelperReady {
  type: 'ready';
  protocol: 1;
  host: '127.0.0.1';
  port: number;
  parent_pid: number;
}

export type ModalResult =
  | { action: 'cancel'; confirmed: false; protocol: 1 }
  | { action: 'insert_groove'; confirmed: true; protocol: 1; grooveId: string };

function parseObject(raw: string, code: string): Record<string, unknown> {
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    throw new Error(code);
  }
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(code);
  }
  return value as Record<string, unknown>;
}

export function parseHelperReady(raw: string, expectedParentPid: number): HelperReady {
  const candidate = parseObject(raw, 'INVALID_READY');
  if (
    candidate.type !== 'ready'
    || candidate.protocol !== GATE0_PROTOCOL
    || candidate.host !== '127.0.0.1'
    || !Number.isInteger(candidate.port)
    || Number(candidate.port) < 1
    || Number(candidate.port) > 65_535
    || candidate.parent_pid !== expectedParentPid
  ) {
    throw new Error('INVALID_READY');
  }
  return candidate as unknown as HelperReady;
}

export function parseModalResult(raw: string): ModalResult {
  const candidate = parseObject(raw, 'INVALID_MODAL_RESULT');
  if (candidate.protocol !== GATE0_PROTOCOL) {
    throw new Error('INVALID_MODAL_PROTOCOL');
  }
  if (candidate.action === 'cancel' && candidate.confirmed === false) {
    return candidate as unknown as ModalResult;
  }
  if (
    candidate.action === 'insert_groove'
    && candidate.confirmed === true
    && typeof candidate.groove_id === 'string'
    && candidate.groove_id.length > 0
  ) {
    // Rebuilt rather than cast: the panel sends snake_case and an id is the one
    // field the extension cannot fall back on, so an absent one is a refusal.
    return {
      action: 'insert_groove',
      confirmed: true,
      protocol: GATE0_PROTOCOL,
      grooveId: candidate.groove_id,
    };
  }
  throw new Error('INVALID_MODAL_RESULT');
}
