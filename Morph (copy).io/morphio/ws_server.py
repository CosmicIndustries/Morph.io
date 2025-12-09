"""
WSServer: asyncio-based websockets server that broadcasts spectrogram snapshots and optionally audio frames.
- frame_q and spec_q are queue.Queue instances (thread producers).
- Uses run_in_executor to wait on queue.get() without blocking the event loop.
"""
from __future__ import annotations
import asyncio
import json
import queue
import numpy as np
import threading
from websockets import serve
from websockets.exceptions import ConnectionClosedOK, ConnectionClosedError

class WSServer:
    def __init__(self, host="127.0.0.1", port=8766, frame_q: queue.Queue | None = None, spec_q: queue.Queue | None = None, json_audio=False):
        """
        json_audio: if True, audio frames are converted to lists and sent in JSON (heavy).
                    if False, only spectrograms are broadcast. (default False)
        """
        self.host = host
        self.port = int(port)
        self.frame_q = frame_q
        self.spec_q = spec_q
        self.json_audio = bool(json_audio)
        self._clients: set = set()
        self._stop = False
        self._server_task = None

    async def handler(self, websocket, path):
        # register client
        self._clients.add(websocket)
        print(f"[WS] client connected ({len(self._clients)} total)")
        try:
            async for msg in websocket:
                # we accept simple JSON commands from the UI that can be extended
                try:
                    cmd = json.loads(msg)
                    # e.g., {"command":"ping"}
                    if isinstance(cmd, dict) and cmd.get("command") == "ping":
                        await websocket.send(json.dumps({"status": "pong"}))
                except Exception:
                    # ignore unknown or non-json messages
                    pass
        except (ConnectionClosedOK, ConnectionClosedError):
            pass
        finally:
            if websocket in self._clients:
                self._clients.remove(websocket)
            print(f"[WS] client disconnected ({len(self._clients)} remaining)")

    async def _broadcaster(self):
        """Continuously read spec frames from spec_q and broadcast as JSON to clients."""
        loop = asyncio.get_running_loop()
        while not self._stop:
            try:
                if self.spec_q is None:
                    await asyncio.sleep(0.05)
                    continue
                # wait for next spec snapshot using thread executor
                spec = await loop.run_in_executor(None, self.spec_q.get)
                # ensure numpy -> plain python conversion
                if isinstance(spec, np.ndarray):
                    # spec shape: (freq_bins, history_len)
                    payload = {
                        "type": "spectrogram",
                        # convert to nested lists of floats; clamp to python floats
                        "data": spec.astype(float).tolist()
                    }
                else:
                    payload = {"type": "spectrogram", "data": spec}

                js = json.dumps(payload, allow_nan=False)
                # broadcast to all clients; iterate over a snapshot to avoid set size change issues
                clients = list(self._clients)
                for ws in clients:
                    try:
                        await ws.send(js)
                    except (ConnectionClosedOK, ConnectionClosedError):
                        # client disconnected; will be removed in handler
                        pass
                    except Exception:
                        # other errors: ignore single send failures
                        pass

            except Exception as e:
                # possibly queue cancellation or stop; print for diagnostics but continue
                # print("[WSServer] broadcaster exception:", e)
                await asyncio.sleep(0.05)

    async def run_server(self):
        """Start websocket server and broadcaster. Blocks until stop() is called."""
        async with serve(self.handler, self.host, self.port):
            print(f"[WS] WebSocket server running on ws://{self.host}:{self.port}")
            # run broadcaster until cancelled
            try:
                await self._broadcaster()
            except asyncio.CancelledError:
                pass

    def start_thread(self):
        """Start the asyncio server in a dedicated thread (not the recommended usage)."""
        # prefer calling asyncio.run(ws.run_server()) in main thread; but support threaded start
        def _thread():
            asyncio.run(self.run_server())
        t = threading.Thread(target=_thread, daemon=True)
        t.start()
        return t

    def stop(self):
        self._stop = True

