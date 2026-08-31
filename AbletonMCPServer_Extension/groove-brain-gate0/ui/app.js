const statusNode = document.querySelector('#status');
const controls = document.querySelector('#controls');
const confirmNode = document.querySelector('#confirm');
const runNode = document.querySelector('#run');
const cancelNode = document.querySelector('#cancel');
const errorNode = document.querySelector('#error');
let submitted = false;

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
  runNode.disabled = true;
  cancelNode.disabled = true;
  controls.hidden = true;
  statusNode.textContent = 'Falha no Gate 0.';
  const message = error instanceof Error ? error.message : String(error);
  errorNode.textContent = message.replace(/[0-9a-f]{64}/gi, '[redacted]');
}

function submit(payload) {
  if (submitted) return;
  submitted = true;
  runNode.disabled = true;
  cancelNode.disabled = true;
  try {
    closeAndSend(payload);
  } catch (error) {
    showTerminalError(error);
  }
}

async function bootstrap() {
  const token = window.location.hash.slice(1);
  history.replaceState(null, '', window.location.pathname);
  if (!/^[0-9a-f]{64}$/i.test(token)) {
    throw new Error('INVALID_BOOTSTRAP_TOKEN');
  }
  const response = await fetch('/api/health', {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
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

confirmNode.addEventListener('change', () => {
  runNode.disabled = submitted || !confirmNode.checked;
});
runNode.addEventListener('click', () => {
  if (!confirmNode.checked) return;
  submit({ action: 'run_session_probe', confirmed: true, protocol: 1 });
});
cancelNode.addEventListener('click', () => {
  submit({ action: 'cancel', confirmed: false, protocol: 1 });
});

bootstrap().catch(showTerminalError);
