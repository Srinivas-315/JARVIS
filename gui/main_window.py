"""
JARVIS — gui/main_window.py  (Iron Man HUD — Ultra Edition)
"""

import math
import random
import sys
import threading
import time
from datetime import datetime

import psutil
from PyQt5.QtCore import QPointF, QRectF, Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontDatabase,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QRadialGradient,
)
from PyQt5.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

try:
    from gui.arc_reactor import ArcReactorWidget
    from gui.hud_widgets import (
        C_BG,
        C_BLUE,
        C_BORDER,
        C_CYAN,
        C_DIM,
        C_PANEL,
        C_TEXT,
        C_TEXT_SEC,
        GaugeWidget,
        HudChatDisplay,
        NetGraphWidget,
        WaveformWidget,
    )
except ImportError:
    sys.path.insert(0, __file__.rsplit("\\", 2)[0])
    from gui.arc_reactor import ArcReactorWidget
    from gui.hud_widgets import (
        C_BG,
        C_BLUE,
        C_BORDER,
        C_CYAN,
        C_DIM,
        C_PANEL,
        C_TEXT,
        C_TEXT_SEC,
        GaugeWidget,
        HudChatDisplay,
        NetGraphWidget,
        WaveformWidget,
    )


# ─────────────────────────────────────────────────────────────────────────────
#  HudBackground  —  decorative full-window background layer
# ─────────────────────────────────────────────────────────────────────────────
class HudBackground(QWidget):
    """
    Paints (behind all panels) :
      • Pointy-top hexagonal grid  (circumradius ≈ 45 px)
      • 120-particle cyan drift field
      • Animated gradient scan bar sweeping top → bottom
      • Iron Man–style corner bracket decorations at all four corners
    """

    _HEX_R = 45  # circumradius  (px)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._scanline_y = 0.0

        # ── Particle field ────────────────────────────────────────────────
        _rng = random.Random(42)
        self._particles = [
            {
                "x": _rng.uniform(0, 1920),
                "y": _rng.uniform(0, 1080),
                "vx": _rng.uniform(-0.35, 0.35),
                "vy": _rng.uniform(-0.35, 0.35),
                "alpha": _rng.randint(40, 120),
                "size": _rng.uniform(1.0, 2.5),
            }
            for _ in range(120)
        ]

        # ── Hex grid polygon cache (rebuilt on resize) ────────────────────
        self._hex_polys: list = []  # list of (QPolygonF, bool_glowing)

        # ── Animation timer  (~30 fps) ────────────────────────────────────
        _t = QTimer(self)
        _t.timeout.connect(self._animate)
        _t.start(30)

    # ── Resize → rebuild hex cache ────────────────────────────────────────
    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._rebuild_hex_grid()

    def _rebuild_hex_grid(self):
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return
        R = self._HEX_R
        hw = math.sqrt(3) * R  # horizontal spacing between centers
        vs = R * 1.5  # vertical step between row centers
        polys = []
        row = 0
        y = -R
        while y < h + R:
            x_off = (hw / 2.0) if (row % 2) else 0.0
            x = -hw + x_off
            col = 0
            while x < w + hw:
                glowing = (abs(hash((row, col))) % 7) == 0
                pts = [
                    QPointF(
                        x + R * math.cos(math.radians(60 * i - 90)),
                        y + R * math.sin(math.radians(60 * i - 90)),
                    )
                    for i in range(6)
                ]
                polys.append((QPolygonF(pts), glowing))
                x += hw
                col += 1
            y += vs
            row += 1
        self._hex_polys = polys

    # ── Animation tick ────────────────────────────────────────────────────
    def _animate(self):
        self._scanline_y = (self._scanline_y + 1.2) % max(1, self.height())
        w, h = self.width(), self.height()
        if w > 0 and h > 0:
            for p in self._particles:
                p["x"] = (p["x"] + p["vx"]) % w
                p["y"] = (p["y"] + p["vy"]) % h
        self.update()

    # ── Paint ─────────────────────────────────────────────────────────────
    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        # 1 ── Hexagonal grid ─────────────────────────────────────────────
        if self._hex_polys:
            dim_pen = QPen(QColor(0, 212, 255, 18), 1.0)
            bright_pen = QPen(QColor(0, 212, 255, 45), 1.0)
            painter.setBrush(Qt.NoBrush)
            for poly, glowing in self._hex_polys:
                painter.setPen(bright_pen if glowing else dim_pen)
                painter.drawConvexPolygon(poly)

        # 2 ── Particle field ──────────────────────────────────────────────
        painter.setPen(Qt.NoPen)
        for p in self._particles:
            painter.setBrush(QColor(0, 212, 255, p["alpha"]))
            s = p["size"]
            painter.drawEllipse(QRectF(p["x"] - s * 0.5, p["y"] - s * 0.5, s, s))

        # 3 ── Animated gradient scan bar ─────────────────────────────────
        sy = int(self._scanline_y)
        grad = QLinearGradient(0, sy - 30, 0, sy + 30)
        grad.setColorAt(0.00, QColor(0, 212, 255, 0))
        grad.setColorAt(0.30, QColor(0, 212, 255, 8))
        grad.setColorAt(0.50, QColor(0, 212, 255, 22))
        grad.setColorAt(0.70, QColor(0, 212, 255, 8))
        grad.setColorAt(1.00, QColor(0, 212, 255, 0))
        painter.setBrush(QBrush(grad))
        painter.setPen(Qt.NoPen)
        painter.drawRect(0, sy - 30, w, 60)

        # 4 ── Corner bracket decorations ─────────────────────────────────
        self._draw_corners(painter, w, h)
        painter.end()

    # ── Corner brackets ───────────────────────────────────────────────────
    def _draw_corners(self, painter, w, h):
        """
        Iron Man–style angular brackets at each corner.
        Each bracket = horizontal arm + vertical arm + 45° chamfer cut
        with tiny dots at the outer arm ends.
        """
        L, C, M = 50, 9, 18  # arm-len, chamfer, margin
        pen = QPen(QColor(0, 212, 255, 180), 2.5)
        pen.setCapStyle(Qt.SquareCap)
        dot = QBrush(QColor(0, 212, 255, 210))

        corners = [
            (M, M, +1, +1),  # top-left
            (w - M, M, -1, +1),  # top-right
            (M, h - M, +1, -1),  # bottom-left
            (w - M, h - M, -1, -1),  # bottom-right
        ]
        for ox, oy, dx, dy in corners:
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            # Horizontal arm: outer-end → chamfer start
            painter.drawLine(QPointF(ox + dx * L, oy), QPointF(ox + dx * C, oy))
            # Vertical arm: outer-end → chamfer start
            painter.drawLine(QPointF(ox, oy + dy * L), QPointF(ox, oy + dy * C))
            # 45° chamfer cut
            painter.drawLine(QPointF(ox + dx * C, oy), QPointF(ox, oy + dy * C))
            # Tiny dots at outer arm ends
            painter.setPen(Qt.NoPen)
            painter.setBrush(dot)
            painter.drawEllipse(QPointF(ox + dx * L, oy), 2.5, 2.5)
            painter.drawEllipse(QPointF(ox, oy + dy * L), 2.5, 2.5)


# ─────────────────────────────────────────────────────────────────────────────
#  VoiceWorker  — DO NOT MODIFY
# ─────────────────────────────────────────────────────────────────────────────
class VoiceWorker(QThread):
    result = pyqtSignal(str)
    state_changed = pyqtSignal(str)
    WAKE_WORDS = ["jarvis", "hey jarvis", "hello jarvis", "jarves", "jarwis"]
    ACTIVE_SECS = 60

    def __init__(self, listener):
        super().__init__()
        self.listener = listener
        self._running = True
        self._active_until = 0
        import speech_recognition as sr

        self._rec = sr.Recognizer()
        self._rec.energy_threshold = 400
        self._rec.dynamic_energy_threshold = True
        self._rec.pause_threshold = 0.5

        # ── Clap detection disabled: PyAudio + speech_recognition share
        # the same mic device; opening both simultaneously causes a native
        # Windows memory crash (audio driver null-pointer). Re-enable only
        # with a dedicated mic-index or sounddevice backend.
        # import threading
        # threading.Thread(target=self._clap_monitor, daemon=True).start()

    def _clap_monitor(self):
        """Detect a hand-clap (sudden loud spike) and wake JARVIS.
        NOTE: only sets _active_until — does NOT emit Qt signals
        (emitting from a non-QThread daemon crashes PyQt5).
        """
        try:
            import math
            import struct

            import pyaudio

            CHUNK = 512
            RATE = 16000
            CLAP_RMS = 2000  # RMS threshold — raise if too sensitive
            COOLDOWN = 2.0  # seconds between triggers

            pa = pyaudio.PyAudio()
            stm = pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=RATE,
                input=True,
                frames_per_buffer=CHUNK,
            )
            last_clap = 0.0
            prev_rms = 0.0

            while self._running:
                try:
                    data = stm.read(CHUNK, exception_on_overflow=False)
                    samples = struct.unpack(f"{CHUNK}h", data)
                    rms = math.sqrt(sum(s * s for s in samples) / CHUNK)
                    now = time.time()

                    if (
                        rms > CLAP_RMS
                        and rms > prev_rms * 3.0
                        and now - last_clap > COOLDOWN
                    ):
                        last_clap = now
                        self.wake_up()  # safe — just sets _active_until
                        print("  👏 Clap detected — JARVIS activated!")

                    prev_rms = rms * 0.4 + prev_rms * 0.6
                except Exception:
                    pass

            stm.stop_stream()
            stm.close()
            pa.terminate()
        except Exception as e:
            print(f"  ⚠️  Clap monitor unavailable: {e}")

    def run(self):
        import speech_recognition as sr

        while self._running:
            if time.time() < self._active_until:
                self.state_changed.emit("listening")
                try:
                    text = self.listener.listen(timeout=8)
                except Exception:
                    text = ""
                if text:
                    self._active_until = time.time() + self.ACTIVE_SECS
                    self.state_changed.emit("processing")
                    self.result.emit(text)
                time.sleep(0.2)
                continue

            self.state_changed.emit("sleeping")
            try:
                mic = sr.Microphone()
                with mic as src:
                    self._rec.adjust_for_ambient_noise(src, duration=0.3)
                    try:
                        audio = self._rec.listen(src, timeout=3, phrase_time_limit=3)
                    except sr.WaitTimeoutError:
                        continue
                try:
                    heard = self._rec.recognize_google(audio, language="en-IN").lower()
                    if any(w in heard for w in self.WAKE_WORDS):
                        self.state_changed.emit("wake")
                        self._active_until = time.time() + self.ACTIVE_SECS
                except Exception:
                    pass
            except Exception:
                time.sleep(0.5)

    def wake_up(self):
        self._active_until = time.time() + self.ACTIVE_SECS

    def stop(self):
        self._running = False


# ─────────────────────────────────────────────────────────────────────────────
#  TargetingReticleWidget  —  two counter-rotating dashed circles
# ─────────────────────────────────────────────────────────────────────────────
class TargetingReticleWidget(QWidget):
    """
    Transparent overlay placed on top of the Arc Reactor.
    Draws:
      • Outer dashed circle — rotates CW at 0.20°/frame
      • Inner dashed circle — rotates CCW at 0.35°/frame
      • 4 tick marks at 0°, 90°, 180°, 270°
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._outer_angle = 0.0
        self._inner_angle = 0.0

        _t = QTimer(self)
        _t.timeout.connect(self._tick)
        _t.start(16)  # ≈ 60 fps

    def _tick(self):
        self._outer_angle = (self._outer_angle + 0.20) % 360.0
        self._inner_angle = (self._inner_angle - 0.35) % 360.0
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0
        outer_r = min(w, h) / 2.0 - 8
        inner_r = outer_r * 0.82

        # ── Outer circle  (CW) ───────────────────────────────────────────
        op = QPen(QColor(0, 212, 255, 60), 1.5)
        op.setStyle(Qt.CustomDashLine)
        op.setDashPattern([8, 10])
        painter.setPen(op)
        painter.setBrush(Qt.NoBrush)
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(self._outer_angle)
        painter.drawEllipse(QRectF(-outer_r, -outer_r, outer_r * 2, outer_r * 2))
        painter.restore()

        # ── Inner circle  (CCW) ──────────────────────────────────────────
        ip = QPen(QColor(0, 212, 255, 60), 1.5)
        ip.setStyle(Qt.CustomDashLine)
        ip.setDashPattern([6, 8])
        painter.setPen(ip)
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(self._inner_angle)
        painter.drawEllipse(QRectF(-inner_r, -inner_r, inner_r * 2, inner_r * 2))
        painter.restore()

        # ── Cardinal tick marks ──────────────────────────────────────────
        tick_pen = QPen(QColor(0, 212, 255, 110), 2.0)
        tick_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(tick_pen)
        for deg in (0, 90, 180, 270):
            rad = math.radians(deg)
            x1 = cx + math.cos(rad) * (outer_r - 10)
            y1 = cy + math.sin(rad) * (outer_r - 10)
            x2 = cx + math.cos(rad) * (outer_r + 5)
            y2 = cy + math.sin(rad) * (outer_r + 5)
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        painter.end()


# ─────────────────────────────────────────────────────────────────────────────
#  JARVISWindow  —  main HUD window
# ─────────────────────────────────────────────────────────────────────────────
class JARVISWindow(QMainWindow):
    add_user_msg = pyqtSignal(str)
    add_jarvis_msg = pyqtSignal(str)
    add_system_msg = pyqtSignal(str)
    update_status = pyqtSignal(str)

    def __init__(self, jarvis=None):
        super().__init__()
        self.jarvis = jarvis
        self._voice_thread = None
        self._drag_pos = None

        self.setWindowTitle("JARVIS — Iron Man HUD")
        self.setMinimumSize(1200, 750)
        self.resize(1600, 900)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self._build()
        self._signals()

    # ── resize → keep background layer synced ────────────────────────────
    def resizeEvent(self, e):
        super().resizeEvent(e)
        if hasattr(self, "_bg"):
            cw = self.centralWidget()
            if cw:
                self._bg.setGeometry(0, 0, cw.width(), cw.height())

    # ─────────────────────────────────────────────────────────────────────
    #  Build UI
    # ─────────────────────────────────────────────────────────────────────
    def _build(self):
        # ── Root widget ───────────────────────────────────────────────────
        root = QWidget()
        root.setObjectName("root")
        root.setStyleSheet("""
            #root {
                background: #020a18;
                border-radius: 14px;
                border: 1px solid rgba(0,212,255,80);
            }
        """)
        self.setCentralWidget(root)

        # ── HUD background layer (sits behind everything) ─────────────────
        self._bg = HudBackground(root)
        self._bg.setGeometry(0, 0, 1920, 1080)
        self._bg.lower()

        # ── Root vertical layout ──────────────────────────────────────────
        vlay = QVBoxLayout(root)
        vlay.setContentsMargins(0, 0, 0, 0)
        vlay.setSpacing(0)

        vlay.addWidget(self._title_bar())

        # ── Body ──────────────────────────────────────────────────────────
        body = QWidget()
        body_lay = QHBoxLayout(body)
        body_lay.setContentsMargins(16, 16, 16, 16)
        body_lay.setSpacing(16)

        # ═══ LEFT PANEL — System Status ═══════════════════════════════════
        left_pan = QWidget()
        left_pan.setFixedWidth(290)
        left_pan.setStyleSheet(
            "background: rgba(4,15,35,210);"
            "border: 1px solid rgba(0,212,255,70);"
            "border-radius: 10px;"
        )
        llay = QVBoxLayout(left_pan)
        llay.setContentsMargins(14, 14, 14, 14)
        llay.setSpacing(6)

        # Header
        hdr = QLabel("◈  SYSTEM STATUS")
        hdr.setStyleSheet(
            f"color:{C_CYAN}; font:bold 13px 'Orbitron'; letter-spacing:3px;"
        )
        llay.addWidget(hdr)

        sep0 = QFrame()
        sep0.setFrameShape(QFrame.HLine)
        sep0.setFrameShadow(QFrame.Plain)
        sep0.setStyleSheet(
            "QFrame { border: none; border-top: 1px solid rgba(0,212,255,70);"
            "margin-top: 2px; margin-bottom: 4px; }"
        )
        llay.addWidget(sep0)

        # Gauges row 1 — CPU, RAM
        g1 = QHBoxLayout()
        self._cpu = GaugeWidget("CPU", C_CYAN)
        self._ram = GaugeWidget("RAM", C_CYAN)
        g1.addWidget(self._cpu)
        g1.addWidget(self._ram)
        llay.addLayout(g1)

        # Gauges row 2 — GPU, BATTERY
        g2 = QHBoxLayout()
        self._gpu = GaugeWidget("GPU", "#ff6600")
        bat = psutil.sensors_battery()
        bat_color = "#00ff88" if bat and bat.percent > 20 else "#ff0044"
        self._bat = GaugeWidget("BATTERY", bat_color)
        if bat:
            self._bat.set_value(bat.percent)
        g2.addWidget(self._gpu)
        g2.addWidget(self._bat)
        llay.addLayout(g2)

        # Network
        net_lbl = QLabel("◈  NETWORK ACTIVITY")
        net_lbl.setStyleSheet(
            f"color:{C_TEXT_SEC}; font:bold 11px 'Orbitron';"
            "letter-spacing:2px; margin-top:8px;"
        )
        llay.addWidget(net_lbl)

        self._net_graph = NetGraphWidget()
        llay.addWidget(self._net_graph)

        # Disk
        self._disk = QLabel("DISK: Loading...")
        self._disk.setStyleSheet(
            f"color:{C_TEXT_SEC}; font:12px 'Share Tech Mono'; margin-top:4px;"
        )
        llay.addWidget(self._disk)

        llay.addStretch()

        # ONLINE indicator
        online_lbl = QLabel("◉  ONLINE")
        online_lbl.setAlignment(Qt.AlignCenter)
        online_lbl.setStyleSheet(
            "color: #00ff88; font: bold 11px 'Orbitron';"
            "letter-spacing: 3px; margin-top: 4px;"
        )
        llay.addWidget(online_lbl)

        body_lay.addWidget(left_pan)

        # ═══ CENTRE PANEL ═════════════════════════════════════════════════
        cen_pan = QWidget()
        clay = QVBoxLayout(cen_pan)
        clay.setContentsMargins(0, 0, 0, 0)
        clay.setSpacing(8)

        # Arc Reactor + Targeting Reticle container
        reactor_container = QWidget()
        reactor_container.setFixedSize(380, 380)
        reactor_container.setAttribute(Qt.WA_TranslucentBackground)

        self._orb = ArcReactorWidget()
        self._orb.setParent(reactor_container)
        self._orb.setGeometry(20, 20, 340, 340)
        self._orb.show()

        self._reticle = TargetingReticleWidget(reactor_container)
        self._reticle.setGeometry(0, 0, 380, 380)
        self._reticle.show()
        self._reticle.raise_()

        reactor_wrap = QWidget()
        rw_lay = QHBoxLayout(reactor_wrap)
        rw_lay.setContentsMargins(0, 0, 0, 0)
        rw_lay.setAlignment(Qt.AlignCenter)
        rw_lay.addWidget(reactor_container)
        clay.addWidget(reactor_wrap, 0, Qt.AlignCenter)

        # State text
        self._state_lbl = QLabel("SYSTEM IDLE")
        self._state_lbl.setAlignment(Qt.AlignCenter)
        self._state_lbl.setStyleSheet(
            f"color:{C_TEXT_SEC}; font: 11px 'Orbitron';"
            "letter-spacing: 5px; margin-top: 2px;"
        )
        clay.addWidget(self._state_lbl)

        # Waveform
        self._waveform = WaveformWidget()
        self._waveform.setFixedHeight(55)
        clay.addWidget(self._waveform)

        # Chat
        self._chat = HudChatDisplay()
        self._chat.setStyleSheet(f"background: {C_PANEL}; border-radius: 8px;")
        clay.addWidget(self._chat, stretch=2)

        body_lay.addWidget(cen_pan, stretch=1)

        # ═══ RIGHT PANEL — Quick Access ════════════════════════════════════
        right_pan = QWidget()
        right_pan.setFixedWidth(250)
        right_pan.setStyleSheet(
            "background: rgba(4,15,35,210);"
            "border: 1px solid rgba(0,212,255,70);"
            "border-radius: 10px;"
        )
        rlay = QVBoxLayout(right_pan)
        rlay.setContentsMargins(14, 14, 14, 14)
        rlay.setSpacing(2)

        qa_hdr = QLabel("◈  QUICK ACCESS")
        qa_hdr.setStyleSheet(
            f"color:{C_CYAN}; font: bold 13px 'Orbitron'; letter-spacing: 3px;"
        )
        rlay.addWidget(qa_hdr)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.HLine)
        sep1.setFrameShadow(QFrame.Plain)
        sep1.setStyleSheet(
            "QFrame { border: none; border-top: 1px solid rgba(0,212,255,70);"
            "margin-top: 2px; margin-bottom: 4px; }"
        )
        rlay.addWidget(sep1)

        btn_style = """
            QPushButton {
                background: rgba(0,212,255,8);
                color: #00d4ff;
                border: 1px solid rgba(0,212,255,50);
                border-left: 3px solid rgba(0,212,255,150);
                border-radius: 6px;
                font: bold 12px 'Orbitron';
                text-align: left;
                padding-left: 14px;
                margin-top: 6px;
                height: 42px;
            }
            QPushButton:hover {
                background: rgba(0,212,255,30);
                border-left: 3px solid #00d4ff;
                color: white;
            }
            QPushButton:pressed {
                background: rgba(0,212,255,60);
                border-left: 3px solid #00d4ff;
            }
        """

        cmds = [
            ("⚡  ACTIVATE", self._wake),
            ("⏹  STOP AUDIO", self._stop_speak),
            ("🌤  WEATHER", lambda: self._quick("weather")),
            ("🕐  TIME", lambda: self._quick("time")),
            ("📰  NEWS", lambda: self._quick("news")),
            ("💻  SYSTEM", lambda: self._quick("system status")),
            ("👁  VISION", lambda: self._quick("what is this")),
            ("📁  FILES", lambda: self._quick("open desktop")),
        ]
        for label, fn in cmds:
            b = QPushButton(label)
            b.setStyleSheet(btn_style)
            b.clicked.connect(fn)
            rlay.addWidget(b)

        rlay.addStretch()

        # Digital clock
        clock = QLabel()
        clock.setAlignment(Qt.AlignCenter)
        clock.setStyleSheet(
            f"color: {C_CYAN}; font: bold 26px 'Share Tech Mono';"
            "letter-spacing: 2px; margin-top: 8px;"
        )

        def update_clock():
            clock.setText(datetime.now().strftime("%H:%M:%S\n%Y-%m-%d"))

        clk_t = QTimer(clock)
        clk_t.timeout.connect(update_clock)
        clk_t.start(1000)
        update_clock()
        rlay.addWidget(clock)

        # Core temp fake readout
        core_temp = QLabel("CORE TEMP  ■  38.4 °C")
        core_temp.setAlignment(Qt.AlignCenter)
        core_temp.setStyleSheet(
            "color: rgba(0,212,255,100); font: 10px 'Share Tech Mono';"
            "letter-spacing: 1px; margin-top: 6px;"
        )
        rlay.addWidget(core_temp)

        body_lay.addWidget(right_pan)

        vlay.addWidget(body, stretch=1)
        vlay.addWidget(self._status_bar())

        # ── Stats refresh timer ────────────────────────────────────────────
        self._prev_net = psutil.net_io_counters()
        self._stats_timer = QTimer(self)
        self._stats_timer.timeout.connect(self._refresh_stats)
        self._stats_timer.start(1000)

    # ─────────────────────────────────────────────────────────────────────
    #  Title bar
    # ─────────────────────────────────────────────────────────────────────
    def _title_bar(self):
        bar = QWidget()
        bar.setObjectName("titleBar")
        bar.setFixedHeight(58)
        bar.setStyleSheet("""
            #titleBar {
                background: rgba(0, 6, 20, 230);
                border-bottom: 1px solid rgba(0,212,255,100);
                border-radius: 14px 14px 0 0;
            }
        """)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(20, 0, 12, 0)
        lay.setSpacing(0)

        # ── Left: hex icon + title block ─────────────────────────────────
        title_vlay = QVBoxLayout()
        title_vlay.setSpacing(1)
        title_vlay.setContentsMargins(0, 6, 0, 6)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)

        hex_icon = QLabel("⬡")
        hex_icon.setStyleSheet(f"color: {C_CYAN}; font: bold 22px; margin-right: 2px;")
        title_row.addWidget(hex_icon)

        title_lbl = QLabel("J.A.R.V.I.S")
        title_lbl.setStyleSheet(
            f"color: {C_CYAN}; font: bold 20px 'Orbitron'; letter-spacing: 6px;"
        )
        title_row.addWidget(title_lbl)
        title_vlay.addLayout(title_row)

        sub_lbl = QLabel("JUST A RATHER VERY INTELLIGENT SYSTEM")
        sub_lbl.setStyleSheet(
            f"color: {C_TEXT_SEC}; font: 9px 'Orbitron'; letter-spacing: 3px;"
        )
        title_vlay.addWidget(sub_lbl)
        lay.addLayout(title_vlay)

        lay.addSpacing(28)

        # ── Status dots: SYS, A.I., VOICE ────────────────────────────────
        for dot_label, dot_color in [
            ("SYS", "#00ff88"),
            ("A.I.", "#00ff88"),
            ("VOICE", "#00ff88"),
        ]:
            dv = QVBoxLayout()
            dv.setSpacing(0)
            dv.setAlignment(Qt.AlignCenter)
            d_dot = QLabel("●")
            d_dot.setAlignment(Qt.AlignCenter)
            d_dot.setStyleSheet(f"color: {dot_color}; font: 14px;")
            d_name = QLabel(dot_label)
            d_name.setAlignment(Qt.AlignCenter)
            d_name.setStyleSheet(
                f"color: {C_TEXT_SEC}; font: 7px 'Orbitron'; letter-spacing: 1px;"
            )
            dv.addWidget(d_dot)
            dv.addWidget(d_name)
            dot_wrap = QWidget()
            dot_wrap.setLayout(dv)
            dot_wrap.setFixedWidth(44)
            lay.addWidget(dot_wrap)

        lay.addStretch()

        # ── ONLINE indicator ──────────────────────────────────────────────
        self._status_lbl = QLabel("● ONLINE")
        self._status_lbl.setStyleSheet(
            "color: #00ff88; font: bold 11px 'Orbitron'; margin-right: 18px;"
        )
        lay.addWidget(self._status_lbl)

        # ── Window controls ───────────────────────────────────────────────
        ctrl_data = [
            ("─", self.showMinimized, "#ffaa00"),
            ("□", self._toggle_max, "#00ff88"),
            ("✕", self.close, "#ff3355"),
        ]
        for sym, fn, hov in ctrl_data:
            b = QPushButton(sym)
            b.setFixedSize(34, 34)
            b.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {C_TEXT_SEC};
                    border: 1px solid rgba(0,212,255,60);
                    border-radius: 5px;
                    font: bold 14px;
                    margin-left: 4px;
                }}
                QPushButton:hover {{
                    background: {hov};
                    color: #000;
                    border: 1px solid {hov};
                }}
                QPushButton:pressed {{
                    background: {hov};
                    opacity: 0.8;
                }}
            """)
            b.clicked.connect(fn)
            lay.addWidget(b)

        return bar

    # ─────────────────────────────────────────────────────────────────────
    #  Status bar
    # ─────────────────────────────────────────────────────────────────────
    def _status_bar(self):
        bar = QWidget()
        bar.setObjectName("statusBar")
        bar.setFixedHeight(42)
        bar.setStyleSheet("""
            #statusBar {
                background: rgba(0, 6, 20, 200);
                border-top: 1px solid rgba(0,212,255,80);
                border-radius: 0 0 14px 14px;
            }
        """)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(20, 0, 20, 0)

        self._listen_lbl = QLabel("💤  SAY 'HEY JARVIS' TO ACTIVATE")
        self._listen_lbl.setStyleSheet(
            f"color: {C_TEXT_SEC}; font: bold 12px 'Orbitron'; letter-spacing: 2px;"
        )
        lay.addWidget(self._listen_lbl)
        lay.addStretch()

        ver = QLabel("v3.0.0  |  JARVIS AI  |  SRINI")
        ver.setStyleSheet(
            f"color: {C_TEXT_SEC}; font: 11px 'Share Tech Mono'; letter-spacing: 1px;"
        )
        lay.addWidget(ver)
        return bar

    # ─────────────────────────────────────────────────────────────────────
    #  Stats refresh
    # ─────────────────────────────────────────────────────────────────────
    def _refresh_stats(self):
        # CPU & RAM
        self._cpu.set_value(psutil.cpu_percent())
        self._ram.set_value(psutil.virtual_memory().percent)

        # GPU — local estimate based on CPU load
        gpu_est = min(100, psutil.cpu_percent() * 0.8)
        self._gpu.set_value(gpu_est)

        # Battery — dynamic color (green > 20%, red ≤ 20%)
        bat = psutil.sensors_battery()
        if bat:
            pct = bat.percent
            if pct > 20:
                self._bat._fill_color = lambda: QColor("#00ff88")
            else:
                self._bat._fill_color = lambda: QColor("#ff0044")
            self._bat.set_value(pct)

        # Network
        cur = psutil.net_io_counters()
        up = (cur.bytes_sent - self._prev_net.bytes_sent) / 1024
        down = (cur.bytes_recv - self._prev_net.bytes_recv) / 1024
        self._prev_net = cur
        self._net_graph.add_data(up, down)

        # Disk
        try:
            disk = psutil.disk_usage("C:\\")
            self._disk.setText(
                f"DISK [C:]  {disk.free / 1e9:.1f} GB FREE\n{disk.percent:.0f}% USED"
            )
        except Exception:
            pass

    # ─────────────────────────────────────────────────────────────────────
    #  Signals & Logic
    # ─────────────────────────────────────────────────────────────────────
    def _signals(self):
        self.add_user_msg.connect(lambda t: self._chat.add_message(t, True))
        self.add_jarvis_msg.connect(lambda t: self._chat.add_message(t, False))
        self.add_system_msg.connect(
            lambda t: self._chat.add_message(f"[SYSTEM]: {t}", False)
        )
        self.update_status.connect(self._set_status)

    def _set_status(self, text: str):
        self._listen_lbl.setText(text)
        tl = text.lower()
        if "listen" in tl:
            self._orb.set_listening()
            self._waveform.set_active(True)
            self._state_lbl.setText("ACTIVE  —  LISTENING")
        elif "think" in tl or "process" in tl:
            self._orb.set_thinking()
            self._waveform.set_active(True)
            self._state_lbl.setText("NEURAL  —  PROCESSING")
        elif "speak" in tl:
            self._orb.set_speaking()
            self._waveform.set_active(True)
            self._state_lbl.setText("AUDIO  —  OUTPUT")
        elif "sleep" in tl or "say" in tl:
            self._orb.set_idle()
            self._waveform.set_active(False)
            self._state_lbl.setText("STANDBY  —  MONITORING")
        elif "wake" in tl or "online" in tl:
            self._orb.set_wake()
            self._waveform.set_active(True)
            self._state_lbl.setText("SYSTEM  —  ACTIVATED")

    # ─────────────────────────────────────────────────────────────────────
    #  Voice loop
    # ─────────────────────────────────────────────────────────────────────
    def start_voice_loop(self):
        if not self.jarvis:
            return
        self._voice_thread = VoiceWorker(self.jarvis.listener)
        self._voice_thread.result.connect(self._on_voice)
        self._voice_thread.state_changed.connect(self._on_state)
        self._voice_thread.start()

    def _on_voice(self, text: str):
        self.add_user_msg.emit(text)
        self.update_status.emit("🧠  PROCESSING...")

        def _work():
            try:
                response = self.jarvis.process_command(text)
                if response:
                    self.add_jarvis_msg.emit(response)
                    self.update_status.emit("🔊  SPEAKING...")
                    try:
                        self.jarvis._speak(response)
                    except Exception as e:
                        print(f"[SPEAK ERR] {e}")
            except Exception as e:
                import traceback

                print(f"[CMD ERR] {e}")
                print(traceback.format_exc())
                self.add_jarvis_msg.emit(
                    "Systems encountered an anomaly, sir. Standing by."
                )
            finally:
                self.update_status.emit("🎤  LISTENING...")

        threading.Thread(target=_work, daemon=True).start()

    def _on_state(self, state: str):
        msgs = {
            "sleeping": "💤  SAY 'HEY JARVIS' TO ACTIVATE",
            "wake": "⚡  JARVIS ACTIVATED — LISTENING (60s)",
            "listening": "🎤  LISTENING...",
            "processing": "🧠  PROCESSING...",
        }
        self.update_status.emit(msgs.get(state, state))

    def _quick(self, cmd: str):
        if self._voice_thread:
            self._voice_thread.wake_up()
        self._on_voice(cmd)

    def _wake(self):
        if self._voice_thread:
            self._voice_thread.wake_up()
            self.update_status.emit("⚡  JARVIS ACTIVATED — LISTENING (60s)")
            self._orb.set_wake()
            self.add_system_msg.emit("JARVIS activated manually.")

    def _stop_speak(self):
        if self.jarvis and hasattr(self.jarvis, "speaker"):
            try:
                self.jarvis.speaker.stop()
            except Exception:
                pass
        self.update_status.emit("⚡  INTERRUPTED — LISTENING...")
        self.add_system_msg.emit("Audio interrupted.")

    # ─────────────────────────────────────────────────────────────────────
    #  Window controls & drag
    # ─────────────────────────────────────────────────────────────────────
    def _toggle_max(self):
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and e.y() < 58:
            self._drag_pos = e.globalPos() - self.pos()

    def mouseMoveEvent(self, e):
        if self._drag_pos and e.buttons() == Qt.LeftButton:
            self.move(e.globalPos() - self._drag_pos)

    def mouseReleaseEvent(self, e):
        self._drag_pos = None

    def closeEvent(self, e):
        if self._voice_thread:
            self._voice_thread.stop()
            self._voice_thread.wait(2000)
        e.accept()


# ─────────────────────────────────────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────────────────────────────────────
def launch_gui(jarvis_instance=None):
    try:
        app = QApplication.instance() or QApplication(sys.argv)
        QFontDatabase.addApplicationFont("C:\\Windows\\Fonts\\consola.ttf")

        win = JARVISWindow(jarvis_instance)
        win.showMaximized()
        win.add_system_msg.emit("JARVIS v3.0 — Iron Man HUD Ultra — Online")
        win.add_jarvis_msg.emit(
            "All systems online and operating within normal parameters, sir."
        )
        if jarvis_instance:
            win.start_voice_loop()
        return app, win
    except Exception:
        import traceback

        traceback.print_exc()
        raise
