import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import vm from 'node:vm';

type Handler = () => void;

class FakeNode {
  className = '';
  disabled = false;
  hidden = false;
  innerHTML = '';
  textContent = '';
  value = '';
  children: FakeNode[] = [];
  private readonly handlers = new Map<string, Handler>();

  addEventListener(name: string, handler: Handler): void {
    this.handlers.set(name, handler);
  }

  dispatch(name: string): void {
    const handler = this.handlers.get(name);
    if (!handler) throw new Error(`MISSING_HANDLER:${name}`);
    handler();
  }

  replaceChildren(): void {
    this.children = [];
  }

  append(node: FakeNode): void {
    this.children.push(node);
  }
}

const SEARCH_PAYLOAD = {
  total: 103,
  returned: 2,
  items: [
    { id: 'a1', genre: ['metal'], bpm: ['bpm_140_159'], kit: ['kick'], bars: 4, meter: '4/4', note_count: 12 },
    { id: 'b2', genre: ['metal'], bpm: ['bpm_140_159'], kit: ['snare'], bars: 2, meter: '4/4', note_count: 8 },
  ],
};

const PANEL_PAYLOAD = {
  url: 'http://192.168.1.40:45123/picker.html#' + 'a'.repeat(64),
  qr: '<svg role="img"></svg>',
};

interface Harness {
  nodes: Record<string, FakeNode>;
  messages: unknown[];
  requests: { path: string; body: unknown }[];
}

async function runPage(
  file: string,
  selectors: string[],
  options: { bridgeThrows?: boolean; searchStatus?: number; emptySearch?: boolean } = {},
): Promise<Harness> {
  const nodes: Record<string, FakeNode> = {};
  const bySelector = new Map<string, FakeNode>();
  for (const name of selectors) {
    const node = new FakeNode();
    nodes[name] = node;
    bySelector.set(`#${name}`, node);
  }
  nodes.controls.hidden = true;

  const messages: unknown[] = [];
  const requests: { path: string; body: unknown }[] = [];
  const token = 'a'.repeat(64);
  const source = fs.readFileSync(path.resolve(`groove-brain-gate0/ui/${file}`), 'utf8');
  const context = vm.createContext({
    AbortSignal,
    Error,
    JSON,
    Math,
    String,
    setTimeout,
    // A no-op: the panel's refresh loop would otherwise hold the test
    // process open, and nothing here depends on it firing.
    setInterval: () => 0,
    document: {
      querySelector(selector: string) {
        const node = bySelector.get(selector);
        if (!node) throw new Error(`UNKNOWN_SELECTOR:${selector}`);
        return node;
      },
      createElement() {
        return new FakeNode();
      },
    },
    fetch: async (target: string, init: { body?: string }) => {
      requests.push({ path: target, body: init.body ? JSON.parse(init.body) : undefined });
      if (target === '/api/health') {
        return { ok: true, status: 200, async json() { return { status: 'ok', protocol: 1 }; } };
      }
      if (target === '/api/panel') {
        return { ok: true, status: 200, async json() { return PANEL_PAYLOAD; } };
      }
      if (target === '/api/snapshot') {
        return { ok: true, status: 200, async json() { return SNAPSHOT; } };
      }
      if (target === '/api/command') {
        return { ok: true, status: 200, async json() { return { status: 'queued' }; } };
      }
      const status = options.searchStatus ?? 200;
      const payload = options.emptySearch ? { total: 0, returned: 0, items: [] } : SEARCH_PAYLOAD;
      return { ok: status === 200, status, async json() { return payload; } };
    },
    history: { replaceState() {} },
    window: {
      chrome: {
        webview: {
          postMessage(message: unknown) {
            if (options.bridgeThrows) throw new Error('BRIDGE_FAILED');
            messages.push(message);
          },
        },
      },
      location: { hash: `#${token}`, pathname: '/' },
    },
  });
  vm.runInContext(source, context, { filename: file });
  await settle();
  return { nodes, messages, requests };
}

async function settle(): Promise<void> {
  for (let index = 0; index < 4; index += 1) {
    await new Promise((resolve) => setImmediate(resolve));
  }
}

const HANDOFF_NODES = ['status', 'controls', 'error', 'qr', 'url', 'done', 'cancel'];
const PICKER_NODES = [
  'status', 'controls', 'error', 'tempo', 'tracks', 'slotsBlock', 'slots',
  'genre', 'bpm', 'surprise', 'chosen', 'knobs', 'write', 'receipt',
];

const SNAPSHOT = {
  tempo: 128,
  tracks: [
    {
      index: 0, name: 'Superior Drummer 3', armed: true, hasDrumRack: true, meter: '4/4',
      slots: [
        { index: 0, filled: false, name: null, noteCount: 0 },
        { index: 1, filled: true, name: 'Verse', noteCount: 34 },
      ],
    },
    { index: 1, name: 'Bass', armed: false, hasDrumRack: false, meter: '4/4', slots: [] },
  ],
};

test('the handoff page shows the QR and the URL for the phone', async () => {
  const { nodes } = await runPage('app.js', HANDOFF_NODES);
  assert.equal(nodes.controls.hidden, false);
  assert.match(nodes.qr.innerHTML, /<svg/u);
  assert.equal(nodes.url.textContent, PANEL_PAYLOAD.url);
});

test('closing the handoff frees Live without carrying a groove', async () => {
  // The whole point of the change: the modal closes so the user can keep
  // working, and the choice arrives later from the phone.
  const { nodes, messages } = await runPage('app.js', HANDOFF_NODES);
  nodes.done.dispatch('click');
  nodes.done.dispatch('click');

  assert.equal(messages.length, 1);
  const payload = JSON.parse((messages[0] as { params: string[] }).params[0]);
  assert.deepEqual(payload, { action: 'handoff', confirmed: true, protocol: 1 });
});

test('cancelling the handoff sends a cancel', async () => {
  const { nodes, messages } = await runPage('app.js', HANDOFF_NODES);
  nodes.cancel.dispatch('click');
  const payload = JSON.parse((messages[0] as { params: string[] }).params[0]);
  assert.deepEqual(payload, { action: 'cancel', confirmed: false, protocol: 1 });
});

test('a bridge failure on the handoff page is visible and terminal', async () => {
  const { nodes } = await runPage('app.js', HANDOFF_NODES, { bridgeThrows: true });
  nodes.cancel.dispatch('click');
  assert.equal(nodes.status.textContent, 'Falha no Groove Brain.');
  assert.equal(nodes.error.textContent, 'BRIDGE_FAILED');
  assert.equal(nodes.controls.hidden, true);
});

test('the panel lists the tracks in the session', async () => {
  const { nodes } = await runPage('picker.js', PICKER_NODES);
  assert.equal(nodes.controls.hidden, false);
  assert.equal(nodes.tracks.children.length, 2);
  assert.match(nodes.tempo.textContent, /128 BPM/u);
  assert.match(nodes.tracks.children[0].textContent, /Superior Drummer 3/u);
});

test('slots appear only once a track is chosen', async () => {
  const { nodes } = await runPage('picker.js', PICKER_NODES);
  assert.equal(nodes.slotsBlock.hidden, true);

  nodes.tracks.children[0].dispatch('click');
  assert.equal(nodes.slotsBlock.hidden, false);
  assert.equal(nodes.slots.children.length, 2);
  assert.match(nodes.slots.children[1].textContent, /Verse/u);
});

test('write stays disabled until a track, a slot and a groove are all chosen', async () => {
  const { nodes } = await runPage('picker.js', PICKER_NODES);
  assert.equal(nodes.write.disabled, true);

  nodes.tracks.children[0].dispatch('click');
  assert.equal(nodes.write.disabled, true);
  nodes.slots.children[0].dispatch('click');
  assert.equal(nodes.write.disabled, true);

  nodes.surprise.dispatch('click');
  await settle();
  assert.equal(nodes.write.disabled, false);
});

test('the button says replace and turns red on a filled slot', async () => {
  // A filled slot has to look different before the tap, not after: the
  // refusal downstream is a safety net, not the interface.
  const { nodes } = await runPage('picker.js', PICKER_NODES);
  nodes.tracks.children[0].dispatch('click');

  nodes.slots.children[0].dispatch('click');
  assert.equal(nodes.write.textContent, 'Escrever');
  nodes.slots.children[1].dispatch('click');
  assert.equal(nodes.write.textContent, 'Substituir');
  assert.equal(nodes.write.className, 'danger');
});

test('the command carries the chosen indices and the knob values', async () => {
  const { nodes, requests } = await runPage('picker.js', PICKER_NODES);
  nodes.tracks.children[0].dispatch('click');
  nodes.slots.children[0].dispatch('click');
  nodes.surprise.dispatch('click');
  await settle();

  nodes.write.dispatch('click');
  await settle();

  const sent = requests.find((entry) => entry.path === '/api/command');
  const body = sent?.body as Record<string, unknown>;
  assert.equal(body.op, 'write');
  assert.equal(body.trackIndex, 0);
  assert.equal(body.slotIndex, 0);
  assert.equal(body.replace, false);
  assert.equal(typeof body.grooveId, 'string');
});

test('a search with no match says so and leaves write disabled', async () => {
  const { nodes } = await runPage('picker.js', PICKER_NODES, { emptySearch: true });
  nodes.tracks.children[0].dispatch('click');
  nodes.slots.children[0].dispatch('click');
  nodes.surprise.dispatch('click');
  await settle();

  assert.match(nodes.chosen.textContent, /Nenhum groove/u);
  assert.equal(nodes.write.disabled, true);
});

test('a failing request on the picker is visible and terminal', async () => {
  const { nodes } = await runPage('picker.js', PICKER_NODES, { searchStatus: 500 });
  nodes.surprise.dispatch('click');
  await settle();
  assert.equal(nodes.status.textContent, 'Falha no Groove Brain.');
  assert.equal(nodes.error.textContent, 'HELPER_SEARCH_500');
  assert.equal(nodes.controls.hidden, true);
});
