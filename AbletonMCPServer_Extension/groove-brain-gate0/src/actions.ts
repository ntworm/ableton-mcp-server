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
): Promise<{ handle: Handle; result: ModalResult; version: string; helper: HelperSession | null }> {
  if (!isHandle(argument)) throw new Error('CLIP_SLOT_HANDLE_REQUIRED');
  if (activeInvocation) throw new Error('GATE0_INVOCATION_ALREADY_ACTIVE');

  const invocation: ActiveInvocation = {
    cancelled: false,
    helper: null,
    start: HelperSession.start(resourceRoot),
  };
  activeInvocation = invocation;

  // On a handoff the helper outlives the modal: the panel is now on a phone,
  // and stopping it here would close the page the user just opened. Ownership
  // passes to the caller, which must call releaseGate0Helper when it is done.
  // Every other path, including a throw, releases it here.
  let handedOff = false;
  try {
    const helper = await invocation.start;
    invocation.helper = helper;
    if (invocation.cancelled) throw new Error('GATE0_INVOCATION_CANCELLED');
    await helper.assertHealthy();
    if (invocation.cancelled) throw new Error('GATE0_INVOCATION_CANCELLED');
    const raw = await context.ui.showModalDialog(helper.modalUrl, 720, 760);
    if (invocation.cancelled) throw new Error('GATE0_INVOCATION_CANCELLED');
    const result = parseModalResult(raw);
    handedOff = result.action === 'handoff';
    return {
      handle: argument,
      result,
      version: helper.extensionVersion,
      helper: handedOff ? helper : null,
    };
  } finally {
    if (!handedOff) await releaseGate0Helper();
  }
}

/** Stop the helper and free the invocation. Safe to call more than once. */
export async function releaseGate0Helper(): Promise<void> {
  const invocation = activeInvocation;
  if (!invocation) return;
  activeInvocation = null;
  const helper = invocation.helper ?? await invocation.start.catch(() => null);
  if (helper) await helper.stop();
}

export async function shutdownGate0Modal(): Promise<void> {
  const invocation = activeInvocation;
  if (!invocation) return;
  invocation.cancelled = true;
  const helper = invocation.helper ?? await invocation.start.catch(() => null);
  if (helper) await helper.stop();
}
