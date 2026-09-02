const statusNode = document.querySelector('#status');
const controls = document.querySelector('#controls');
const errorNode = document.querySelector('#error');
const genreNode = document.querySelector('#genre');
const bpmNode = document.querySelector('#bpm');
const searchNode = document.querySelector('#search');
const resultsNode = document.querySelector('#results');
const countNode = document.querySelector('#count');
const sentNode = document.querySelector('#sent');

let bearer = null;

function showTerminalError(error) {
  controls.hidden = true;
  statusNode.textContent = 'Falha no Groove Brain.';
  const message = error instanceof Error ? error.message : String(error);
  errorNode.textContent = message.replace(/[0-9a-f]{64}/gi, '[redacted]');
}

async function api(path, body) {
  const response = await fetch(path, {
    method: 'POST',
    headers: { Authorization: `Bearer ${bearer}`, 'Content-Type': 'application/json' },
    cache: 'no-store',
    body: JSON.stringify(body ?? {}),
  });
  if (!response.ok) {
    throw new Error(`HELPER_${path.slice(5).toUpperCase()}_${response.status}`);
  }
  return response.json();
}

function choose(id) {
  // The panel does not close itself. Live writes the clip, and the user may
  // want to pick a second groove for the next slot without scanning again.
  api('/api/select', { id })
    .then(() => {
      sentNode.hidden = false;
      setTimeout(() => { sentNode.hidden = true; }, 2_000);
    })
    .catch(showTerminalError);
}

function render(payload) {
  resultsNode.replaceChildren();
  countNode.textContent = `${payload.total} encontrados, mostrando ${payload.items.length}`;
  for (const item of payload.items) {
    const entry = document.createElement('li');
    entry.textContent =
      `${item.bars} compassos ${item.meter} · ${item.note_count} notas · ${item.kit.join(' ')}`;
    entry.addEventListener('click', () => choose(item.id));
    resultsNode.append(entry);
  }
}

function runSearch() {
  const body = {};
  const genre = genreNode.value.trim();
  if (genre) body.genre = genre;
  if (bpmNode.value) body.bpm = bpmNode.value;
  api('/api/search', body).then(render).catch(showTerminalError);
}

async function bootstrap() {
  bearer = window.location.hash.slice(1);
  history.replaceState(null, '', window.location.pathname);
  if (!/^[0-9a-f]{64}$/i.test(bearer)) {
    throw new Error('INVALID_BOOTSTRAP_TOKEN');
  }
  const body = await api('/api/health');
  if (body.status !== 'ok' || body.protocol !== 1) {
    throw new Error('HELPER_PROTOCOL_MISMATCH');
  }
  statusNode.textContent = 'Toque em um groove para enviá-lo ao Live.';
  controls.hidden = false;
  runSearch();
}

searchNode.addEventListener('click', runSearch);
genreNode.addEventListener('keydown', (event) => {
  if (event.key === 'Enter') runSearch();
});

bootstrap().catch(showTerminalError);
