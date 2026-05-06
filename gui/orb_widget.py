"""
JARVIS — gui/orb_widget.py
Animated glowing orb that pulses when JARVIS is listening/speaking.
"""

import math
from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt, QTimer, QPointF
from PyQt5.QtGui import QPainter, QRadialGradient, QColor, QPen, QBrush


class OrbWidget(QWidget):
    """Animated JARVIS orb — glows and pulses based on state."""

    # States
    IDLE = 0
    LISTENING = 1
    THINKING = 2
    SPEAKING = 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(160, 160)
        self.setMaximumSize(160, 160)

        self._state = self.IDLE
        self._pulse = 0.0        # 0.0 - 1.0 pulse animation
        self._angle = 0.0        # Rotation for ring
        self._glow_size = 0.0    # Glow expansion

        # Animation timer — 60 FPS
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._timer.start(16)  # ~60fps

    @property
    def state(self):
        return self._state

    def set_idle(self):
        self._state = self.IDLE

    def set_listening(self):
        self._state = self.LISTENING

    def set_thinking(self):
        self._state = self.THINKING

    def set_speaking(self):
        self._state = self.SPEAKING

    def _animate(self):
        """Update animation frame."""
        self._pulse = (self._pulse + 0.03) % (2 * math.pi)
        self._angle = (self._angle + 1.5) % 360
        self._glow_size = 0.5 + 0.5 * math.sin(self._pulse)
        self.update()

    def paintEvent(self, event):
        """Draw the orb."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        base_r = min(w, h) / 2 - 20

        # Choose colors based on state
        if self._state == self.IDLE:
            core_color = QColor(59, 130, 246)      # Blue
            glow_color = QColor(59, 130, 246, 60)
            ring_color = QColor(59, 130, 246, 80)
        elif self._state == self.LISTENING:
            core_color = QColor(34, 197, 94)        # Green
            glow_color = QColor(34, 197, 94, 80)
            ring_color = QColor(34, 197, 94, 120)
        elif self._state == self.THINKING:
            core_color = QColor(168, 85, 247)       # Purple
            glow_color = QColor(168, 85, 247, 60)
            ring_color = QColor(168, 85, 247, 100)
        else:  # SPEAKING
            core_color = QColor(6, 182, 212)         # Cyan
            glow_color = QColor(6, 182, 212, 80)
            ring_color = QColor(6, 182, 212, 120)

        # Pulse amount
        pulse = math.sin(self._pulse)
        pulse_r = base_r + pulse * 6

        # ── Outer glow ──────────────────────────────────────
        glow_r = pulse_r + 15 + self._glow_size * 10
        grad = QRadialGradient(QPointF(cx, cy), glow_r)
        grad.setColorAt(0, glow_color)
        grad.setColorAt(0.5, QColor(glow_color.red(), glow_color.green(), glow_color.blue(), 30))
        grad.setColorAt(1, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(grad))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(cx, cy), glow_r, glow_r)

        # ── Spinning ring (when active) ─────────────────────
        if self._state != self.IDLE:
            ring_pen = QPen(ring_color, 2)
            painter.setPen(ring_pen)
            painter.setBrush(Qt.NoBrush)
            arc_r = pulse_r + 8
            painter.save()
            painter.translate(cx, cy)
            painter.rotate(self._angle)
            painter.drawArc(
                int(-arc_r), int(-arc_r),
                int(arc_r * 2), int(arc_r * 2),
                0, 270 * 16  # 270 degree arc
            )
            painter.restore()

        # ── Core orb ────────────────────────────────────────
        core_grad = QRadialGradient(QPointF(cx, cy - 10), pulse_r)
        lighter = QColor(
            min(255, core_color.red() + 60),
            min(255, core_color.green() + 60),
            min(255, core_color.blue() + 60)
        )
        core_grad.setColorAt(0, lighter)
        core_grad.setColorAt(0.7, core_color)
        core_grad.setColorAt(1, QColor(
            core_color.red() // 2,
            core_color.green() // 2,
            core_color.blue() // 2
        ))
        painter.setBrush(QBrush(core_grad))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(cx, cy), pulse_r, pulse_r)

        # ── Highlight (glass reflection) ────────────────────
        highlight = QRadialGradient(QPointF(cx - 8, cy - 12), pulse_r * 0.5)
        highlight.setColorAt(0, QColor(255, 255, 255, 80))
        highlight.setColorAt(1, QColor(255, 255, 255, 0))
        painter.setBrush(QBrush(highlight))
        painter.drawEllipse(QPointF(cx - 8, cy - 12), pulse_r * 0.4, pulse_r * 0.3)

        painter.end()
