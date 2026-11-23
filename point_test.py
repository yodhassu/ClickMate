"""Test pointing WITHOUT voice, so you can tell whether the problem is the arrow or the model.

  python point_test.py --ui
      No model involved. The blue arrow flies to 4 spots on your screen.
      If this works, the overlay is fine.

  python point_test.py "where is the start button"
      You get 4 seconds to switch to the window you want analysed. Then it takes a screenshot,
      asks Ollama, prints what the model picked, saves debug images (grid_stage*.jpg for Ollama, pointer_result.jpg for Gemini),
      and flies the arrow to the result.
"""
import sys
import threading

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import QApplication

import capture
import config
import locator
import providers
from overlay import Overlay


class Bridge(QObject):
    point = pyqtSignal(float, float)
    notice = pyqtSignal(str)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    app = QApplication(sys.argv)
    overlay = Overlay()
    bridge = Bridge()
    bridge.point.connect(overlay.point_at)
    bridge.notice.connect(overlay.notice)

    if sys.argv[1] == "--ui":
        spots = [("CENTER", 0.5, 0.5), ("TOP-LEFT", 0.1, 0.1), ("TOP-RIGHT", 0.9, 0.1),
                 ("BOTTOM-RIGHT", 0.9, 0.9), ("BOTTOM-LEFT", 0.1, 0.9)]

        def go(name, fx, fy):
            print("flying to", name)
            overlay.set_status("Pointer test - the arrow should be at:")
            overlay.set_answer(name)
            overlay.point_at(fx, fy)

        for i, (name, fx, fy) in enumerate(spots):
            QTimer.singleShot(1000 + i * 3000, lambda n=name, x=fx, y=fy: go(n, x, y))
        QTimer.singleShot(1000 + len(spots) * 3000 + 3000, app.quit)
        return app.exec()

    question = " ".join(sys.argv[1:])
    print(f'Question: "{question}"\nSwitch to the window you want analysed - capturing in 4 seconds...')

    def work():
        image, _ = capture.grab_primary()
        client = providers.make_client()
        print(f"Using {client.label}")
        problems = client.check()
        if problems:
            print("\n".join(problems))
            bridge.notice.emit(problems[0])
            return
        spot = locator.locate(client, image, question, debug_dir=config.ROOT / "debug", allow_none=False)
        print("Result (fractions of the screen):", spot)
        if spot:
            bridge.point.emit(*spot)
        else:
            bridge.notice.emit("The model could not pick a cell - see the console")
        QTimer.singleShot(0, lambda: None)

    QTimer.singleShot(4000, lambda: threading.Thread(target=work, daemon=True).start())
    QTimer.singleShot(60000, app.quit)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
