#!/usr/bin/env python3
"""
run_morphio.py
Launcher that wires capture -> processor -> ws server -> http UI.
Runs websockets server on asyncio in the main thread (no "no running event loop" errors).
"""
import os
import time
import queue
import threading
import asyncio
import signal
from pathlib import Path

# local modules
from morphio.audio_capture import AudioCapture
from morphio.audio_processor import AudioProcessor
from morphio.ws_server import WSServer
from morphio.http_server import HttpServer

ROOT = Path(__file__).parent.resolve()
UI_ROOT = ROOT / "sarpedon"

print("[Morphio] Booting…")

# shared queues
capture_q = queue.Queue(maxsize=8)   # raw float32 chunks from capture (np.ndarray)
proc_q    = queue.Queue(maxsize=8)   # processed audio frames (if used)
spec_q    = queue.Queue(maxsize=8)   # spectrogram matrix snapshots (numpy arrays or lists)

# detect a monitor device (PipeWire/pulse monitor)
def find_monitor_device():
    try:
        import sounddevice as sd  # local import so script still loads if not available
        devs = sd.query_devices()
        for d in devs:
            name = d.get("name", "").lower()
            if "monitor" in name or "pipewire" in name or "loopback" in name:
                return d["name"]
    except Exception as exc:
        print("[run_morphio] device query failed:", exc)
    return None

monitor_device = find_monitor_device()
if monitor_device is None:
    print("[run_morphio] No explicit monitor device found; capture will use default input.")
else:
    print(f"[run_morphio] Using monitor device: {monitor_device!r}")

# 1) Start capture thread (writes numpy float32 arrays into capture_q)
cap = AudioCapture(out_q=capture_q, rate=48000, channels=2, chunk=4096, device=monitor_device)
cap.start()

# 2) Start audio processor thread (reads from capture_q, writes to proc_q and spec_q)
processor = AudioProcessor(in_q=capture_q, out_q=proc_q, spec_q=spec_q, sr=48000, n_fft=4096, history_len=128)
processor_thread = threading.Thread(target=processor.start, daemon=True)
processor_thread.start()
print("[processor] running…")

# 3) Start threaded HTTP server serving ./sarpedon
http = HttpServer(host="127.0.0.1", port=8080, ui_root=str(UI_ROOT))
http.start()
print(f"[HTTP] Serving UI on http://127.0.0.1:8080/index.html")

# 4) Start websocket server (async — run in main loop)
ws = WSServer(host="127.0.0.1", port=8766, frame_q=proc_q, spec_q=spec_q, json_audio=False)

# graceful shutdown helpers
stop_event = threading.Event()

def _shutdown(signum=None, frame=None):
    print("[Morphio] shutdown requested")
    stop_event.set()
    try:
        cap.stop()
    except Exception:
        pass
    try:
        processor.stop()
    except Exception:
        pass
    try:
        http.stop()
    except Exception:
        pass
    # WSServer exposes stop() used by run_server when cancelled
    try:
        ws.stop()
    except Exception:
        pass

signal.signal(signal.SIGINT, _shutdown)
signal.signal(signal.SIGTERM, _shutdown)

# Run asyncio server in the main thread
async def main_async():
    # start ws server and broadcaster; this method returns when cancelled
    await ws.run_server()  # blocks until stop() invoked or Ctrl-C

if __name__ == "__main__":
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        _shutdown()
    except Exception as e:
        print("[run_morphio] main exception:", e)
        _shutdown()
    finally:
        # wait a little for threads to stop cleanly
        time.sleep(0.3)
        print("[Morphio] exited")

