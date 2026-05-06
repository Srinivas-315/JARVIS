"""
JARVIS — gui/system_stats.py
Real-time system stats sidebar — CPU, RAM, battery, disk.
"""

import psutil
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QProgressBar, QFrame
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont


class StatBar(QFrame):
    """A single stat with label + progress bar."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(4)

        # Title + value label
        self._header = QLabel(title)
        self._header.setFont(QFont("Segoe UI", 9))
        self._header.setStyleSheet("color: rgba(148, 163, 184, 0.8);")

        self._value = QLabel("0%")
        self._value.setFont(QFont("Segoe UI Semibold", 11))
        self._value.setStyleSheet("color: #e2e8f0;")
        self._value.setAlignment(Qt.AlignRight)

        header_layout = QVBoxLayout()
        header_layout.setSpacing(2)
        header_layout.addWidget(self._header)
        header_layout.addWidget(self._value)
        layout.addLayout(header_layout)

        # Progress bar
        self._bar = QProgressBar()
        self._bar.setMaximum(100)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(6)
        self._bar.setStyleSheet("""
            QProgressBar {
                background: rgba(30, 41, 59, 0.8);
                border-radius: 3px;
                border: none;
            }
            QProgressBar::chunk {
                border-radius: 3px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #06b6d4, stop:1 #3b82f6);
            }
        """)
        layout.addWidget(self._bar)

    def set_value(self, value: int, text: str = ""):
        """Update the stat value."""
        self._bar.setValue(min(100, max(0, value)))
        self._value.setText(text or f"{value}%")

        # Color based on value
        if value > 80:
            color = "#ef4444"  # Red — danger
        elif value > 60:
            color = "#f59e0b"  # Yellow — warning
        else:
            color = "#06b6d4"  # Cyan — normal

        self._bar.setStyleSheet(f"""
            QProgressBar {{
                background: rgba(30, 41, 59, 0.8);
                border-radius: 3px;
                border: none;
            }}
            QProgressBar::chunk {{
                border-radius: 3px;
                background: {color};
            }}
        """)


class SystemStats(QWidget):
    """Real-time system stats panel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(180)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Title
        title = QLabel("SYSTEM")
        title.setFont(QFont("Segoe UI Semibold", 10))
        title.setStyleSheet("color: rgba(100, 210, 255, 0.6); letter-spacing: 3px;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Stats
        self._cpu = StatBar("CPU")
        self._ram = StatBar("RAM")
        self._disk = StatBar("DISK")
        self._battery = StatBar("BATTERY")

        layout.addWidget(self._cpu)
        layout.addWidget(self._ram)
        layout.addWidget(self._disk)
        layout.addWidget(self._battery)
        layout.addStretch()

        # Update timer — every 2 seconds
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update)
        self._timer.start(2000)
        self._update()  # Initial update

    def _update(self):
        """Refresh system stats."""
        try:
            cpu = psutil.cpu_percent(interval=0)
            self._cpu.set_value(int(cpu), f"{cpu:.0f}%")

            ram = psutil.virtual_memory()
            used_gb = ram.used / (1024 ** 3)
            total_gb = ram.total / (1024 ** 3)
            self._ram.set_value(int(ram.percent), f"{used_gb:.1f}/{total_gb:.0f} GB")

            disk = psutil.disk_usage('C:\\')
            used_d = disk.used / (1024 ** 3)
            total_d = disk.total / (1024 ** 3)
            self._disk.set_value(int(disk.percent), f"{used_d:.0f}/{total_d:.0f} GB")

            battery = psutil.sensors_battery()
            if battery:
                status = "⚡" if battery.power_plugged else "🔋"
                self._battery.set_value(int(battery.percent), f"{status} {battery.percent:.0f}%")
            else:
                self._battery.set_value(100, "Desktop")

        except Exception:
            pass
