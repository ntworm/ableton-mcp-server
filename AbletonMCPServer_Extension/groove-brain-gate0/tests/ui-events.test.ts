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
  options: { bridgeThrows?: boolean; searchStatus?: number } = {},
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
    String,
    setTimeout,
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
      if (target === '/api/select') {
        return { ok: true, status: 200, async json() { return { status: 'selected' }; } };
      }
      const status = options.searchStatus ?? 200;
      return { ok: status === 200, status, async json() { return SEARCH_PAYLOAD; } };
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
  'status', 'controls', 'error', 'genre', 'bpm', 'search', 'results', 'count', 'sent',
];

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

test('the picker searches as soon as it connects', async () => {
  const { nodes, requests } = await runPage('picker.js', PICKER_NODES);
  assert.equal(nodes.controls.hidden, false);
  assert.ok(requests.some((entry) => entry.path === '/api/search'));
  assert.equal(nodes.results.children.length, 2);
  assert.match(nodes.count.textContent, /103 encontrados/u);
});

test('a search sends only the filters that were filled in', async () => {
  const { nodes, requests } = await runPage('picker.js', PICKER_NODES);
  nodes.genre.value = '  metal  ';
  nodes.search.dispatch('click');
  await settle();

  const searches = requests.filter((entry) => entry.path === '/api/search');
  assert.deepEqual(searches.at(-1)?.body, { genre: 'metal' });
});

test('tapping a result sends it to Live and the panel stays open', async () => {
  // The panel does not close itself: picking a second groove for the next slot
  // should not mean scanning the code again.
  const { nodes, requests } = await runPage('picker.js', PICKER_NODES);
  nodes.results.children[1].dispatch('click');
  await settle();

  const select = requests.find((entry) => entry.path === '/api/select');
  assert.deepEqual(select?.body, { id: 'b2' });
  assert.equal(nodes.controls.hidden, false);
  assert.equal(nodes.sent.hidden, false);
});

test('a failing search on the picker is visible and terminal', async () => {
  const { nodes } = await runPage('picker.js', PICKER_NODES, { searchStatus: 500 });
  assert.equal(nodes.status.textContent, 'Falha no Groove Brain.');
  assert.equal(nodes.error.textContent, 'HELPER_SEARCH_500');
  assert.equal(nodes.controls.hidden, true);
});
