"""
JARVIS — gui/chat_display.py
ChatGPT-style chat display with colored bubbles and typewriter animation.
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QLabel, QHBoxLayout, QFrame
)
from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QFont, QColor


class ChatBubble(QFrame):
    """A single chat message bubble."""

    def __init__(self, text: str, is_user: bool = True, parent=None):
        super().__init__(parent)
        self.full_text = text
        self.is_user = is_user
        self._char_index = 0

        self.setFrameShape(QFrame.NoFrame)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)

        # Create message label
        self.label = QLabel("")
        self.label.setWordWrap(True)
        self.label.setTextFormat(Qt.PlainText)
        self.label.setFont(QFont("Segoe UI", 11))
        self.label.setMinimumWidth(100)
        self.label.setMaximumWidth(500)

        if is_user:
            # User bubble — right side, blue
            self.label.setStyleSheet("""
                QLabel {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 #2563eb, stop:1 #1d4ed8);
                    color: #ffffff;
                    border-radius: 16px;
                    padding: 12px 16px;
                    font-size: 12px;
                }
            """)
            layout.addStretch()
            layout.addWidget(self.label)
        else:
            # JARVIS bubble — left side, dark glass
            self.label.setStyleSheet("""
                QLabel {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 rgba(30, 41, 59, 220), stop:1 rgba(15, 23, 42, 240));
                    color: #e2e8f0;
                    border-radius: 16px;
                    padding: 12px 16px;
                    border: 1px solid rgba(100, 210, 255, 0.15);
                    font-size: 12px;
                }
            """)
            layout.addWidget(self.label)
            layout.addStretch()

        # Show text immediately for user, typewriter for JARVIS
        if is_user:
            self.label.setText(text)
        else:
            self._start_typewriter()

    def _start_typewriter(self):
        """Typewriter animation for JARVIS responses."""
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._type_char)
        self._timer.start(15)  # 15ms per character — fast but visible

    def _type_char(self):
        """Add one character at a time."""
        if self._char_index < len(self.full_text):
            self._char_index += 1
            self.label.setText(self.full_text[:self._char_index])
        else:
            self._timer.stop()


class ChatDisplay(QScrollArea):
    """Scrollable chat display with message bubbles."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # Container widget
        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setSpacing(8)
        self._layout.setContentsMargins(16, 16, 16, 16)
        self._layout.addStretch()  # Push messages to bottom

        self.setWidget(self._container)

        # Style the scroll area
        self.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            QWidget {
                background: transparent;
            }
            QScrollBar:vertical {
                background: rgba(15, 23, 42, 0.5);
                width: 6px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: rgba(100, 210, 255, 0.3);
                border-radius: 3px;
                min-height: 30px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

    def add_user_message(self, text: str):
        """Add a user message bubble."""
        bubble = ChatBubble(text, is_user=True, parent=self._container)
        self._layout.insertWidget(self._layout.count() - 1, bubble)
        QTimer.singleShot(50, self._scroll_to_bottom)

    def add_jarvis_message(self, text: str):
        """Add a JARVIS response bubble with typewriter effect."""
        bubble = ChatBubble(text, is_user=False, parent=self._container)
        self._layout.insertWidget(self._layout.count() - 1, bubble)
        QTimer.singleShot(50, self._scroll_to_bottom)

    def add_system_message(self, text: str):
        """Add a small system/status message."""
        label = QLabel(text)
        label.setAlignment(Qt.AlignCenter)
        label.setFont(QFont("Segoe UI", 9))
        label.setStyleSheet("color: rgba(148, 163, 184, 0.7); padding: 4px;")
        self._layout.insertWidget(self._layout.count() - 1, label)
        QTimer.singleShot(50, self._scroll_to_bottom)

    def clear_chat(self):
        """Clear all messages."""
        while self._layout.count() > 1:  # Keep the stretch
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _scroll_to_bottom(self):
        """Scroll to the latest message."""
        scrollbar = self.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
