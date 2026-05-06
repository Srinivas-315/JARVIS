# gui/hud_widgets.py  ─  JARVIS Full Visual HUD Upgrade
# Provides: GaugeWidget, NetGraphWidget, WaveformWidget, HudChatDisplay
#           + all C_* colour constants consumed by main_window.py
"""
All paint helpers stay inside each widget so the file is self-contained.
No external assets are needed – everything is drawn with QPainter.
"""

import collections
import math
import random
from datetime import datetime

from PyQt5.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QRadialGradient,
)
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

# ── Palette (names are imported verbatim by main_window.py) ──────────────────
C_BG = "#020a18"
C_PANEL = "rgba(4, 15, 35, 210)"
C_BLUE = "#0055ff"
C_CYAN = "#00d4ff"
C_GREEN = "#00ff88"
C_PURPLE = "#9d00ff"
C_GOLD = "#ffaa00"
C_DIM = "rgba(0, 212, 255, 35)"
C_TEXT = "#00d4ff"
C_TEXT_SEC = "#3a8aaa"
C_BORDER = "rgba(0, 212, 255, 90)"
C_BORDER2 = "rgba(0, 212, 255, 40)"


# ── Colour helper ─────────────────────────────────────────────────────────────
def _qc(s: str) -> QColor:
    """Parse '#rrggbb'  or  'rgba(r,g,b,a)'  →  QColor  (alpha 0-255)."""
    s = s.strip()
    if s.startswith("rgba"):
        parts = s[5:-1].split(",")
        r = int(parts[0].strip())
        g = int(parts[1].strip())
        b = int(parts[2].strip())
        a = int(float(parts[3].strip()))
        return QColor(r, g, b, a)
    return QColor(s)


# ─────────────────────────────────────────────────────────────────────────────
#  GaugeWidget  –  circular arc gauge  (110 × 110)
# ─────────────────────────────────────────────────────────────────────────────
class GaugeWidget(QWidget):
    """
    Beautiful arc gauge.
    Sweep: 270 ° starting at 225 ° (lower-left), going clockwise.
    Fill colour: 0-60 % → cyan  |  60-80 % → gold  |  80-100 % → red.
    Glow is painted as a second, wider+transparent arc beneath the fill.
    A small triangle indicator marks the tip of the fill arc.
    """

    _START_DEG = 225  # Qt convention: CCW from 3-o'clock
    _SWEEP_DEG = -270  # negative = clockwise on screen

    def __init__(self, label: str, color: str = C_CYAN):
        super().__init__()
        self.setFixedSize(110, 110)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._val = 0.0
        self._label = label
        # 'color' is kept for API compatibility; value-based colouring takes precedence
        self._color = color

    # public API ──────────────────────────────────────────────────────────────
    def set_value(self, v: float) -> None:
        self._val = max(0.0, min(100.0, float(v)))
        self.update()

    # internals ───────────────────────────────────────────────────────────────
    def _fill_color(self) -> QColor:
        if self._val < 60.0:
            return QColor(C_CYAN)
        if self._val < 80.0:
            return QColor(C_GOLD)
        return QColor("#ff3355")

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        W, H = float(self.width()), float(self.height())
        cx, cy = W * 0.5, H * 0.5
        R = 41.0  # arc radius
        AW = 7  # arc stroke width

        arc_rect = QRectF(cx - R, cy - R, R * 2.0, R * 2.0)

        # ── Background dark circle ────────────────────────────────────────
        bg_grad = QRadialGradient(cx, cy, R + 6)
        bg_grad.setColorAt(0.00, QColor(0, 30, 65, 150))
        bg_grad.setColorAt(0.65, QColor(0, 12, 30, 115))
        bg_grad.setColorAt(1.00, QColor(0, 4, 14, 60))
        p.setBrush(QBrush(bg_grad))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QRectF(cx - R - 6, cy - R - 6, (R + 6) * 2, (R + 6) * 2))

        # Subtle inner ring
        ring_col = QColor(0, 212, 255, 22)
        p.setPen(QPen(ring_col, 1))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QRectF(cx - R + 2, cy - R + 2, (R - 2) * 2, (R - 2) * 2))

        # ── Track arc (dim background) ────────────────────────────────────
        track_col = QColor(0, 212, 255, 55)
        p.setPen(QPen(track_col, AW, Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        p.drawArc(arc_rect, self._START_DEG * 16, self._SWEEP_DEG * 16)

        # ── Fill arc ──────────────────────────────────────────────────────
        fill_span = int(self._SWEEP_DEG * self._val / 100.0)

        if abs(fill_span) > 0:
            fill_col = self._fill_color()

            # Outer glow pass (wider, low alpha)
            glow_col = QColor(fill_col)
            glow_col.setAlpha(40)
            p.setPen(QPen(glow_col, AW + 9, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(arc_rect, self._START_DEG * 16, fill_span * 16)

            # Inner glow pass
            glow_col2 = QColor(fill_col)
            glow_col2.setAlpha(80)
            p.setPen(QPen(glow_col2, AW + 3, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(arc_rect, self._START_DEG * 16, fill_span * 16)

            # Crisp fill arc
            p.setPen(QPen(fill_col, AW, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(arc_rect, self._START_DEG * 16, fill_span * 16)

            # ── Triangle indicator at arc tip ──────────────────────────────
            # tip_deg: angle (Qt convention) where the fill arc ends
            tip_deg = self._START_DEG + fill_span
            tip_rad = math.radians(tip_deg)
            tip_x = cx + R * math.cos(tip_rad)
            tip_y = cy - R * math.sin(tip_rad)  # Qt Y increases downward

            tri_col = QColor(fill_col)
            tri_col.setAlpha(235)

            p.save()
            p.translate(tip_x, tip_y)
            # Rotate so that the triangle's local +X axis points radially outward.
            # Qt rotate() is clockwise; -tip_deg aligns +X with the outward radius.
            p.rotate(-tip_deg)
            sz = 5.5
            tri = QPolygonF(
                [
                    QPointF(sz, 0.0),  # apex  (outward)
                    QPointF(-sz * 0.45, sz * 0.80),  # base right
                    QPointF(-sz * 0.45, -sz * 0.80),  # base left
                ]
            )
            p.setBrush(QBrush(tri_col))
            p.setPen(Qt.NoPen)
            p.drawPolygon(tri)
            p.restore()

        # ── Value text ────────────────────────────────────────────────────
        val_font = QFont("Share Tech Mono", 13, QFont.Bold)
        val_font.setStyleHint(QFont.TypeWriter)
        p.setFont(val_font)
        p.setPen(QColor(C_TEXT))
        p.drawText(QRectF(0, cy - 14.0, W, 23.0), Qt.AlignCenter, f"{int(self._val)}%")

        # ── Label text ────────────────────────────────────────────────────
        lbl_font = QFont("Orbitron", 7, QFont.Bold)
        lbl_font.setStyleHint(QFont.SansSerif)
        p.setFont(lbl_font)
        p.setPen(QColor(C_TEXT_SEC))
        p.drawText(QRectF(0, cy + 11.0, W, 16.0), Qt.AlignCenter, self._label)

        p.end()


# ─────────────────────────────────────────────────────────────────────────────
#  NetGraphWidget  –  upload / download line graph
# ─────────────────────────────────────────────────────────────────────────────
class NetGraphWidget(QWidget):
    """
    Rolling 60-sample network activity graph.
    Blue  = upload   |   Cyan = download.
    Each channel is drawn as a glowing filled line graph.
    Current speed labels float at the top.
    """

    _SAMPLES = 60

    def __init__(self):
        super().__init__()
        self.setFixedHeight(94)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._up = collections.deque([0.0] * self._SAMPLES, maxlen=self._SAMPLES)
        self._dn = collections.deque([0.0] * self._SAMPLES, maxlen=self._SAMPLES)
        self._max_val = 100.0
        self._cur_up = 0.0
        self._cur_dn = 0.0

    # public API ──────────────────────────────────────────────────────────────
    def add_data(self, up: float, dn: float) -> None:
        self._cur_up = max(0.0, up)
        self._cur_dn = max(0.0, dn)
        self._up.append(self._cur_up)
        self._dn.append(self._cur_dn)
        m = max(max(self._up), max(self._dn), 1.0)
        if m > self._max_val:
            self._max_val = m * 1.15
        elif m < self._max_val * 0.35 and self._max_val > 100.0:
            self._max_val = max(100.0, self._max_val * 0.93)
        self.update()

    # internals ───────────────────────────────────────────────────────────────
    def _build_line(self, hist, w: float, h: float, top: float) -> QPainterPath:
        """Build a QPainterPath for a single data channel."""
        n = len(hist)
        if n < 2:
            return QPainterPath()
        usable_h = h - top
        dx = w / max(n - 1, 1)
        path = QPainterPath()
        y0 = h - (hist[0] / self._max_val) * usable_h
        path.moveTo(0.0, y0)
        for i in range(1, n):
            x = i * dx
            y = h - (hist[i] / self._max_val) * usable_h
            path.lineTo(x, y)
        return path

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = float(self.width()), float(self.height())
        H_PAD = 18.0  # vertical space reserved for the labels at top

        # ── Panel background ──────────────────────────────────────────────
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 7, 20, 95))
        p.drawRoundedRect(QRectF(0, 0, w, h), 4, 4)

        # ── Grid ──────────────────────────────────────────────────────────
        grid_col = QColor(0, 212, 255, 28)
        p.setPen(QPen(grid_col, 1, Qt.DotLine))
        for i in range(1, 4):
            gy = H_PAD + (h - H_PAD) * i / 4.0
            p.drawLine(QPointF(0.0, gy), QPointF(w, gy))
        for i in range(1, 10):
            gx = w * i / 10.0
            p.drawLine(QPointF(gx, H_PAD), QPointF(gx, h))

        # ── Channel painter helper ─────────────────────────────────────────
        def _draw(hist, hex_col: str) -> None:
            line = self._build_line(hist, w, h, H_PAD)
            if line.isEmpty():
                return

            # Filled area under the line (vertical gradient, fades to 0)
            fill = QPainterPath(line)
            fill.lineTo(w, h)
            fill.lineTo(0.0, h)
            fill.closeSubpath()

            area_grad = QLinearGradient(0.0, H_PAD, 0.0, h)
            c_top = QColor(hex_col)
            c_top.setAlpha(85)
            c_bot = QColor(hex_col)
            c_bot.setAlpha(0)
            area_grad.setColorAt(0.0, c_top)
            area_grad.setColorAt(1.0, c_bot)
            p.setBrush(QBrush(area_grad))
            p.setPen(Qt.NoPen)
            p.drawPath(fill)

            # Outer glow line
            glow = QColor(hex_col)
            glow.setAlpha(50)
            p.setPen(QPen(glow, 4.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(Qt.NoBrush)
            p.drawPath(line)

            # Crisp main line
            p.setPen(
                QPen(QColor(hex_col), 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            )
            p.drawPath(line)

        # Draw download first (behind upload)
        _draw(self._dn, C_CYAN)
        _draw(self._up, C_BLUE)

        # ── Speed labels ──────────────────────────────────────────────────
        lbl_font = QFont("Share Tech Mono", 8)
        lbl_font.setStyleHint(QFont.TypeWriter)
        p.setFont(lbl_font)

        p.setPen(QColor(C_BLUE))
        p.drawText(
            QRectF(5.0, 1.0, w * 0.5 - 5.0, 15.0),
            Qt.AlignLeft | Qt.AlignVCenter,
            f"\u25b2 UP  {self._cur_up:>8.1f} KB/s",
        )

        p.setPen(QColor(C_CYAN))
        p.drawText(
            QRectF(w * 0.5, 1.0, w * 0.5 - 5.0, 15.0),
            Qt.AlignRight | Qt.AlignVCenter,
            f"\u25bc DN  {self._cur_dn:>8.1f} KB/s",
        )

        p.end()


# ─────────────────────────────────────────────────────────────────────────────
#  WaveformWidget  –  animated voice waveform  (50 bars)
# ─────────────────────────────────────────────────────────────────────────────
class WaveformWidget(QWidget):
    """
    50-bar animated waveform.
    Active   → taller, bright cyan bars + occasional beat spike.
    Inactive → short, dim bars that ripple gently.
    Each bar is a vertical gradient rectangle (dim bottom → bright top).
    """

    _N_BARS = 50

    def __init__(self):
        super().__init__()
        self.setFixedHeight(64)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._bars = [random.uniform(0.05, 0.11) for _ in range(self._N_BARS)]
        self._targets = [0.07] * self._N_BARS
        self._active = False
        self._tick_n = 0

        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(40)  # ~25 fps

    # public API ──────────────────────────────────────────────────────────────
    def set_active(self, active: bool) -> None:
        self._active = active

    # internals ───────────────────────────────────────────────────────────────
    def _tick(self) -> None:
        self._tick_n += 1
        beat = self._active and (self._tick_n % 17 == 0)
        mid = self._N_BARS // 2

        for i in range(self._N_BARS):
            if self._active:
                # Bars closer to the centre are taller → organic mountain shape
                dist = abs(i - mid) / max(mid, 1)
                hi = max(0.35, 0.95 - dist * 0.28)
                lo = max(0.12, 0.28 - dist * 0.12)
                if beat and abs(i - mid) <= 4:
                    self._targets[i] = random.uniform(0.82, 1.00)
                else:
                    self._targets[i] = random.uniform(lo, hi)
            else:
                self._targets[i] = random.uniform(0.03, 0.13)

            # Smooth lerp toward target
            self._bars[i] += (self._targets[i] - self._bars[i]) * 0.22

        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = float(self.width()), float(self.height())
        gap = 1.0
        n = self._N_BARS
        bar_w = (w - gap * (n - 1)) / n

        if bar_w <= 0:
            p.end()
            return

        p.setPen(Qt.NoPen)

        for i, val in enumerate(self._bars):
            bh = max(2.0, val * h * 0.94)
            bx = i * (bar_w + gap)
            by = (h - bh) * 0.5

            # Gradient: dim at bar bottom → bright at bar top
            grad = QLinearGradient(bx, by + bh, bx, by)  # bottom → top
            if self._active:
                c_bot = QColor(C_CYAN)
                c_bot.setAlpha(95)
                c_top = QColor(C_CYAN)
                c_top.setAlpha(255)
            else:
                c_bot = QColor(C_CYAN)
                c_bot.setAlpha(22)
                c_top = QColor(C_CYAN)
                c_top.setAlpha(72)
            grad.setColorAt(0.0, c_bot)
            grad.setColorAt(1.0, c_top)

            p.setBrush(QBrush(grad))
            p.drawRoundedRect(QRectF(bx, by, bar_w, bh), 1.0, 1.0)

        p.end()


# ─────────────────────────────────────────────────────────────────────────────
#  HudChatDisplay  –  scrollable COMMS LOG
# ─────────────────────────────────────────────────────────────────────────────
class HudChatDisplay(QWidget):
    """
    Scrollable comms log with:
      • "COMMS LOG" title bar
      • Timestamps (HH:MM) on every message
      • Green  "YOU >"   prefix for user messages
      • Cyan   "JARVIS >"  prefix for AI messages
      • Alternating row tint for readability
      • Word-wrapped body text
      • Auto-scroll to latest message
    """

    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Title bar ─────────────────────────────────────────────────────
        title_bar = QWidget()
        title_bar.setFixedHeight(28)
        title_bar.setStyleSheet(
            f"background: rgba(0, 212, 255, 16);border-bottom: 1px solid {C_BORDER};"
        )
        tb_lay = QHBoxLayout(title_bar)
        tb_lay.setContentsMargins(10, 0, 10, 0)
        tb_lay.setSpacing(6)

        icon_lbl = QLabel("\u25c8")  # ◈
        icon_lbl.setStyleSheet(f"color: {C_CYAN}; font-size: 12px;")
        tb_lay.addWidget(icon_lbl)

        title_lbl = QLabel("COMMS LOG")
        title_lbl.setStyleSheet(
            f"color: {C_TEXT};"
            "font-family: 'Orbitron', 'Segoe UI', sans-serif;"
            "font-size: 10px;"
            "font-weight: bold;"
            "letter-spacing: 3px;"
        )
        tb_lay.addWidget(title_lbl)
        tb_lay.addStretch()

        active_dot = QLabel("\u25cf")  # ●
        active_dot.setStyleSheet(f"color: {C_GREEN}; font-size: 9px;")
        tb_lay.addWidget(active_dot)

        outer.addWidget(title_bar)

        # ── Scroll area ───────────────────────────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            QScrollBar:vertical {{
                background: rgba(0, 8, 22, 130);
                width: 5px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {C_BORDER};
                border-radius: 2px;
                min-height: 18px;
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {{
                background: none;
            }}
        """)

        self._inner = QWidget()
        self._inner.setStyleSheet("background: transparent;")
        self._vlay = QVBoxLayout(self._inner)
        self._vlay.setContentsMargins(8, 8, 8, 8)
        self._vlay.setSpacing(2)
        self._vlay.addStretch()  # messages appear above this stretch

        self._msg_count = 0
        self._scroll.setWidget(self._inner)
        outer.addWidget(self._scroll)

    # public API ──────────────────────────────────────────────────────────────
    def add_message(self, text: str, is_user: bool) -> None:
        timestamp = datetime.now().strftime("%H:%M")
        prefix_raw = "YOU &gt;" if is_user else "JARVIS &gt;"
        p_color = C_GREEN if is_user else C_CYAN

        # Alternate subtle row tint
        row_alpha = 14 if (self._msg_count % 2 == 0) else 0

        row = QWidget()
        row.setStyleSheet(
            f"background: rgba(0, 212, 255, {row_alpha});border-radius: 3px;"
        )
        row_lay = QVBoxLayout(row)
        row_lay.setContentsMargins(7, 4, 7, 5)
        row_lay.setSpacing(2)

        # ── Header: coloured prefix  +  dim timestamp ─────────────────────
        header = QLabel(
            f"<span style='"
            f"color:{p_color};"
            f"font-family:Orbitron,monospace;"
            f"font-size:10px;"
            f"font-weight:bold;"
            f"letter-spacing:1px;"
            f"'>{prefix_raw}</span>"
            f"&nbsp;&nbsp;"
            f"<span style='"
            f"color:{C_TEXT_SEC};"
            f'font-family:"Share Tech Mono",monospace;'
            f"font-size:9px;"
            f"'>{timestamp}</span>"
        )
        header.setTextFormat(Qt.RichText)
        row_lay.addWidget(header)

        # ── Body: plain word-wrapped message text ─────────────────────────
        body = QLabel(text)
        body.setWordWrap(True)
        body.setTextFormat(Qt.PlainText)
        body.setStyleSheet(
            f"color: {C_TEXT_SEC};"
            "font-family: 'Rajdhani', 'Segoe UI', sans-serif;"
            "font-size: 13px;"
            "padding-left: 4px;"
        )
        row_lay.addWidget(body)

        # Insert before the trailing stretch so new messages appear at bottom
        self._vlay.insertWidget(self._vlay.count() - 1, row)
        self._msg_count += 1

        # Scroll after Qt has had a chance to re-layout
        QTimer.singleShot(60, self._scroll_to_bottom)

    # internals ───────────────────────────────────────────────────────────────
    def _scroll_to_bottom(self) -> None:
        sb = self._scroll.verticalScrollBar()
        sb.setValue(sb.maximum())
