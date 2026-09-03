import { initialize, type ActivationContext } from '@ableton-extensions/sdk';
import fs from 'node:fs';
import nodePath from 'node:path';
import { performance as nodePerformance } from 'node:perf_hooks';
import { openGate0Modal, releaseGate0Helper, shutdownGate0Modal } from './actions.js';
import { resourceRootFromEntryDir } from './resource-path.js';
import type { KitProfile } from './kit-profile.js';
import { serveSession } from './session-loop.js';
import type { ProbeReceipt } from './session-clip-probe.js';

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

/**
 * The kit profile bundled with the package.
 *
 * Keyed by kit rather than by plugin: the same settings page read with two kits
 * loaded gives two different maps, with no edit by the user. A profile for the
 * kit actually loaded is future work; this is the one that was measured.
 */
function loadKitProfile(resourceRoot: string): KitProfile {
  const path = nodePath.join(resourceRoot, 'data', 'kit-profile.json');
  return JSON.parse(fs.readFileSync(path, 'utf8')) as KitProfile;
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
        const { result, helper } = await openGate0Modal(
          context,
          argument,
          resourceRoot,
        );
        if (result.action === 'cancel' || !helper || !state.active) return;

        // Live is usable from here: the modal is closed and the panel is on the
        // phone. Nothing below opens a window.
        await serveSession({
          helper,
          song: context.application.song as never,
          profile: loadKitProfile(resourceRoot),
          stillActive: () => state.active,
          onReceipt: (receipt) => {
            console.log(`[groove-brain] ${receipt.status} ${receipt.code} `
              + `${receipt.trackName ?? '?'} slot ${receipt.slotIndex + 1} `
              + `${receipt.noteCount} notas`);
          },
        });
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
