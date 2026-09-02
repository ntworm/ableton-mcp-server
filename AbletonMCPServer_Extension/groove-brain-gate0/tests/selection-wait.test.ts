import assert from 'node:assert/strict';
import { test } from 'node:test';
import { waitForSelection } from '../src/extension.js';

function fakeClock() {
  let now = 0;
  return {
    nowMs: () => now,
    sleep: async (ms: number) => { now += ms; },
  };
}

test('the wait returns the first groove the phone picks', async () => {
  const clock = fakeClock();
  const answers = [null, null, 'a1'];
  const helper = { pollSelection: async () => answers.shift() ?? null };
  assert.equal(await waitForSelection(helper, () => true, clock.nowMs, clock.sleep), 'a1');
});

test('deactivating the extension stops the wait', async () => {
  // Live closing or the extension unloading must not leave a helper listening
  // on the LAN with nobody to collect from it.
  const clock = fakeClock();
  let active = true;
  const helper = {
    pollSelection: async () => {
      active = false;
      return null;
    },
  };
  assert.equal(await waitForSelection(helper, () => active, clock.nowMs, clock.sleep), null);
});

test('an abandoned panel times out instead of waiting forever', async () => {
  const clock = fakeClock();
  const helper = { pollSelection: async () => null };
  assert.equal(await waitForSelection(helper, () => true, clock.nowMs, clock.sleep), null);
  // The clock only advances through the injected sleep, so reaching the end
  // proves the loop is bounded rather than merely slow.
  assert.ok(clock.nowMs() >= 15 * 60 * 1000);
});
