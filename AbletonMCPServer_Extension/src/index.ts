import { WebSocketServer } from 'ws';
import { AudioClip, WarpMode } from '@ableton-extensions/sdk';
import { getExtensionContext } from './context.js';

let wss: WebSocketServer | null = null;

class RpcDomainError extends Error {
  constructor(
    public readonly domainCode: string,
    message: string,
    public readonly hint?: string,
  ) {
    super(message);
  }
}

function rpcError(error: unknown, id: any): { jsonrpc: string; error: unknown; id: any } {
  if (error instanceof RpcDomainError) {
    return {
      jsonrpc: "2.0",
      id,
      error: {
        code: -32000,
        message: error.message,
        data: { code: error.domainCode, hint: error.hint },
      },
    };
  }
  const message = error instanceof Error ? error.message : String(error);
  return {
    jsonrpc: "2.0",
    id,
    error: { code: -32603, message },
  };
}

const WARP_MODE_MAP: Record<string, number> = {
  "beats": WarpMode.Beats,
  "tones": WarpMode.Tones,
  "texture": WarpMode.Texture,
  "re-pitch": WarpMode.Repitch,
  "complex": WarpMode.Complex,
  "complex_pro": WarpMode.ComplexPro,
};

const REVERSE_WARP_MODE_MAP: Record<number, string> = {
  [WarpMode.Beats]: "beats",
  [WarpMode.Tones]: "tones",
  [WarpMode.Texture]: "texture",
  [WarpMode.Repitch]: "re-pitch",
  [WarpMode.Complex]: "complex",
  [WarpMode.ComplexPro]: "complex_pro",
};

function getTrackAtIndex(song: any, index: number) {
  const tracks = song.tracks;
  const returnTracks = song.returnTracks;
  const masterTrack = song.mainTrack;
  const allTracks = [...tracks, ...returnTracks, masterTrack];
  if (index < 0 || index >= allTracks.length) {
    throw new Error(`Track index ${index} out of range`);
  }
  return allTracks[index]!;
}

async function handleGetWarpState(params: any) {
  const context = getExtensionContext();
  if (!context) throw new Error("Extension SDK not initialized");

  const song = context.application.song;
  const track = getTrackAtIndex(song, params.track_index);
  if (params.clip_index < 0 || params.clip_index >= track.clipSlots.length) {
    throw new Error(`Clip slot index ${params.clip_index} out of range`);
  }
  const slot = track.clipSlots[params.clip_index]!;
  const clip = slot.clip;
  if (!clip) {
    throw new Error(`Clip slot is empty`);
  }

  let audioClip: AudioClip<any>;
  try {
    audioClip = context.getObjectFromHandle(clip.handle, AudioClip);
  } catch (err) {
    throw new Error("Clip is not an audio clip");
  }

  const modeStr = REVERSE_WARP_MODE_MAP[audioClip.warpMode] || "unknown";
  const markers = (audioClip.warpMarkers || []).map((m) => ({
    sample_time: m.sampleTime,
    beat_time: m.beatTime,
  }));

  return {
    warping: audioClip.warping,
    warp_mode: modeStr,
    warp_markers: markers,
  };
}

async function handleSetWarpState(params: any) {
  const context = getExtensionContext();
  if (!context) throw new Error("Extension SDK not initialized");

  const song = context.application.song;
  const track = getTrackAtIndex(song, params.track_index);
  if (params.clip_index < 0 || params.clip_index >= track.clipSlots.length) {
    throw new Error(`Clip slot index ${params.clip_index} out of range`);
  }
  const slot = track.clipSlots[params.clip_index]!;
  const clip = slot.clip;
  if (!clip) {
    throw new Error(`Clip slot is empty`);
  }

  let audioClip: AudioClip<any>;
  try {
    audioClip = context.getObjectFromHandle(clip.handle, AudioClip);
  } catch (err) {
    throw new Error("Clip is not an audio clip");
  }

  // Group multiple LOM writes in one transaction
  await context.withinTransaction(() => {
    if (params.warping !== undefined) {
      audioClip.warping = params.warping;
    }
    if (params.warp_mode !== undefined) {
      const modeVal = WARP_MODE_MAP[params.warp_mode];
      if (modeVal === undefined) {
        throw new Error(`Invalid warp mode: ${params.warp_mode}`);
      }
      audioClip.warpMode = modeVal;
    }
  });

  return {
    status: "ok",
    warping: audioClip.warping,
    warp_mode: REVERSE_WARP_MODE_MAP[audioClip.warpMode] || "unknown",
  };
}

async function handleLoadDeviceToTrack(params: any) {
  const context = getExtensionContext();
  if (!context) throw new Error("Extension SDK not initialized");

  const song = context.application.song;
  const track = getTrackAtIndex(song, params.track_index);
  const index = track.devices.length;
  
  // Insert device at the end of the device chain
  const device = await track.insertDevice(params.device_uri, index);

  return {
    status: "loaded",
    device_name: device.name,
    device_index: index,
  };
}

export function startServer(): void {
  if (wss) return;

  wss = new WebSocketServer({ port: 9889 });

  wss.on('connection', (ws) => {
    console.log('[Extension WS] Client connected');

    ws.on('message', async (message) => {
      let request: any;
      try {
        request = JSON.parse(message.toString());
      } catch (err) {
        ws.send(JSON.stringify({
          jsonrpc: "2.0",
          error: { code: -32700, message: "Parse error" },
          id: null
        }));
        return;
      }

      const { method, params, id } = request;
      console.log(`[Extension WS] Request method: ${method}, id: ${id}`);

      try {
        let result: any;
        if (method === 'get_warp_state') {
          result = await handleGetWarpState(params);
        } else if (method === 'set_warp_state') {
          result = await handleSetWarpState(params);
        } else if (method === 'load_device_to_track') {
          result = await handleLoadDeviceToTrack(params);
        } else {
          ws.send(JSON.stringify({
            jsonrpc: "2.0",
            error: { code: -32601, message: "Method not found" },
            id
          }));
          return;
        }

        ws.send(JSON.stringify({
          jsonrpc: "2.0",
          result,
          id
        }));
      } catch (err: any) {
        console.error(`[Extension WS] Error executing method ${method}:`, err);
        ws.send(JSON.stringify(rpcError(err, id)));
      }
    });

    ws.on('close', () => {
      console.log('[Extension WS] Client disconnected');
    });
  });

  console.log('[Extension WS] Server started on port 9889');
}

export async function stopServer(): Promise<void> {
  if (!wss) return;

  return new Promise<void>((resolve, reject) => {
    wss!.close((err) => {
      if (err) {
        reject(err);
      } else {
        wss = null;
        resolve();
      }
    });
  });
}
