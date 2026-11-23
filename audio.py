"""Push-to-talk microphone recorder: 16 kHz mono 16-bit WAV, which is what whisper.cpp wants."""
import os
import tempfile
import wave

import numpy as np
import sounddevice as sd

import config

SAMPLE_RATE = 16000


class Recorder:
    def __init__(self):
        self._chunks = []
        self._stream = None

    def start(self):
        self._chunks = []
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="int16",
            callback=lambda indata, frames, t, status: self._chunks.append(indata.copy()),
        )
        self._stream.start()

    def stop(self):
        """Stop recording. Returns the WAV path, or None if the clip was too short."""
        if self._stream is None:
            return None
        self._stream.stop()
        self._stream.close()
        self._stream = None
        if not self._chunks:
            return None
        audio = np.concatenate(self._chunks)
        if len(audio) / SAMPLE_RATE < config.MIN_RECORD_SECONDS:
            return None
        fd, path = tempfile.mkstemp(suffix=".wav", prefix="clicky_")
        os.close(fd)
        with wave.open(path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio.tobytes())
        return path
