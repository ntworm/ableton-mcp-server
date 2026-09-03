const statusNode = document.querySelector('#status');
const controls = document.querySelector('#controls');
const errorNode = document.querySelector('#error');
const tempoNode = document.querySelector('#tempo');
const tracksNode = document.querySelector('#tracks');
const slotsBlock = document.querySelector('#slotsBlock');
const slotsNode = document.querySelector('#slots');
const genreNode = document.querySelector('#genre');
const bpmNode = document.querySelector('#bpm');
const surpriseNode = document.querySelector('#surprise');
const chosenNode = document.querySelector('#chosen');
const knobsNode = document.querySelector('#knobs');
const writeNode = document.querySelector('#write');
const receiptNode = document.querySelector('#receipt');

const AXES = ['density', 'energy', 'swing', 'complexity', 'polyrhythm'];
const AXIS_LABEL = {
  density: 'Densidade',
  energy: 'Intensidade',
  swing: 'Swing',
  complexity: 'Complexidade',
  polyrhythm: 'Polirritmia',
};

let bearer = null;
let session = null;
let snapshot = null;
let trackIndex = null;
let slotIndex = null;
let groove = null;
const knobs = {};

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
  if (!response.ok) throw new Error(`HELPER_${path.slice(5).toUpperCase()}_${response.status}`);
  return response.json();
}

function updateWriteButton() {
  const slot = slotIndex === null ? null : snapshot?.tracks[trackIndex]?.slots[slotIndex];
  const ready = trackIndex !== null && slotIndex !== null && groove !== null;
  writeNode.disabled = !ready;
  // A filled slot has to look different from an empty one before the tap, not
  // after: the refusal is a safety net, not the interface.
  writeNode.textContent = slot?.filled ? 'Substituir' : 'Escrever';
  writeNode.className = slot?.filled ? 'danger' : '';
}

function renderSlots() {
  const track = snapshot?.tracks[trackIndex];
  slotsBlock.hidden = !track;
  slotsNode.replaceChildren();
  if (!track) return;
  for (const slot of track.slots) {
    const entry = document.createElement('li');
    const count = slot.noteCount === null ? '?' : slot.noteCount;
    entry.textContent = slot.filled
      ? `${slot.index + 1}. ${slot.name ?? 'clipe'} · ${count} notas`
      : `${slot.index + 1}. vazio`;
    entry.className = slot.index === slotIndex ? 'selected' : slot.filled ? 'filled' : '';
    entry.addEventListener('click', () => {
      slotIndex = slot.index;
      renderSlots();
      updateWriteButton();
    });
    slotsNode.append(entry);
  }
}

function renderTracks() {
  tempoNode.textContent = snapshot ? `${snapshot.tempo} BPM` : '';
  tracksNode.replaceChildren();
  for (const track of snapshot?.tracks ?? []) {
    const entry = document.createElement('li');
    const tags = [track.meter, track.hasDrumRack ? 'drum rack' : null, track.armed ? 'armada' : null]
      .filter(Boolean)
      .join(' · ');
    entry.textContent = `${track.name} — ${tags}`;
    entry.className = track.index === trackIndex ? 'selected' : '';
    entry.addEventListener('click', () => {
      trackIndex = track.index;
      slotIndex = null;
      renderTracks();
      renderSlots();
      updateWriteButton();
    });
    tracksNode.append(entry);
  }
}

function renderKnobs() {
  knobsNode.replaceChildren();
  for (const axis of AXES) {
    const row = document.createElement('label');
    const name = document.createElement('span');
    name.textContent = AXIS_LABEL[axis];
    const slider = document.createElement('input');
    slider.type = 'range';
    slider.min = '-100';
    slider.max = '100';
    slider.value = '0';
    slider.addEventListener('input', () => {
      name.textContent = `${AXIS_LABEL[axis]} ${(Number(slider.value) / 100).toFixed(2)}`;
    });
    knobs[axis] = slider;
    row.append(name, slider);
    knobsNode.append(row);
  }
}

function readKnobs() {
  const out = {};
  for (const axis of AXES) {
    const value = Number(knobs[axis].value) / 100;
    if (value !== 0) out[axis] = value;
  }
  return out;
}

async function refresh() {
  // A helper restart means this page belongs to a session that no longer
  // exists. Saying so beats the refused connection the user saw before.
  const health = await api('/api/health');
  if (session !== null && health.session !== session) {
    throw new Error('SESSAO_ENCERRADA: escaneie o código de novo');
  }
  const next = await api('/api/snapshot');
  if (!next) return;
  snapshot = next;
  // The chosen indices survive a refresh only while they still exist: a track
  // deleted in Live must not stay selected on the phone.
  if (trackIndex !== null && !snapshot.tracks[trackIndex]) trackIndex = null;
  if (trackIndex !== null && slotIndex !== null && !snapshot.tracks[trackIndex].slots[slotIndex]) {
    slotIndex = null;
  }
  renderTracks();
  renderSlots();
  updateWriteButton();
}

surpriseNode.addEventListener('click', () => {
  const body = {};
  const genre = genreNode.value.trim();
  if (genre) body.genre = genre;
  if (bpmNode.value) body.bpm = bpmNode.value;
  api('/api/search', body)
    .then((payload) => {
      if (payload.items.length === 0) {
        chosenNode.textContent = 'Nenhum groove com esses filtros.';
        groove = null;
      } else {
        groove = payload.items[Math.floor(Math.random() * payload.items.length)];
        chosenNode.textContent =
          `${groove.bars} compassos ${groove.meter} · ${groove.note_count} notas · `
          + `${groove.kit.join(' ')} — de ${payload.total} encontrados`;
      }
      updateWriteButton();
    })
    .catch(showTerminalError);
});

writeNode.addEventListener('click', () => {
  if (trackIndex === null || slotIndex === null || !groove) return;
  const slot = snapshot.tracks[trackIndex].slots[slotIndex];
  writeNode.disabled = true;
  receiptNode.textContent = 'Escrevendo…';
  api('/api/command', {
    op: 'write',
    trackIndex,
    slotIndex,
    grooveId: groove.id,
    transforms: readKnobs(),
    seed: Math.floor(Math.random() * 1_000_000),
    replace: Boolean(slot.filled),
  })
    .then(() => {
      receiptNode.textContent = 'Enviado ao Live.';
      // The extension republishes after it writes, so the slot state the panel
      // shows catches up without the user reloading.
      setTimeout(() => refresh().catch(showTerminalError), 1_200);
    })
    .catch(showTerminalError);
});

genreNode.addEventListener('keydown', (event) => {
  if (event.key === 'Enter') surpriseNode.click();
});

async function bootstrap() {
  bearer = window.location.hash.slice(1);
  history.replaceState(null, '', window.location.pathname);
  if (!/^[0-9a-f]{64}$/i.test(bearer)) throw new Error('INVALID_BOOTSTRAP_TOKEN');
  const health = await api('/api/health');
  if (health.status !== 'ok' || health.protocol !== 1) throw new Error('HELPER_PROTOCOL_MISMATCH');
  session = health.session ?? null;

  renderKnobs();
  await refresh();
  statusNode.textContent = snapshot
    ? 'Escolha uma track e um slot.'
    : 'Aguardando o Live enviar a sessão…';
  controls.hidden = false;
  setInterval(() => refresh().catch(showTerminalError), 4_000);
}

bootstrap().catch(showTerminalError);
