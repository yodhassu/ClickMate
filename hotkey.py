"""Hold Ctrl+Alt+Space to talk. Observe-only: other apps still receive the keys."""
from pynput import keyboard

_CTRL = {keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r}
_ALT = {keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt_gr}


class PushToTalk:
    def __init__(self, on_press, on_release):
        self._on_press = on_press
        self._on_release = on_release
        self._held = set()
        self._active = False
        self._listener = None

    def _combo_down(self):
        return (self._held & _CTRL) and (self._held & _ALT) and keyboard.Key.space in self._held

    def _press(self, key):
        self._held.add(key)
        if not self._active and self._combo_down():
            self._active = True
            self._on_press()

    def _release(self, key):
        self._held.discard(key)
        if self._active and not self._combo_down():
            self._active = False
            self._on_release()

    def start(self):
        # suppress=False is important: True would block every keystroke system-wide.
        self._listener = keyboard.Listener(on_press=self._press, on_release=self._release, suppress=False)
        self._listener.start()
