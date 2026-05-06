"""
JARVIS — gui/arc_reactor.py  v2.0 — Iron Man Arc Reactor Remaster
Ultra-realistic multi-ring plasma reactor with:
  • 9 concentric rings at varied speeds/directions/alphas
  • Simulated bloom glow (3 paint passes per ring)
  • Hexagonal crystalline inner core (double counter-rotating hex)
  • 20-particle orbital energy field with glow halos
  • Smooth state→color interpolation
  • Sequential ring startup animation
  • Energy spoke lines from center
  • 5-layer plasma core
"""

import math
import random

from PyQt5.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PyQt5.QtWidgets import QWidget


class ArcReactorWidget(QWidget):
    # 9-ring config: (arc_span_deg, speed_deg_per_frame, direction, thickness_factor)
    _RING_CFG = [
        (330, 0.25, 1, 1.15),  # ring 0 — outermost, slowest
        (290, 0.42, -1, 1.05),  # ring 1
        (250, 0.64, 1, 0.95),  # ring 2
        (210, 0.90, -1, 0.87),  # ring 3
        (175, 1.22, 1, 0.78),  # ring 4
        (140, 1.62, -1, 0.70),  # ring 5
        (108, 2.10, 1, 0.62),  # ring 6
        (78, 2.70, -1, 0.54),  # ring 7
        (52, 3.40, 1, 0.46),  # ring 8 — innermost, fastest
    ]

    # Ring radii as fraction of base_r
    _RADII = [0.94, 0.84, 0.74, 0.65, 0.57, 0.49, 0.42, 0.35, 0.28]

    # State colours (R, G, B)
    _COLOURS = {
        "idle": (0, 160, 255),
        "listening": (0, 255, 110),
        "thinking": (160, 50, 255),
        "speaking": (0, 220, 255),
        "wake": (255, 170, 0),
    }

    def __init__(self):
        super().__init__()
        self.setMinimumSize(340, 340)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self._fade = 0.0
        self._ready = False
        self._ring_fade = [0.0] * len(self._RING_CFG)

        self._angles = [random.uniform(0, 360) for _ in self._RING_CFG]
        self._pulse = 0.0
        self._pd = 1
        self._state = "idle"
        self._speed = 1.0

        # Smooth colour lerp
        self._cur_rgb = list(self._COLOURS["idle"])
        self._tgt_rgb = list(self._COLOURS["idle"])

        # Particle system
        random.seed(7)
        self._particles = []
        for _ in range(20):
            self._particles.append(
                {
                    "a": random.uniform(0, 360),
                    "spd": random.uniform(0.5, 2.2) * random.choice([-1, 1]),
                    "r": random.uniform(0.32, 0.90),
                    "sz": random.uniform(1.8, 4.0),
                    "al": random.uniform(100, 220),
                    "trail": [],
                }
            )

        self._hex_angle = 0.0
        self._spoke_pulse = 0.0

        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(16)

    # ── State API ──────────────────────────────────────────────
    def set_idle(self):
        self._state = "idle"
        self._speed = 1.0
        self._tgt_rgb = list(self._COLOURS["idle"])

    def set_wake(self):
        self._state = "wake"
        self._speed = 3.8
        self._tgt_rgb = list(self._COLOURS["wake"])

    def set_listening(self):
        self._state = "listening"
        self._speed = 1.8
        self._tgt_rgb = list(self._COLOURS["listening"])

    def set_thinking(self):
        self._state = "thinking"
        self._speed = 3.0
        self._tgt_rgb = list(self._COLOURS["thinking"])

    def set_speaking(self):
        self._state = "speaking"
        self._speed = 2.1
        self._tgt_rgb = list(self._COLOURS["speaking"])

    # ── Tick ───────────────────────────────────────────────────
    def _tick(self):
        if not self._ready:
            self._fade = min(1.0, self._fade + 0.012)
            if self._fade >= 1.0:
                self._ready = True

        for i in range(len(self._ring_fade)):
            if self._fade > i * 0.10:
                self._ring_fade[i] = min(1.0, self._ring_fade[i] + 0.035)

        self._pulse += 0.020 * self._pd
        if self._pulse >= 1.0:
            self._pd = -1
        if self._pulse <= 0.0:
            self._pd = 1

        self._spoke_pulse += 0.04
        if self._spoke_pulse > 2 * math.pi:
            self._spoke_pulse -= 2 * math.pi

        for i, (_, spd, direction, _) in enumerate(self._RING_CFG):
            self._angles[i] = (self._angles[i] + spd * direction * self._speed) % 360

        self._hex_angle = (self._hex_angle + 0.35 * self._speed) % 360

        for ch in range(3):
            diff = self._tgt_rgb[ch] - self._cur_rgb[ch]
            self._cur_rgb[ch] = min(255, max(0, self._cur_rgb[ch] + diff * 0.07))

        for p in self._particles:
            p["a"] = (p["a"] + p["spd"] * self._speed) % 360

        self.update()

    # ── Paint ──────────────────────────────────────────────────
    def paintEvent(self, _):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setOpacity(self._fade)

        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0
        base_r = min(w, h) / 2.0 - 6
        pv = self._pulse
        r, g, b = int(self._cur_rgb[0]), int(self._cur_rgb[1]), int(self._cur_rgb[2])

        # ── 1. Deep aura background ──────────────────────────
        for rm, am in [(1.08, 8), (0.88, 16), (0.68, 28), (0.50, 44), (0.35, 60)]:
            bg = QRadialGradient(cx, cy, base_r * rm)
            bg.setColorAt(0.0, QColor(r, g, b, int(am * (0.35 + 0.65 * pv))))
            bg.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.setBrush(QBrush(bg))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(
                QRectF(
                    cx - base_r * rm, cy - base_r * rm, base_r * rm * 2, base_r * rm * 2
                )
            )

        # ── 2. Energy spoke lines (6 spokes from center) ─────
        spoke_alpha = int(40 + 50 * abs(math.sin(self._spoke_pulse)))
        spoke_pen = QPen(QColor(r, g, b, spoke_alpha), 1.0, Qt.DashLine)
        spoke_pen.setDashPattern([4, 6])
        painter.setPen(spoke_pen)
        inner_spoke = base_r * self._RADII[-1] * 1.1
        outer_spoke = base_r * self._RADII[0]
        for k in range(6):
            ang = math.radians(k * 60 + self._hex_angle * 0.3)
            x1 = cx + math.cos(ang) * inner_spoke
            y1 = cy + math.sin(ang) * inner_spoke
            x2 = cx + math.cos(ang) * outer_spoke
            y2 = cy + math.sin(ang) * outer_spoke
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        # ── 3. Orbital particles ─────────────────────────────
        if self._state != "idle":
            for p in self._particles:
                pr = base_r * p["r"]
                px = cx + math.cos(math.radians(p["a"])) * pr
                py = cy + math.sin(math.radians(p["a"])) * pr
                al = int(p["al"] * (0.45 + 0.55 * pv))
                sz = p["sz"]
                # Glow halo
                glow_r = sz * 4.0
                glow = QRadialGradient(px, py, glow_r)
                glow.setColorAt(0.0, QColor(r, g, b, al))
                glow.setColorAt(0.5, QColor(r, g, b, al // 3))
                glow.setColorAt(1.0, QColor(r, g, b, 0))
                painter.setBrush(QBrush(glow))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(QPointF(px, py), glow_r, glow_r)
                # Bright core
                painter.setBrush(QColor(255, 255, 255, min(255, al + 40)))
                painter.drawEllipse(QPointF(px, py), sz * 0.55, sz * 0.55)

        # ── 4. Nine rotating rings with bloom glow ───────────
        for i, (span, _, _, thk_pct) in enumerate(self._RING_CFG):
            ring_r = base_r * self._RADII[i]
            angle = self._angles[i]
            opacity = self._ring_fade[i]
            if opacity < 0.01:
                continue

            base_thk = base_r * 0.042 * thk_pct
            alpha_base = int((205 - i * 16) * (0.45 + 0.55 * pv) * opacity)
            rect = QRectF(cx - ring_r, cy - ring_r, ring_r * 2, ring_r * 2)

            # Bloom passes: wide+dim → medium → thin+bright
            for bw, ba in [
                (base_thk * 4.5, max(1, alpha_base // 6)),
                (base_thk * 2.2, max(1, alpha_base // 3)),
                (base_thk * 1.0, alpha_base),
            ]:
                pen = QPen(QColor(r, g, b, ba), bw, Qt.SolidLine, Qt.RoundCap)
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
                painter.drawArc(rect, int(angle * 16), int(span * 16))

            # White leading-edge highlight
            hl_al = int(200 * (0.4 + 0.6 * pv) * opacity)
            painter.setPen(
                QPen(
                    QColor(255, 255, 255, hl_al),
                    base_thk * 0.40,
                    Qt.SolidLine,
                    Qt.RoundCap,
                )
            )
            painter.drawArc(rect, int(angle * 16), int(span * 0.15 * 16))

            # Tick marks
            n_ticks = max(8, 24 - i * 2)
            tick_al = max(0, int(alpha_base * 0.55))
            for t_i in range(n_ticks):
                a_r = math.radians(t_i * 360 / n_ticks + angle)
                inn = ring_r - base_thk * 0.7
                out = ring_r + base_thk * 0.7
                painter.setPen(QPen(QColor(r, g, b, tick_al), max(0.5, base_r * 0.005)))
                painter.drawLine(
                    QPointF(cx + math.cos(a_r) * inn, cy + math.sin(a_r) * inn),
                    QPointF(cx + math.cos(a_r) * out, cy + math.sin(a_r) * out),
                )

        # ── 5. Double counter-rotating hexagonal core ────────
        hex_r_out = base_r * 0.165
        hex_r_inn = base_r * 0.085

        for hex_r_v, hex_ang_v, n_sides in [
            (hex_r_out, self._hex_angle, 6),
            (hex_r_inn, -self._hex_angle * 1.5, 6),
        ]:
            painter.save()
            painter.translate(cx, cy)
            painter.rotate(hex_ang_v)

            path = QPainterPath()
            for k in range(n_sides):
                ang_k = math.radians(
                    k * 360 / n_sides + (30 if hex_r_v == hex_r_inn else 0)
                )
                px2 = math.cos(ang_k) * hex_r_v
                py2 = math.sin(ang_k) * hex_r_v
                if k == 0:
                    path.moveTo(px2, py2)
                else:
                    path.lineTo(px2, py2)
            path.closeSubpath()

            hex_al = int(170 * (0.5 + 0.5 * pv))
            for hw, ha in [(3.5, hex_al // 5), (2.0, hex_al // 2), (1.0, hex_al)]:
                painter.setPen(QPen(QColor(r, g, b, ha), hw))
                painter.setBrush(Qt.NoBrush)
                painter.drawPath(path)

            painter.restore()

        # ── 6. Five-layer plasma core ────────────────────────
        core_r = base_r * 0.21
        pv2 = 0.60 + 0.40 * pv

        # Soft outer halos
        for rm, am in [(4.0, 6), (3.0, 12), (2.2, 22), (1.6, 40), (1.15, 70)]:
            cg = QRadialGradient(cx, cy, core_r * rm)
            cg.setColorAt(0.0, QColor(r, g, b, int(am * pv2)))
            cg.setColorAt(1.0, QColor(r, g, b, 0))
            painter.setBrush(QBrush(cg))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(
                QRectF(
                    cx - core_r * rm, cy - core_r * rm, core_r * rm * 2, core_r * rm * 2
                )
            )

        # Main plasma gradient
        wc = QRadialGradient(cx, cy, core_r)
        wc.setColorAt(0.00, QColor(255, 255, 255, int(255 * pv2)))
        wc.setColorAt(
            0.15,
            QColor(
                min(255, r + 100), min(255, g + 100), min(255, b + 100), int(250 * pv2)
            ),
        )
        wc.setColorAt(0.40, QColor(r, g, b, int(220 * pv2)))
        wc.setColorAt(0.70, QColor(r // 2, g // 2, b // 2, int(150 * pv2)))
        wc.setColorAt(0.90, QColor(r // 4, g // 4, b // 4, int(80 * pv2)))
        wc.setColorAt(1.00, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(wc))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QRectF(cx - core_r, cy - core_r, core_r * 2, core_r * 2))

        # Glass specular highlight (off-center)
        sx, sy = cx - core_r * 0.28, cy - core_r * 0.32
        sr = core_r * 0.45
        sg = QRadialGradient(sx, sy, sr)
        sg.setColorAt(0.0, QColor(255, 255, 255, int(210 * pv2)))
        sg.setColorAt(0.4, QColor(255, 255, 255, int(70 * pv2)))
        sg.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setBrush(QBrush(sg))
        painter.drawEllipse(QRectF(sx - sr, sy - sr, sr * 2, sr * 2))

        painter.end()
