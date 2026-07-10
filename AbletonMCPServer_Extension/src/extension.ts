import { initialize, type ActivationContext } from '@ableton-extensions/sdk';
import { setExtensionContext, clearExtensionContext } from './context.js';
import { startServer, stopServer } from './index.js';

let activated = false;

function activate(activation: ActivationContext): void {
  if (activated) {
    console.log('[ableton-mcp-server-extension] activate() called while already active; restarting server only');
    startServer();
    return;
  }
  activated = true;

  const context = initialize(activation, '1.0.0');
  setExtensionContext(context);

  console.log('[ableton-mcp-server-extension] starting WebSocket server...');
  startServer();

  console.log('[ableton-mcp-server-extension] activate() done; awaiting requests');
}

function deactivate(): void {
  if (!activated) return;
  activated = false;

  stopServer()
    .finally(() => {
      clearExtensionContext();
      console.log('[ableton-mcp-server-extension] deactivate() done; server stopped');
    });
}

export { activate, deactivate };
