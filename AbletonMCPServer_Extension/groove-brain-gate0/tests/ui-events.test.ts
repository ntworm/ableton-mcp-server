import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import vm from 'node:vm';

type Handler = () => void;

class FakeNode {
  checked = false;
  disabled = false;
  hidden = false;
  textContent = '';
  private readonly handlers = new Map<string, Handler>();

  addEventListener(name: string, handler: Handler): void {
    this.handlers.set(name, handler);
  }

  dispatch(name: string): void {
    const handler = this.handlers.get(name);
    if (!handler) throw new Error(`MISSING_HANDLER:${name}`);
    handler();
  }
}

interface UiHarness {
  cancel: FakeNode;
  confirm: FakeNode;
  controls: FakeNode;
  error: FakeNode;
  messages: unknown[];
  run: FakeNode;
  status: FakeNode;
}

async function createHarness(bridgeThrows = false): Promise<UiHarness> {
  const status = new FakeNode();
  const controls = new FakeNode();
  const confirm = new FakeNode();
  const run = new FakeNode();
  const cancel = new FakeNode();
  const error = new FakeNode();
  controls.hidden = true;
  run.disabled = true;
  const nodes = new Map<string, FakeNode>([
    ['#status', status],
    ['#controls', controls],
    ['#confirm', confirm],
    ['#run', run],
    ['#cancel', cancel],
    ['#error', error],
  ]);
  const messages: unknown[] = [];
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
    },
    fetch: async () => ({
      ok: true,
      status: 200,
      async json() {
        return { status: 'ok', protocol: 1 };
      },
    }),
    history: { replaceState() {} },
    window: {
      chrome: {
        webview: {
          postMessage(message: unknown) {
            if (bridgeThrows) throw new Error('BRIDGE_FAILED');
            messages.push(message);
          },
        },
      },
      location: { hash: `#${token}`, pathname: '/' },
    },
  });
  vm.runInContext(source, context, { filename: 'app.js' });
  await new Promise((resolve) => setImmediate(resolve));
  return { cancel, confirm, controls, error, messages, run, status };
}

test('run action latches after the first confirmed click', async () => {
  const ui = await createHarness();
  ui.confirm.checked = true;
  ui.confirm.dispatch('change');
  assert.equal(ui.run.disabled, false);

  ui.run.dispatch('click');
  ui.run.dispatch('click');

  assert.equal(ui.messages.length, 1);
  assert.equal(ui.run.disabled, true);
  assert.equal(ui.cancel.disabled, true);
});

test('bridge failure becomes a terminal visible UI error', async () => {
  const ui = await createHarness(true);

  assert.doesNotThrow(() => ui.cancel.dispatch('click'));
  assert.equal(ui.status.textContent, 'Falha no Gate 0.');
  assert.equal(ui.error.textContent, 'BRIDGE_FAILED');
  assert.equal(ui.controls.hidden, true);
  assert.equal(ui.run.disabled, true);
  assert.equal(ui.cancel.disabled, true);
});
