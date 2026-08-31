import type { ExtensionContext, Handle } from '@ableton-extensions/sdk';
import { HelperSession } from './helper-process.js';
import { parseModalResult, type ModalResult } from './protocol.js';

interface ActiveInvocation {
  cancelled: boolean;
  helper: HelperSession | null;
  start: Promise<HelperSession>;
}

let activeInvocation: ActiveInvocation | null = null;

function isHandle(value: unknown): value is Handle {
  return Boolean(value)
    && typeof value === 'object'
    && typeof (value as { id?: unknown }).id === 'bigint';
}

export async function openGate0Modal(
  context: ExtensionContext<'1.0.0'>,
  argument: unknown,
  resourceRoot: string,
): Promise<{ handle: Handle; result: ModalResult; version: string }> {
  if (!isHandle(argument)) throw new Error('CLIP_SLOT_HANDLE_REQUIRED');
  if (activeInvocation) throw new Error('GATE0_INVOCATION_ALREADY_ACTIVE');

  const invocation: ActiveInvocation = {
    cancelled: false,
    helper: null,
    start: HelperSession.start(resourceRoot),
  };
  activeInvocation = invocation;

  try {
    const helper = await invocation.start;
    invocation.helper = helper;
    if (invocation.cancelled) throw new Error('GATE0_INVOCATION_CANCELLED');
    await helper.assertHealthy();
    if (invocation.cancelled) throw new Error('GATE0_INVOCATION_CANCELLED');
    const raw = await context.ui.showModalDialog(helper.modalUrl, 960, 680);
    if (invocation.cancelled) throw new Error('GATE0_INVOCATION_CANCELLED');
    return {
      handle: argument,
      result: parseModalResult(raw),
      version: helper.extensionVersion,
    };
  } finally {
    try {
      const helper = invocation.helper ?? await invocation.start.catch(() => null);
      if (helper) await helper.stop();
    } finally {
      if (activeInvocation === invocation) activeInvocation = null;
    }
  }
}

export async function shutdownGate0Modal(): Promise<void> {
  const invocation = activeInvocation;
  if (!invocation) return;
  invocation.cancelled = true;
  const helper = invocation.helper ?? await invocation.start.catch(() => null);
  if (helper) await helper.stop();
}
