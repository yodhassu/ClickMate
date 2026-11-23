"""On-screen visuals, all click-through and always on top:

  Companion - a small blue arrow that follows your mouse cursor. When Clicky points at
              something it flies there (tip on the target), pulses, then flies back to you.
  Panel     - a rounded text box at the bottom of the screen showing what you asked and the
              answer as it streams in.
  Overlay   - tiny facade the app talks to.

Both widgets are small, so moving them is cheap (no full-screen repainting).
"""
import math

from PyQt6.QtCore import QObject, QPointF, QRect, QRectF, Qt, QTimer
from PyQt6.QtGui import QBrush, QColor, QCursor, QFont, QFontMetrics, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import QApplication, QWidget

import config

BLUE = QColor(37, 99, 235)
FLAGS = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
         | Qt.WindowType.Tool | Qt.WindowType.WindowTransparentForInput
         | Qt.WindowType.WindowDoesNotAcceptFocus)

SIZE = 100   # companion widget size
TIP = 40     # the arrow tip (and pulse ring centre) sits at (TIP, TIP) inside the widget

WRAP = Qt.TextFlag.TextWordWrap.value
LEFT = Qt.AlignmentFlag.AlignLeft.value
VCENTER = Qt.AlignmentFlag.AlignVCenter.value


def _ghost(widget: QWidget):
    widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    widget.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)


class Companion(QWidget):
    def __init__(self):
        super().__init__(None, FLAGS)
        _ghost(self)
        self.resize(SIZE, SIZE)
        self._pos = QPointF(QCursor.pos())
        self._target = None          # QPointF (global logical px) where the tip should land
        self._listening = False
        self._phase = 0.0
        self._dirty = True
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    def fly_to(self, x: float, y: float):
        self._target = QPointF(x, y)

    def follow(self):
        self._target = None

    def set_listening(self, on: bool):
        self._listening = on
        self._dirty = True

    def _tick(self):
        if self._target is None:
            cur = QCursor.pos()
            desired = QPointF(cur.x() - 18, cur.y() - 18)       # tip rests just below-right of the cursor
            ease = 0.35
        else:
            desired = QPointF(self._target.x() - TIP, self._target.y() - TIP)
            ease = 0.12
        delta = desired - self._pos
        if abs(delta.x()) > 0.3 or abs(delta.y()) > 0.3:
            self._pos = self._pos + delta * ease
            self.move(round(self._pos.x()), round(self._pos.y()))
        if self._target is not None or self._listening:
            self._phase = (self._phase + (0.2 if self._listening else 0.09)) % (2 * math.pi)
            self.update()
            self._dirty = True
        elif self._dirty:
            self._dirty = False
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._target is not None or self._listening:
            pulse = 0.5 + 0.5 * math.sin(self._phase)
            radius = 20 + 14 * pulse
            color = QColor(239, 68, 68) if self._listening else BLUE
            p.setBrush(Qt.BrushStyle.NoBrush)
            c = QColor(color)
            c.setAlpha(int(210 - 120 * pulse))
            p.setPen(QPen(c, 3))
            p.drawEllipse(QPointF(TIP, TIP), radius, radius)
        arrow = QPolygonF([QPointF(TIP, TIP), QPointF(TIP + 15, TIP + 34),
                           QPointF(TIP + 21, TIP + 21), QPointF(TIP + 36, TIP + 18)])
        p.setPen(QPen(QColor("white"), 2))
        p.setBrush(QBrush(BLUE))
        p.drawPolygon(arrow)


class Panel(QWidget):
    MAX_WIDTH = 700
    PAD = 20

    def __init__(self):
        super().__init__(None, FLAGS)
        _ghost(self)
        self.header = ""
        self.body = ""
        self._body_font = QFont("Segoe UI", 12)
        self._head_font = QFont("Segoe UI", 10, QFont.Weight.DemiBold)
        self._head_h = 0
        self._body_h = 0
        self._gap = 0

    def set_text(self, header: str, body: str):
        self.header, self.body = header, body
        if not header and not body:
            self.hide()
            return
        screen = QApplication.primaryScreen().geometry()
        width = min(self.MAX_WIDTH, screen.width() - 80)
        inner = width - 2 * self.PAD
        self._head_h = QFontMetrics(self._head_font).height() if header else 0
        self._body_h = (QFontMetrics(self._body_font)
                        .boundingRect(QRect(0, 0, inner, 10000), WRAP, body).height() if body else 0)
        self._gap = 6 if (header and body) else 0
        height = 2 * 14 + self._head_h + self._gap + self._body_h
        self.setGeometry(screen.x() + (screen.width() - width) // 2,
                         screen.y() + screen.height() - height - 110, width, height)
        self.show()
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(20, 22, 32, 235))
        p.drawRoundedRect(QRectF(self.rect()), 16, 16)
        inner = self.width() - 2 * self.PAD
        y = 14
        if self.header:
            p.setFont(self._head_font)
            p.setPen(QColor(147, 197, 253))
            p.drawText(QRectF(self.PAD, y, inner, self._head_h), LEFT | VCENTER, self.header)
            y += self._head_h + self._gap
        if self.body:
            p.setFont(self._body_font)
            p.setPen(QColor("white"))
            p.drawText(QRectF(self.PAD, y, inner, self._body_h + 4), LEFT | WRAP, self.body)


class Overlay(QObject):
    def __init__(self):
        super().__init__()
        self.companion = Companion()
        self.panel = Panel()
        self.companion.show()

        self._point_timer = QTimer(self)
        self._point_timer.setSingleShot(True)
        self._point_timer.timeout.connect(self.clear_point)
        self._panel_timer = QTimer(self)
        self._panel_timer.setSingleShot(True)
        self._panel_timer.timeout.connect(lambda: self.panel.set_text("", ""))

    # ---- what the app calls ----
    def listening(self, on: bool):
        self.companion.set_listening(on)

    def set_status(self, header: str):
        """Header line (e.g. what you asked). Clears the body. Empty text hides the panel."""
        self._panel_timer.stop()
        self.panel.set_text(header, "")

    def set_answer(self, body: str):
        self.panel.set_text(self.panel.header, body)

    def answer_done(self):
        seconds = 6 + len(self.panel.body) / 14      # longer answers stay longer
        self._panel_timer.start(int(seconds * 1000))

    def notice(self, text: str, seconds: int = 5):
        self._panel_timer.stop()
        self.panel.set_text("", text)
        self._panel_timer.start(seconds * 1000)

    def point_at(self, fx: float, fy: float):
        """fx, fy: position as fractions of the primary screen (the screenshot area)."""
        geo = QApplication.primaryScreen().geometry()
        self.companion.fly_to(geo.x() + fx * geo.width(), geo.y() + fy * geo.height())
        self._point_timer.start(config.POINT_SECONDS * 1000)

    def clear_point(self):
        self.companion.follow()

    def clear(self):
        """New question started: hide the old answer and return the companion to the cursor."""
        self._point_timer.stop()
        self._panel_timer.stop()
        self.companion.follow()
        self.panel.set_text("", "")
