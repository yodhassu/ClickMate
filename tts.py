"""Text-to-speech with the default Windows voice (SAPI5), no downloads, no keys.

A worker thread owns the COM voice object (COM objects must stay on one thread).
Sentences are queued so the first one is spoken while the model is still writing the rest.
"""
import queue
import threading

import config

SVS_ASYNC = 1
SVS_ASYNC_PURGE = 3   # async + purge-before-speak: cuts off current speech


class Speaker:
    def __init__(self):
        self._queue = queue.Queue()
        self._cancel = threading.Event()
        self._generation = 0
        threading.Thread(target=self._run, daemon=True).start()

    def say(self, text: str):
        if text.strip():
            self._queue.put((self._generation, text))

    def stop(self):
        """Drop queued sentences and interrupt the one being spoken."""
        self._generation += 1
        self._cancel.set()
        try:
            while True:
                self._queue.get_nowait()
        except queue.Empty:
            pass

    def _run(self):
        try:
            import pythoncom
            import win32com.client
            pythoncom.CoInitialize()
            voice = win32com.client.Dispatch("SAPI.SpVoice")
            voice.Rate = config.TTS_RATE
            voice.Volume = config.TTS_VOLUME
        except Exception as exc:   # not on Windows / pywin32 missing
            print(f"[tts] Windows speech unavailable ({exc}); text will only be printed.")
            voice = None

        while True:
            generation, text = self._queue.get()
            self._cancel.clear()
            if generation != self._generation:
                continue
            if voice is None:
                print(f"[clicky] {text}")
                continue
            voice.Speak(text, SVS_ASYNC)
            while not voice.WaitUntilDone(100):
                if self._cancel.is_set():
                    voice.Speak("", SVS_ASYNC_PURGE)
                    break
