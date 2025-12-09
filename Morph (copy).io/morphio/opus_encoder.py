# morphio/opus_encoder.py
# Lightweight wrapper around pyogg OpusEncoder
import io
import numpy as np
try:
    from pyogg import OpusEncoder
except Exception as e:
    raise RuntimeError("pyogg is required for Opus encoding") from e

class OpusEncoderWrapper:
    def __init__(self, channels=2, rate=48000, application="audio", frame_size=960):
        """
        frame_size: samples per channel per frame (default 20ms @ 48k = 960)
        """
        self.rate = rate
        self.channels = channels
        self.frame_size = frame_size
        self.encoder = OpusEncoder()
        self.encoder.set_application(application)
        self.encoder.set_sampling_frequency(rate)
        self.encoder.set_channels(channels)
        # set bitrate if you want: self.encoder.set_bitrate(64000)

    def encode_frame(self, arr: np.ndarray) -> bytes:
        """
        arr: numpy float32 array shaped (n,channels) or 1D interleaved
        returns raw opus packet bytes (not Ogg container)
        """
        a = np.asarray(arr, dtype=np.float32)
        if a.ndim == 2:
            # expect shape (frame_size, channels)
            interleaved = a.reshape(-1).astype(np.float32).tobytes()
        else:
            interleaved = a.astype(np.float32).tobytes()
        # pyogg expects int16 PCM by default; we'll convert
        ints = (np.asarray(a * 32767.0, dtype=np.int16)).tobytes()
        packet = self.encoder.encode(ints, self.frame_size)
        return packet

