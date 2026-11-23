"""Clicky Mini - a voice-driven, screen-aware helper for Windows.

Hold Ctrl+Alt+Space, ask a question, release.
  listen  : whisper.cpp (offline)
  think   : Ollama vision model (local)  OR  Google Gemini (cloud, free key) - your choice
  speak   : Windows built-in voice (SAPI5)
  show    : answer text panel + a blue companion that follows your cursor and points
"""
import ctypes
import os
import sys
import threading
import traceback

import requests
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QActionGroup, QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

import capture
import config
import locator
import llm
import providers
import stt
from audio import Recorder
from hotkey import PushToTalk
from overlay import Overlay
from textutil import clean_for_speech, split_sentences, wants_pointer
from tts import Speaker


class Bridge(QObject):
    """Lets worker threads talk to the GUI thread safely."""
    listening = pyqtSignal(bool)        # mic is open
    status = pyqtSignal(str)            # panel header line ("" hides the panel)
    answer = pyqtSignal(str)            # panel body: the answer so far
    answer_done = pyqtSignal()
    notice = pyqtSignal(str)            # temporary message (errors, hints)
    point = pyqtSignal(float, float)    # fractions of the screen
    clear = pyqtSignal()                # new question: reset everything


class Clicky:
    def __init__(self, bridge: Bridge):
        self.bridge = bridge
        self.llm = providers.make_client()     # Ollama or Gemini, see config.PROVIDER
        self.recorder = Recorder()
        self.speaker = Speaker()
        self.history = []        # [{"role":..., "content":...}] text only
        self._turn = 0           # bumps on every new hotkey press so stale work can be dropped

    def set_provider(self, name: str):
        """Switch brain at runtime (tray menu). The slow health check runs off the GUI thread
        and reports through the panel."""
        self.llm = providers.make_client(name)
        config.save_provider(name)
        client = self.llm
        print(f"[clicky] now using {client.label}")

        def verify():
            client.warmup()
            problems = client.check()
            for problem in problems:
                print(problem)
            self.bridge.notice.emit(problems[0] if problems else f"Now using {client.label}")

        threading.Thread(target=verify, daemon=True).start()

    # ---- hotkey callbacks (run on the keyboard thread) ----
    def on_press(self):
        self._turn += 1
        self.speaker.stop()
        self.bridge.clear.emit()          # hides the old answer BEFORE we take the screenshot
        try:
            self.recorder.start()
            self.bridge.listening.emit(True)
        except Exception as exc:
            self.bridge.notice.emit(f"Microphone error: {exc}")

    def on_release(self):
        self.bridge.listening.emit(False)
        try:
            wav = self.recorder.stop()
            if wav is None:
                return
            shot = capture.grab_primary()     # grab the screen NOW, before the user moves on
        except Exception as exc:
            self.bridge.notice.emit(f"Capture error: {exc}")
            return
        self._save_debug_screenshot(shot[0])
        threading.Thread(target=self._pipeline, args=(wav, shot, self._turn), daemon=True).start()

    @staticmethod
    def _save_debug_screenshot(image):
        """Keeps the last image sent to the model, so you can check what it really saw."""
        try:
            folder = config.ROOT / "debug"
            folder.mkdir(exist_ok=True)
            llm.downscale(image).save(folder / "last_screenshot.jpg", quality=80)
        except Exception:
            pass

    def _point(self, image, question, alive, must_find=False):
        """Returns True if the blue cursor was sent somewhere."""
        spot = locator.locate(self.llm, image, question,
                              debug_dir=config.ROOT / "debug", allow_none=not must_find)
        print(f"[clicky] pointer target (fractions of screen): {spot}")
        if spot and alive():
            self.bridge.point.emit(spot[0], spot[1])
            return True
        return False

    # ---- the pipeline (runs on a worker thread) ----
    def _pipeline(self, wav, shot, turn):
        alive = lambda: turn == self._turn
        image, _monitor = shot
        try:
            self.bridge.status.emit("Transcribing...")
            question = stt.transcribe(wav)
            if not alive():
                return
            if not question:
                self.bridge.notice.emit("Didn't catch that - try again")
                return

            self.bridge.status.emit(f"You: {question}")
            point_first = wants_pointer(question)     # "where is...", "what do I click..."
            note = ""
            if point_first:
                self.bridge.answer.emit("Looking for it...")
                found = self._point(image, question, alive, must_find=True)
                if not alive():
                    return
                if not found:
                    note = "\n\n(I couldn't work out where to point - check the console.)"
            self.bridge.answer.emit("Thinking...")

            n = config.HISTORY_TURNS
            earlier = self.history[-2 * n:] if n > 0 else []
            messages = (
                [{"role": "system", "content": config.SYSTEM_PROMPT}]
                + earlier
                + [{"role": "user",
                    "content": f"This is a screenshot of my screen right now. {question}",
                    "images": [llm.pil_to_b64(llm.downscale(image))]}]
            )

            full, buffer = "", ""
            for piece in self.llm.stream_chat(messages):
                if not alive():
                    return
                full += piece
                buffer += piece
                self.bridge.answer.emit(full.strip() + note)
                sentences, buffer = split_sentences(buffer)
                for sentence in sentences:
                    self.speaker.say(clean_for_speech(sentence))
            if buffer.strip() and alive():
                self.speaker.say(clean_for_speech(buffer))

            if not alive():
                return
            if not full.strip():
                self.bridge.notice.emit("The model returned an empty answer.")
                return
            self.bridge.answer.emit(full.strip() + note)
            self.bridge.answer_done.emit()
            self.history += [{"role": "user", "content": question},
                             {"role": "assistant", "content": full.strip()}]

            if not point_first:
                self._point(image, question, alive)
        except requests.ConnectionError:
            hint = "is it running?" if self.llm.name == "ollama" else "check your internet."
            self.bridge.notice.emit(f"Can't reach {self.llm.label} - {hint}")
        except Exception as exc:
            traceback.print_exc()
            self.bridge.notice.emit(f"Error: {exc}")
        finally:
            try:
                os.remove(wav)
            except OSError:
                pass


def already_running() -> bool:
    """Named mutex so a second copy doesn't create duplicate hotkey listeners."""
    if os.name != "nt":
        return False
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CreateMutexW(None, False, "Local\\ClickyMini-SingleInstance")
    return kernel32.GetLastError() == 183   # ERROR_ALREADY_EXISTS


def tray_icon() -> QIcon:
    pix = QPixmap(32, 32)
    pix.fill(QColor(0, 0, 0, 0))
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(37, 99, 235))
    p.setPen(QColor("white"))
    p.drawEllipse(3, 3, 26, 26)
    p.end()
    return QIcon(pix)


def main():
    if already_running():
        print("Clicky Mini is already running (check the system tray).")
        return 0

    problems = stt.check_installed()
    if problems:
        print("\n".join(problems))
        return 1

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    overlay = Overlay()

    bridge = Bridge()
    bridge.listening.connect(overlay.listening)
    bridge.status.connect(overlay.set_status)
    bridge.answer.connect(overlay.set_answer)
    bridge.answer_done.connect(overlay.answer_done)
    bridge.notice.connect(overlay.notice)
    bridge.point.connect(overlay.point_at)
    bridge.clear.connect(overlay.clear)

    clicky = Clicky(bridge)

    tray = QSystemTrayIcon(tray_icon(), app)
    menu = QMenu()
    group = QActionGroup(menu)
    group.setExclusive(True)
    choices = {"ollama": "AI: Ollama (local, offline)", "gemini": "AI: Gemini (cloud, free key)"}
    for name, text in choices.items():
        action = menu.addAction(text)
        action.setCheckable(True)
        action.setChecked(clicky.llm.name == name)
        group.addAction(action)

        action.triggered.connect(lambda _checked=False, name=name: clicky.set_provider(name))
    menu.addSeparator()
    menu.addAction("Quit Clicky Mini", app.quit)
    tray.setContextMenu(menu)
    tray.setToolTip("Clicky Mini - hold Ctrl+Alt+Space to talk")
    tray.show()

    print(f"[clicky] AI provider: {clicky.llm.label}  (switch from the tray icon or set CLICKY_PROVIDER)")
    for problem in clicky.llm.check():
        print(problem)
        overlay.notice(problem, 8)
    threading.Thread(target=clicky.llm.warmup, daemon=True).start()

    PushToTalk(clicky.on_press, clicky.on_release).start()
    print("Clicky Mini is running. Hold Ctrl+Alt+Space to talk. Quit from the tray icon.")
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
