const statusNode = document.querySelector('#status');
const controls = document.querySelector('#controls');
const errorNode = document.querySelector('#error');
const genreNode = document.querySelector('#genre');
const bpmNode = document.querySelector('#bpm');
const searchNode = document.querySelector('#search');
const resultsNode = document.querySelector('#results');
const countNode = document.querySelector('#count');
const insertNode = document.querySelector('#insert');
const cancelNode = document.querySelector('#cancel');

let submitted = false;
// Hoisted out of bootstrap(): the search calls need it too, and the URL it
// arrived in is erased on the first line of the handshake.
let bearer = null;
let selectedId = null;

function closeAndSend(payload) {
  const message = { method: 'close_and_send', params: [JSON.stringify(payload)] };
  if (window.chrome?.webview) {
    window.chrome.webview.postMessage(message);
    return;
  }
  if (window.webkit?.messageHandlers?.live) {
    window.webkit.messageHandlers.live.postMessage(message);
    return;
  }
  throw new Error('ABLETON_MODAL_BRIDGE_UNAVAILABLE');
}

function showTerminalError(error) {
  submitted = true;
  searchNode.disabled = true;
  insertNode.disabled = true;
  cancelNode.disabled = true;
  controls.hidden = true;
  statusNode.textContent = 'Falha no Groove Brain.';
  const message = error instanceof Error ? error.message : String(error);
  errorNode.textContent = message.replace(/[0-9a-f]{64}/gi, '[redacted]');
}

function submit(payload) {
  if (submitted) return;
  submitted = true;
  searchNode.disabled = true;
  insertNode.disabled = true;
  cancelNode.disabled = true;
  try {
    closeAndSend(payload);
  } catch (error) {
    showTerminalError(error);
  }
}

async function api(path, body) {
  const response = await fetch(path, {
    method: 'POST',
    headers: { Authorization: `Bearer ${bearer}`, 'Content-Type': 'application/json' },
    cache: 'no-store',
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`HELPER_${path.slice(5).toUpperCase()}_${response.status}`);
  }
  return response.json();
}

function select(id, node) {
  selectedId = id;
  for (const child of resultsNode.children) {
    child.className = child === node ? 'selected' : '';
  }
  insertNode.disabled = submitted;
}

function render(payload) {
  // A new search invalidates the old pick. Leaving it selected would insert a
  // groove that is no longer on screen.
  selectedId = null;
  insertNode.disabled = true;
  resultsNode.replaceChildren();
  countNode.textContent = `${payload.total} encontrados, mostrando ${payload.items.length}`;
  for (const item of payload.items) {
    const entry = document.createElement('li');
    entry.textContent = `${item.bars} compassos ${item.meter} · ${item.note_count} notas · ${item.kit.join(' ')}`;
    entry.addEventListener('click', () => select(item.id, entry));
    resultsNode.append(entry);
  }
}

async function bootstrap() {
  bearer = window.location.hash.slice(1);
  history.replaceState(null, '', window.location.pathname);
  if (!/^[0-9a-f]{64}$/i.test(bearer)) {
    throw new Error('INVALID_BOOTSTRAP_TOKEN');
  }
  const response = await fetch('/api/health', {
    method: 'POST',
    headers: { Authorization: `Bearer ${bearer}` },
    cache: 'no-store',
  });
  if (!response.ok) {
    throw new Error(`HELPER_HEALTH_${response.status}`);
  }
  const body = await response.json();
  if (body.status !== 'ok' || body.protocol !== 1) {
    throw new Error('HELPER_PROTOCOL_MISMATCH');
  }
  statusNode.textContent = 'Helper local autenticado. Nenhuma conexão externa usada.';
  controls.hidden = false;
}

searchNode.addEventListener('click', () => {
  if (submitted) return;
  const body = {};
  const genre = genreNode.value.trim();
  if (genre) body.genre = genre;
  if (bpmNode.value) body.bpm = bpmNode.value;
  api('/api/search', body).then(render).catch(showTerminalError);
});

insertNode.addEventListener('click', () => {
  if (!selectedId) return;
  submit({ action: 'insert_groove', confirmed: true, protocol: 1, groove_id: selectedId });
});

cancelNode.addEventListener('click', () => {
  submit({ action: 'cancel', confirmed: false, protocol: 1 });
});

bootstrap().catch(showTerminalError);
