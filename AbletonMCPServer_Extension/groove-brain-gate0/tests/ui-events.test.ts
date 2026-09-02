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

interface UiHarness {
  bpm: FakeNode;
  cancel: FakeNode;
  controls: FakeNode;
  count: FakeNode;
  error: FakeNode;
  genre: FakeNode;
  insert: FakeNode;
  messages: unknown[];
  requests: { path: string; body: unknown }[];
  results: FakeNode;
  search: FakeNode;
  status: FakeNode;
}

async function createHarness(
  options: { bridgeThrows?: boolean; searchStatus?: number } = {},
): Promise<UiHarness> {
  const nodesByName: Record<string, FakeNode> = {
    status: new FakeNode(),
    controls: new FakeNode(),
    error: new FakeNode(),
    genre: new FakeNode(),
    bpm: new FakeNode(),
    search: new FakeNode(),
    results: new FakeNode(),
    count: new FakeNode(),
    insert: new FakeNode(),
    cancel: new FakeNode(),
  };
  nodesByName.controls.hidden = true;
  nodesByName.insert.disabled = true;
  const nodes = new Map<string, FakeNode>(
    Object.entries(nodesByName).map(([name, node]) => [`#${name}`, node]),
  );

  const messages: unknown[] = [];
  const requests: { path: string; body: unknown }[] = [];
  const token = 'a'.repeat(64);
  const source = fs.readFileSync(path.resolve('groove-brain-gate0/ui/app.js'), 'utf8');
  const context = vm.createContext({
    AbortSignal,
    Error,
    JSON,
    String,
    document: {
      querySelector(selector: string) {
        const node = nodes.get(selector);
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
      const status = options.searchStatus ?? 200;
      return {
        ok: status === 200,
        status,
        async json() { return SEARCH_PAYLOAD; },
      };
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
  vm.runInContext(source, context, { filename: 'app.js' });
  await new Promise((resolve) => setImmediate(resolve));
  return { ...nodesByName, messages, requests } as UiHarness;
}

async function settle(): Promise<void> {
  await new Promise((resolve) => setImmediate(resolve));
  await new Promise((resolve) => setImmediate(resolve));
}

test('the panel is usable only after the helper authenticates', async () => {
  const ui = await createHarness();
  assert.equal(ui.controls.hidden, false);
  assert.equal(ui.insert.disabled, true);
});

test('a search sends only the filters that were filled in', async () => {
  const ui = await createHarness();
  ui.genre.value = '  metal  ';
  ui.search.dispatch('click');
  await settle();

  const search = ui.requests.find((entry) => entry.path === '/api/search');
  assert.deepEqual(search?.body, { genre: 'metal' });
});

test('results render and picking one enables insert', async () => {
  const ui = await createHarness();
  ui.search.dispatch('click');
  await settle();

  assert.equal(ui.results.children.length, 2);
  assert.match(ui.count.textContent, /103 encontrados/u);
  assert.equal(ui.insert.disabled, true);

  ui.results.children[1].dispatch('click');
  assert.equal(ui.insert.disabled, false);
  assert.equal(ui.results.children[1].className, 'selected');
  assert.equal(ui.results.children[0].className, '');
});

test('insert sends the picked groove and latches after the first click', async () => {
  const ui = await createHarness();
  ui.search.dispatch('click');
  await settle();
  ui.results.children[0].dispatch('click');

  ui.insert.dispatch('click');
  ui.insert.dispatch('click');

  assert.equal(ui.messages.length, 1);
  const payload = JSON.parse(
    (ui.messages[0] as { params: string[] }).params[0],
  );
  assert.deepEqual(payload, {
    action: 'insert_groove',
    confirmed: true,
    protocol: 1,
    groove_id: 'a1',
  });
  assert.equal(ui.insert.disabled, true);
  assert.equal(ui.cancel.disabled, true);
});

test('insert does nothing while nothing is picked', async () => {
  const ui = await createHarness();
  ui.search.dispatch('click');
  await settle();

  ui.insert.dispatch('click');
  assert.equal(ui.messages.length, 0);
});

test('a new search drops the previous pick', async () => {
  // Leaving it selected would insert a groove that is no longer on screen.
  const ui = await createHarness();
  ui.search.dispatch('click');
  await settle();
  ui.results.children[0].dispatch('click');
  assert.equal(ui.insert.disabled, false);

  ui.search.dispatch('click');
  await settle();
  assert.equal(ui.insert.disabled, true);

  ui.insert.dispatch('click');
  assert.equal(ui.messages.length, 0);
});

test('a failing search becomes a terminal visible error', async () => {
  const ui = await createHarness({ searchStatus: 500 });
  ui.search.dispatch('click');
  await settle();

  assert.equal(ui.status.textContent, 'Falha no Groove Brain.');
  assert.equal(ui.error.textContent, 'HELPER_SEARCH_500');
  assert.equal(ui.controls.hidden, true);
});

test('bridge failure becomes a terminal visible UI error', async () => {
  const ui = await createHarness({ bridgeThrows: true });

  assert.doesNotThrow(() => ui.cancel.dispatch('click'));
  assert.equal(ui.status.textContent, 'Falha no Groove Brain.');
  assert.equal(ui.error.textContent, 'BRIDGE_FAILED');
  assert.equal(ui.controls.hidden, true);
  assert.equal(ui.insert.disabled, true);
  assert.equal(ui.cancel.disabled, true);
});
