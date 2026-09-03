const statusNode = document.querySelector('#status');
const controls = document.querySelector('#controls');
const errorNode = document.querySelector('#error');
const qrNode = document.querySelector('#qr');
const urlNode = document.querySelector('#url');
const doneNode = document.querySelector('#done');
const cancelNode = document.querySelector('#cancel');

let submitted = false;
let bearer = null;

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
  doneNode.disabled = true;
  cancelNode.disabled = true;
  controls.hidden = true;
  statusNode.textContent = 'Falha no Groove Brain.';
  const message = error instanceof Error ? error.message : String(error);
  errorNode.textContent = message.replace(/[0-9a-f]{64}/gi, '[redacted]');
}

function submit(payload) {
  if (submitted) return;
  submitted = true;
  doneNode.disabled = true;
  cancelNode.disabled = true;
  try {
    closeAndSend(payload);
  } catch (error) {
    showTerminalError(error);
  }
}

async function bootstrap() {
  bearer = window.location.hash.slice(1);
  history.replaceState(null, '', window.location.pathname);
  if (!/^[0-9a-f]{64}$/i.test(bearer)) {
    throw new Error('INVALID_BOOTSTRAP_TOKEN');
  }
  const health = await fetch('/api/health', {
    method: 'POST',
    headers: { Authorization: `Bearer ${bearer}` },
    cache: 'no-store',
  });
  if (!health.ok) throw new Error(`HELPER_HEALTH_${health.status}`);
  const body = await health.json();
  if (body.status !== 'ok' || body.protocol !== 1) {
    throw new Error('HELPER_PROTOCOL_MISMATCH');
  }

  const panel = await fetch('/api/panel', {
    method: 'POST',
    headers: { Authorization: `Bearer ${bearer}` },
    cache: 'no-store',
  });
  if (!panel.ok) throw new Error(`HELPER_PANEL_${panel.status}`);
  const { url, qr } = await panel.json();

  // The SVG comes from the helper, not from the network, and carries no script.
  if (qr) qrNode.innerHTML = qr;
  urlNode.textContent = url;
  // Clickable, not just readable: on the same machine the panel is one tap
  // away, and typing a sixty-four character token is nobody's idea of a link.
  urlNode.href = url;
  statusNode.textContent = 'Aponte a câmera do celular para o código.';
  controls.hidden = false;
}

doneNode.addEventListener('click', () => {
  submit({ action: 'handoff', confirmed: true, protocol: 1 });
});

cancelNode.addEventListener('click', () => {
  submit({ action: 'cancel', confirmed: false, protocol: 1 });
});

bootstrap().catch(showTerminalError);
