import { initialize, type ActivationContext } from '@ableton-extensions/sdk';
import { performance as nodePerformance } from 'node:perf_hooks';
import { openGate0Modal, releaseGate0Helper, shutdownGate0Modal } from './actions.js';
import { storeReceipt } from './receipt-store.js';
import { resourceRootFromEntryDir } from './resource-path.js';
import { adaptClipSlot } from './sdk-slot-adapter.js';
import { parseGrooveResponse } from './groove-client.js';
import { clipLengthBeats, toClipNotes } from './groove-writer.js';
import type { HelperSession } from './helper-process.js';
import { runSessionClipProbe, type ProbeReceipt } from './session-clip-probe.js';

const COMMAND_ID = 'groove-brain.gate0.open';

interface Lifecycle {
  active: boolean;
  operation: Promise<void> | null;
  registration: Promise<void> | null;
  unregister: (() => Promise<void>) | null;
}

let lifecycle: Lifecycle | null = null;

export function monotonicNow(): number {
  return nodePerformance.now();
}

export function sanitizeErrorMessage(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error);
  return message.replace(/[0-9a-f]{64}/gi, '[redacted]');
}

function escapeHtml(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;');
}

export function receiptModalDataUrl(receipt: ProbeReceipt): string {
  const summary = escapeHtml(JSON.stringify({ ...receipt, receiptSaved: true }, null, 2));
  const html = '<meta charset="utf-8">'
    + '<style>body{font:14px monospace;background:#1d1d1d;color:#eee;padding:24px}'
    + 'pre{white-space:pre-wrap}</style>'
    + `<h1>Gate 0 receipt</h1><pre>${summary}</pre>`;
  return `data:text/html;charset=utf-8,${encodeURIComponent(html)}`;
}

/** How long the panel stays open on the phone before the helper is released. */
const SELECTION_TIMEOUT_MS = 15 * 60 * 1000;
/** Slow enough to be free, fast enough that a tap feels immediate. */
const SELECTION_POLL_MS = 400;

/**
 * Wait for the browser to pick a groove.
 *
 * Returns null when the extension is deactivated or the panel is abandoned:
 * a helper left listening on the LAN because nobody pressed anything is the
 * one outcome this must not produce.
 */
export async function waitForSelection(
  helper: Pick<HelperSession, 'pollSelection'>,
  stillActive: () => boolean,
  nowMs: () => number = Date.now,
  sleep: (ms: number) => Promise<void> = (ms) =>
    new Promise((resolve) => setTimeout(resolve, ms)),
): Promise<string | null> {
  const deadline = nowMs() + SELECTION_TIMEOUT_MS;
  while (stillActive() && nowMs() < deadline) {
    const chosen = await helper.pollSelection();
    if (chosen !== null) return chosen;
    await sleep(SELECTION_POLL_MS);
  }
  return null;
}

function activate(activation: ActivationContext): void {
  if (lifecycle?.active) {
    console.log('[groove-brain-gate0] activate() ignored while already active');
    return;
  }

  const context = initialize(activation, '1.0.0');
  const resourceRoot = resourceRootFromEntryDir(__dirname);
  const state: Lifecycle = {
    active: true,
    operation: null,
    registration: null,
    unregister: null,
  };
  lifecycle = state;

  context.commands.registerCommand(COMMAND_ID, (argument: unknown) => {
    if (!state.active || state.operation) return;
    const operation = (async (): Promise<void> => {
      try {
        const { handle, result, version, helper } = await openGate0Modal(
          context,
          argument,
          resourceRoot,
        );
        if (result.action === 'cancel' || !helper || !state.active) return;

        // Live is usable again from here: the modal is closed and the panel is
        // on the phone. Nothing below opens a window until the clip is written.
        const grooveId = await waitForSelection(helper, () => state.active);
        if (grooveId === null || !state.active) return;
        const groove = parseGrooveResponse(await helper.fetchGroove(grooveId));

        const slot = adaptClipSlot(context, handle);
        const injectFailure = process.env.GROOVE_BRAIN_GATE0_INJECT === 'after_create'
          ? 'after_create' as const
          : undefined;
        const receipt = await runSessionClipProbe(slot, {
          extensionVersion: version,
          nowEpochMs: Date.now,
          nowMonotonicMs: monotonicNow,
          injectFailure,
          notes: toClipNotes(groove),
          lengthBeats: clipLengthBeats(groove),
          // The id, not a path or a digest: enough to find the groove again
          // through search, and nothing about where it came from.
          clipName: `Groove Brain ${groove.id}`,
        });
        storeReceipt(context, receipt);
        if (state.active) {
          await context.ui.showModalDialog(receiptModalDataUrl(receipt), 840, 620);
        }
      } catch (error: unknown) {
        console.error(`[groove-brain-gate0] ${sanitizeErrorMessage(error)}`);
      } finally {
        await releaseGate0Helper();
        state.operation = null;
      }
    })();
    state.operation = operation;
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
