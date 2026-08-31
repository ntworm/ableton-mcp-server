import { initialize, type ActivationContext } from '@ableton-extensions/sdk';
import { openGate0Modal, shutdownGate0Modal } from './actions.js';
import { resourceRootFromEntryDir } from './resource-path.js';

const COMMAND_ID = 'groove-brain.gate0.open';

interface Lifecycle {
  active: boolean;
  registration: Promise<void> | null;
  unregister: (() => Promise<void>) | null;
}

let lifecycle: Lifecycle | null = null;

export function sanitizeErrorMessage(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error);
  return message.replace(/[0-9a-f]{64}/gi, '[redacted]');
}

function activate(activation: ActivationContext): void {
  if (lifecycle?.active) {
    console.log('[groove-brain-gate0] activate() ignored while already active');
    return;
  }

  const context = initialize(activation, '1.0.0');
  const resourceRoot = resourceRootFromEntryDir(__dirname);
  const state: Lifecycle = { active: true, registration: null, unregister: null };
  lifecycle = state;

  context.commands.registerCommand(COMMAND_ID, (argument: unknown) => {
    if (!state.active) return;
    void openGate0Modal(context, argument, resourceRoot)
      .then(({ result }) => {
        console.log(`[groove-brain-gate0] modal result: ${result.action}`);
      })
      .catch((error: unknown) => {
        console.error(`[groove-brain-gate0] ${sanitizeErrorMessage(error)}`);
      });
  });

  state.registration = context.ui
    .registerContextMenuAction('ClipSlot', 'Open Groove Brain Gate 0', COMMAND_ID)
    .then(async (unregister) => {
      if (!state.active) {
        await unregister();
        return;
      }
      state.unregister = unregister;
    })
    .catch((error: unknown) => {
      console.error(
        `[groove-brain-gate0] context action registration failed: ${sanitizeErrorMessage(error)}`,
      );
    });
}

function deactivate(): void {
  const state = lifecycle;
  if (!state?.active) return;
  state.active = false;
  if (lifecycle === state) lifecycle = null;

  void (async () => {
    await shutdownGate0Modal();
    await state.registration;
    const unregister = state.unregister;
    state.unregister = null;
    if (unregister) await unregister();
  })().catch((error: unknown) => {
    console.error(`[groove-brain-gate0] deactivate failed: ${sanitizeErrorMessage(error)}`);
  });
}

export { activate, deactivate };
