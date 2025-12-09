"""
AudioCapture: non-blocking capture using sounddevice.InputStream.
Writes float32 interleaved frames (shape: frames x channels) as numpy arrays into out_q.
"""

from __future__ import annotations
import threading
import numpy as np
import queue
import traceback

try:
    import sounddevice as sd
except Exception as e:
    sd = None
    # We'll raise at start() if missing

class AudioCapture:
    def __init__(self, out_q: queue.Queue, rate=48000, channels=2, chunk=4096, device=None):
        """
        out_q: queue.Queue() - consumer takes np.ndarray (shape=(frames,channels), dtype=float32)
        device: device name or index (optional)
        """
        self.out_q = out_q
        self.rate = int(rate)
        self.channels = int(channels)
        self.chunk = int(chunk)
        self.device = device
        self.stream = None
        self._running = False
        self._thread = None

    def _callback(self, indata, frames, time_info, status):
        try:
            if status:
                # keep lightweight
                print("[capture] status:", status)
            # ensure float32 contiguous
            arr = np.array(indata, dtype=np.float32, copy=True)
            try:
                self.out_q.put_nowait(arr)
            except queue.Full:
                # drop if the consumer is slow; that's better than blocking audio callback
                pass
        except Exception:
            print("[capture] callback error:")
            traceback.print_exc()

    def start(self):
        if sd is None:
            raise RuntimeError("sounddevice not available; install sounddevice in your venv")

        if self._running:
            return

        try:
            self.stream = sd.InputStream(
                samplerate=self.rate,
                channels=self.channels,
                blocksize=self.chunk,
                device=self.device,
                dtype="float32",
                callback=self._callback,
            )
            self.stream.start()
            self._running = True
            print(f"[capture] started input stream device={self.device!r} rate={self.rate} chunk={self.chunk}")
        except Exception as e:
            raise RuntimeError(f"[capture] failed to start InputStream: {e}")

    def stop(self):
        try:
            if self.stream:
                self.stream.stop()
                self.stream.close()
            self._running = False
            print("[capture] stopped")
        except Exception:
            pass

