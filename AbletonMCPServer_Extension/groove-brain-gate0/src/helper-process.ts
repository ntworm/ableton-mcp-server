import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process';
import { createHash, randomBytes } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import readline from 'node:readline';
import { GATE0_PROTOCOL, parseHelperReady, type HelperReady } from './protocol.js';

const HELPER_RELATIVE_PATH = 'windows-x64/groove-brain-gate0-helper.exe';

export interface RuntimeManifest {
  protocol: 1;
  platform: 'win32-x64';
  helper: typeof HELPER_RELATIVE_PATH;
  sha256: string;
}

function isStrictDescendant(root: string, candidate: string): boolean {
  const relative = path.relative(root, candidate);
  return relative !== ''
    && relative !== '..'
    && !relative.startsWith(`..${path.sep}`)
    && !path.isAbsolute(relative);
}

function sha256(pathname: string): string {
  return createHash('sha256').update(fs.readFileSync(pathname)).digest('hex');
}

function parseRuntimeManifest(raw: string): RuntimeManifest {
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    throw new Error('INVALID_RUNTIME_MANIFEST');
  }
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('INVALID_RUNTIME_MANIFEST');
  }
  const candidate = value as Record<string, unknown>;
  if (
    candidate.protocol !== GATE0_PROTOCOL
    || candidate.platform !== 'win32-x64'
    || typeof candidate.helper !== 'string'
    || typeof candidate.sha256 !== 'string'
    || !/^[0-9a-f]{64}$/.test(candidate.sha256)
  ) {
    throw new Error('INVALID_RUNTIME_MANIFEST');
  }
  return candidate as unknown as RuntimeManifest;
}

export function loadRuntime(
  resourceRoot: string,
): { executable: string; manifest: RuntimeManifest } {
  try {
    const runtimeRoot = path.resolve(resourceRoot, 'runtime');
    const manifestPath = path.join(runtimeRoot, 'manifest.json');
    const manifest = parseRuntimeManifest(fs.readFileSync(manifestPath, 'utf8'));
    if (manifest.helper !== HELPER_RELATIVE_PATH) {
      throw new Error('INVALID_HELPER_PATH');
    }
    const executable = path.resolve(runtimeRoot, ...manifest.helper.split('/'));
    if (!isStrictDescendant(runtimeRoot, executable)) {
      throw new Error('INVALID_HELPER_PATH');
    }
    const stats = fs.lstatSync(executable);
    if (!stats.isFile() || stats.isSymbolicLink()) {
      throw new Error('INVALID_HELPER_PATH');
    }
    const realRuntimeRoot = fs.realpathSync.native(runtimeRoot);
    const realExecutable = fs.realpathSync.native(executable);
    if (!isStrictDescendant(realRuntimeRoot, realExecutable)) {
      throw new Error('INVALID_HELPER_PATH');
    }
    if (sha256(realExecutable) !== manifest.sha256) {
      throw new Error('HELPER_HASH_MISMATCH');
    }
    return { executable: realExecutable, manifest };
  } catch (error) {
    if (
      error instanceof Error
      && [
        'INVALID_RUNTIME_MANIFEST',
        'INVALID_HELPER_PATH',
        'HELPER_HASH_MISMATCH',
      ].includes(error.message)
    ) {
      throw error;
    }
    throw new Error('INVALID_HELPER_PATH');
  }
}

function hasExited(child: ChildProcessWithoutNullStreams): boolean {
  return child.exitCode !== null || child.signalCode !== null;
}

function readyLine(
  child: ChildProcessWithoutNullStreams,
  expectedParentPid: number,
  timeoutMs: number,
): Promise<HelperReady> {
  return new Promise<HelperReady>((resolve, reject) => {
    const lines = readline.createInterface({ input: child.stdout, crlfDelay: Infinity });
    let settled = false;
    let timer: NodeJS.Timeout | undefined;

    const cleanup = () => {
      if (timer) clearTimeout(timer);
      lines.removeListener('line', onLine);
      child.removeListener('exit', onExit);
      child.removeListener('error', onError);
      lines.close();
    };
    const finish = (action: () => void) => {
      if (settled) return;
      settled = true;
      cleanup();
      action();
    };
    const onLine = (line: string) => {
      try {
        const ready = parseHelperReady(line, expectedParentPid);
        finish(() => resolve(ready));
      } catch (error) {
        finish(() => reject(error));
      }
    };
    const onExit = (code: number | null, signal: NodeJS.Signals | null) => {
      finish(() => reject(new Error(`HELPER_EXITED_BEFORE_READY:${code ?? signal ?? 'unknown'}`)));
    };
    const onError = (error: Error) => {
      finish(() => reject(new Error(`HELPER_SPAWN_ERROR:${error.message}`)));
    };

    lines.once('line', onLine);
    child.once('exit', onExit);
    child.once('error', onError);
    timer = setTimeout(
      () => finish(() => reject(new Error('HELPER_READY_TIMEOUT'))),
      timeoutMs,
    );
    if (hasExited(child)) {
      onExit(child.exitCode, child.signalCode);
    }
  });
}

function waitForExit(
  child: ChildProcessWithoutNullStreams,
  timeoutMs: number,
): Promise<boolean> {
  if (hasExited(child) || child.pid === undefined) return Promise.resolve(true);
  return new Promise<boolean>((resolve) => {
    let settled = false;
    let timer: NodeJS.Timeout | undefined;
    const cleanup = () => {
      if (timer) clearTimeout(timer);
      child.removeListener('exit', onExit);
      child.removeListener('error', onError);
    };
    const finish = (result: boolean) => {
      if (settled) return;
      settled = true;
      cleanup();
      resolve(result);
    };
    const onExit = () => finish(true);
    const onError = () => finish(hasExited(child) || child.pid === undefined);
    child.once('exit', onExit);
    child.once('error', onError);
    if (hasExited(child)) {
      finish(true);
      return;
    }
    timer = setTimeout(() => finish(false), timeoutMs);
  });
}

async function terminateChild(
  child: ChildProcessWithoutNullStreams,
  timeoutMs: number,
): Promise<void> {
  if (hasExited(child) || child.pid === undefined) return;
  try {
    child.kill();
  } catch {
    // The exit check below decides whether termination actually completed.
  }
  if (!(await waitForExit(child, timeoutMs)) && !hasExited(child)) {
    throw new Error('HELPER_TERMINATION_TIMEOUT');
  }
}

export class HelperSession {
  private stopPromise?: Promise<void>;

  private constructor(
    private readonly child: ChildProcessWithoutNullStreams,
    public readonly ready: HelperReady,
    private readonly token: string,
  ) {}

  static async start(resourceRoot: string, timeoutMs = 5_000): Promise<HelperSession> {
    if (process.platform !== 'win32' || process.arch !== 'x64') {
      throw new Error('UNSUPPORTED_GATE0_PLATFORM');
    }
    const { executable } = loadRuntime(resourceRoot);
    const token = randomBytes(32).toString('hex');
    const child = spawn(executable, [], {
      cwd: resourceRoot,
      windowsHide: true,
      stdio: ['pipe', 'pipe', 'pipe'],
      env: { SystemRoot: process.env.SystemRoot ?? 'C:\\Windows' },
    });
    child.stdin.on('error', () => {
      // EPIPE is expected if the helper exits between readiness and shutdown.
    });
    const awaitingReady = readyLine(child, process.pid, timeoutMs);
    try {
      child.stdin.write(
        `${JSON.stringify({
          type: 'bootstrap',
          protocol: GATE0_PROTOCOL,
          token,
          ui_dir: path.join(resourceRoot, 'ui'),
          parent_pid: process.pid,
        })}\n`,
      );
      const ready = await awaitingReady;
      return new HelperSession(child, ready, token);
    } catch (error) {
      await terminateChild(child, 1_000);
      throw error;
    }
  }

  get origin(): string {
    return `http://localhost:${this.ready.port}`;
  }

  get modalUrl(): string {
    return `${this.origin}/#${this.token}`;
  }

  async assertHealthy(): Promise<void> {
    const response = await fetch(`${this.origin}/api/health`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${this.token}`,
        Origin: this.origin,
      },
      cache: 'no-store',
      signal: AbortSignal.timeout(2_000),
    });
    if (!response.ok) throw new Error(`HELPER_HEALTH_${response.status}`);
    const body = (await response.json()) as { status?: string; protocol?: number };
    if (body.status !== 'ok' || body.protocol !== GATE0_PROTOCOL) {
      throw new Error('HELPER_HEALTH_PAYLOAD');
    }
  }

  stop(timeoutMs = 2_000): Promise<void> {
    this.stopPromise ??= this.stopInternal(timeoutMs);
    return this.stopPromise;
  }

  private async stopInternal(timeoutMs: number): Promise<void> {
    if (hasExited(this.child)) return;
    try {
      this.child.stdin.end(
        `${JSON.stringify({ type: 'shutdown', protocol: GATE0_PROTOCOL })}\n`,
      );
    } catch {
      // If stdin already closed, the exit/kill path below remains authoritative.
    }
    if (await waitForExit(this.child, timeoutMs)) return;
    await terminateChild(this.child, timeoutMs);
  }
}
