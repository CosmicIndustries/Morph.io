"""
AudioProcessor: read raw chunks from in_q, compute short-time spectral snapshot and put to spec_q.
Also forwards frames (optional) to out_q.
Designed to be run in its own thread.
"""
from __future__ import annotations
import threading
import queue
import numpy as np
from scipy.signal import get_window
import time

class AudioProcessor:
    def __init__(self, in_q: queue.Queue, out_q: queue.Queue | None = None, spec_q: queue.Queue | None = None,
                 sr=48000, n_fft=4096, history_len=128, window="hann", channels=2):
        self.in_q = in_q
        self.out_q = out_q
        self.spec_q = spec_q
        self.sr = int(sr)
        self.n_fft = int(n_fft)
        self.history_len = int(history_len)
        self.window = get_window(window, self.n_fft, fftbins=True)
        self.channels = channels
        self._running = False
        # rolling buffer: shape (freq_bins, history_len)
        self.freq_bins = self.n_fft // 2 + 1
        self._spec_buffer = np.full((self.freq_bins, self.history_len), -120.0, dtype=np.float32)
        self._lock = threading.Lock()

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _run(self):
        """Main processing loop: block on in_q.get(), compute spectrum, push to spec_q."""
        print("[processor] _run loop started")
        while self._running:
            try:
                frame = self.in_q.get(timeout=0.5)  # np.ndarray (frames, channels)
            except queue.Empty:
                continue

            # If interleaved stereo, convert to mono for spectrogram (simple mean)
            if isinstance(frame, np.ndarray):
                if frame.ndim == 2 and frame.shape[1] >= 2:
                    mono = frame[:, :self.channels].mean(axis=1)
                elif frame.ndim == 1:
                    mono = frame
                else:
                    # fallback: flatten
                    mono = frame.ravel()
                # If frame shorter than n_fft, pad
                if mono.shape[0] < self.n_fft:
                    mono = np.pad(mono, (0, max(0, self.n_fft - mono.shape[0])))
                else:
                    mono = mono[: self.n_fft]

                # apply window and rfft
                win = mono * self.window
                spec = np.fft.rfft(win, n=self.n_fft)
                mag = np.abs(spec) + 1e-12
                # convert to dBFS
                mag_db = 20.0 * np.log10(mag)
                # clamp to [-120, 0]
                mag_db = np.clip(mag_db, -120.0, 0.0).astype(np.float32)

                # rotate buffer and insert as newest column
                with self._lock:
                    self._spec_buffer = np.roll(self._spec_buffer, -1, axis=1)
                    self._spec_buffer[:, -1] = mag_db

                # push a copy of the current spec buffer to spec_q (non-blocking)
                if self.spec_q is not None:
                    try:
                        # copy to ensure producer reuses buffer safely
                        self.spec_q.put_nowait(self._spec_buffer.copy())
                    except queue.Full:
                        # drop slow updates
                        pass

                # forward raw frame if requested
                if self.out_q is not None:
                    try:
                        self.out_q.put_nowait(frame.copy())
                    except queue.Full:
                        pass

            else:
                # unexpected item type; ignore
                continue

        print("[processor] stopped")

