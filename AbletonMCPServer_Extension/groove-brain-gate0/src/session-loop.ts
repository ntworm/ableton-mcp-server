/**
 * The loop that runs while the panel is on the phone.
 *
 * Publish what the set looks like, take whatever the panel asked for, apply it,
 * publish again. Live is usable throughout: nothing here opens a window.
 *
 * Gate 2 let a single failed request fall through to the `finally` that stopped
 * the helper, so one transient error killed the session and the page died with
 * a refused connection. Failures are counted instead, and only a run of them
 * gives up.
 */

import { parseCommand } from './command.js';
import { parseGrooveResponse } from './groove-client.js';
import { clipLengthBeats, toClipNotes } from './groove-writer.js';
import type { KitProfile } from './kit-profile.js';
import { snapshotSession, type ReadableSong } from './session-snapshot.js';
import { applyCommand, type Receipt, type WritableSong } from './session-writer.js';
import { applyTransforms } from './transforms.js';

/** How long the panel may stay open before the helper is released. */
export const SESSION_TIMEOUT_MS = 30 * 60 * 1000;
/** Slow enough to be free, fast enough that a tap feels immediate. */
export const POLL_MS = 400;
/** One bad request is the network; several in a row is a dead helper. */
export const MAX_CONSECUTIVE_FAILURES = 8;

export interface SessionHelper {
  publishSnapshot(snapshot: unknown): Promise<void>;
  takeCommand(): Promise<string | null>;
  fetchGroove(id: string): Promise<string>;
}

export interface SessionDeps {
  helper: SessionHelper;
  song: ReadableSong & WritableSong;
  profile: KitProfile;
  stillActive: () => boolean;
  onReceipt?: (receipt: Receipt) => void;
  nowMs?: () => number;
  sleep?: (ms: number) => Promise<void>;
}

export async function serveSession(deps: SessionDeps): Promise<void> {
  const {
    helper, song, profile, stillActive, onReceipt,
    nowMs = Date.now,
    sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms)),
  } = deps;

  const deadline = nowMs() + SESSION_TIMEOUT_MS;
  let failures = 0;
  let published = '';

  while (stillActive() && nowMs() < deadline && failures < MAX_CONSECUTIVE_FAILURES) {
    try {
      // Republished only when it changed. The panel polls on its own clock and
      // a snapshot that is identical is noise on the wire.
      const snapshot = snapshotSession(song);
      const serialised = JSON.stringify(snapshot);
      if (serialised !== published) {
        await helper.publishSnapshot(snapshot);
        published = serialised;
      }

      const raw = await helper.takeCommand();
      failures = 0;
      if (raw === null) {
        await sleep(POLL_MS);
        continue;
      }

      const command = parseCommand(raw);
      let notes: ReturnType<typeof toClipNotes> = [];
      let lengthBeats = 0;
      if (command.op === 'write' && command.grooveId) {
        const groove = parseGrooveResponse(await helper.fetchGroove(command.grooveId));
        notes = applyTransforms(toClipNotes(groove), command.transforms, command.seed);
        lengthBeats = clipLengthBeats(groove);
      }
      const receipt = await applyCommand(song, command, notes, lengthBeats, profile);
      onReceipt?.(receipt);
      // Forces a republish on the next turn so the panel sees the new clip.
      published = '';
    } catch {
      // A command that cannot be parsed or applied must not end the session:
      // the user is holding the panel and would see it die for one bad tap.
      failures += 1;
      await sleep(POLL_MS);
    }
  }
}
