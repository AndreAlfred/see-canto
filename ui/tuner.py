"""
ui/tuner.py — Tachometer-style intonation needle gauge.

Vertical needle = in tune; leans left for flat, right for sharp. During a
glissando the nearest-note target hands off, so the needle sweeps to one edge
and flies back to the other ("shifting gears") — an emergent consequence of the
+/-50-cent nearest-note invariant, not a scripted animation.

update_pitch(hz) is called once per analysis frame; pass None for silence.
"""

import math

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPainter, QPen, QColor, QFont
from PySide6.QtWidgets import QWidget

from audio.intonation import IntonationTracker

_MAX_CENTS = 50.0      # full needle deflection
_MAX_DEGREES = 60.0    # ...maps to +/- 60 degrees from vertical


class TunerWidget(QWidget):
    """Needle gauge showing cents deviation from the nearest note."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tracker = IntonationTracker()
        self._mode = "light"
        self.setMinimumHeight(150)

    def update_pitch(self, frequency_hz: float | None) -> None:
        self._tracker.update(frequency_hz)
        self.update()  # schedule a repaint

    def set_theme_mode(self, mode: str) -> None:
        self._mode = mode
        self.update()

    # -- painting -----------------------------------------------------------
    def _colors(self) -> dict:
        if self._mode == "dark":
            return {"arc": QColor("#5c626b"), "tick": QColor("#5c626b"),
                    "needle": QColor("#e5573f"), "center": QColor("#3fbd72"),
                    "text": QColor("#e8eaed"), "green": QColor("#3fbd72"),
                    "muted": QColor("#9aa0a8")}
        return {"arc": QColor("#c9ccd1"), "tick": QColor("#a2a7ae"),
                "needle": QColor("#c0392b"), "center": QColor("#2e9e5b"),
                "text": QColor("#22252a"), "green": QColor("#2e9e5b"),
                "muted": QColor("#6b7078")}

    def _cents_to_angle_rad(self, cents: float) -> float:
        # 0 cents -> straight up; +cents (sharp) -> clockwise (right).
        clamped = max(-_MAX_CENTS, min(_MAX_CENTS, cents))
        return math.radians((clamped / _MAX_CENTS) * _MAX_DEGREES)

    def paintEvent(self, event) -> None:
        c = self._colors()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        pivot = QPointF(w / 2, h * 0.88)
        radius = min(w / 2.2, h * 0.78)

        # Arc + ticks (every 10 cents).
        p.setPen(QPen(c["arc"], 2))
        for cents in range(-50, 51, 10):
            a = self._cents_to_angle_rad(cents)
            outer = QPointF(pivot.x() + radius * math.sin(a),
                            pivot.y() - radius * math.cos(a))
            inner_r = radius - (14 if cents % 50 == 0 else 8)
            inner = QPointF(pivot.x() + inner_r * math.sin(a),
                            pivot.y() - inner_r * math.cos(a))
            p.setPen(QPen(c["tick"], 2 if cents % 50 == 0 else 1))
            p.drawLine(inner, outer)

        raw = self._tracker.raw

        # Calm center marker (only when the center is stable).
        center = self._tracker.center
        if center is not None and self._tracker.center_stable:
            a = self._cents_to_angle_rad(center[2])
            tip = QPointF(pivot.x() + radius * math.sin(a),
                          pivot.y() - radius * math.cos(a))
            base_r = radius - 20
            base = QPointF(pivot.x() + base_r * math.sin(a),
                           pivot.y() - base_r * math.cos(a))
            pen = QPen(c["center"], 6)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawLine(base, tip)

        # Live needle.
        cents = raw[2] if raw is not None else 0.0
        a = self._cents_to_angle_rad(cents)
        end = QPointF(pivot.x() + radius * 0.92 * math.sin(a),
                      pivot.y() - radius * 0.92 * math.cos(a))
        needle_color = c["needle"] if raw is not None else c["muted"]
        pen = QPen(needle_color, 4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawLine(pivot, end)

        # Hub.
        p.setBrush(c["text"])
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(pivot, 7, 7)

        # Note + cents readout.
        if raw is not None:
            name, octave, cents = raw
            in_tune = abs(cents) <= self._tracker.green_cents
            label = f"{name}{octave}   {cents:+.0f}¢"
            p.setPen(c["green"] if in_tune else c["text"])
        else:
            label = "—"
            p.setPen(c["muted"])
        font = QFont()
        font.setPointSize(15)
        font.setBold(True)
        p.setFont(font)
        p.drawText(0, int(h * 0.90), w, int(h * 0.12),
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                   label)
        p.end()
