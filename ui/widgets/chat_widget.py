"""Chat widget — bubble-style conversation list + input row."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QSize, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QFont, QFontMetrics, QPen, QBrush
from PyQt6.QtWidgets import (
    QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
    QStyledItemDelegate, QVBoxLayout, QWidget, QStyle,
)


ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"
ROLE_SYSTEM = "system"


class _BubbleDelegate(QStyledItemDelegate):
    PADDING = 10
    BUBBLE_R = 8
    MAX_WIDTH_RATIO = 0.78

    def paint(self, painter, option, index) -> None:  # type: ignore[override]
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        role = index.data(Qt.ItemDataRole.UserRole) or ROLE_ASSISTANT

        bubble_color = QColor("#1e3a8a") if role == ROLE_USER else QColor("#5b21b6")
        if role == ROLE_SYSTEM:
            bubble_color = QColor("#313244")
        text_color = QColor("#ffffff") if role != ROLE_SYSTEM else QColor("#cdd6f4")

        viewport_w = option.rect.width()
        max_w = int(viewport_w * self.MAX_WIDTH_RATIO)
        font = option.font
        metrics = QFontMetrics(font)
        available = max(80, max_w - 2 * self.PADDING)
        bounding = metrics.boundingRect(0, 0, available, 10000,
                                        Qt.TextFlag.TextWordWrap, text)
        bubble_w = bounding.width() + 2 * self.PADDING
        bubble_h = bounding.height() + 2 * self.PADDING

        if role == ROLE_USER:
            x = option.rect.right() - bubble_w - 8
        else:
            x = option.rect.left() + 8
        y = option.rect.top() + 4

        painter.setBrush(QBrush(bubble_color))
        painter.setPen(QPen(bubble_color))
        painter.drawRoundedRect(x, y, bubble_w, bubble_h,
                                self.BUBBLE_R, self.BUBBLE_R)
        painter.setPen(QPen(text_color))
        painter.setFont(font)
        painter.drawText(x + self.PADDING, y + self.PADDING,
                         bounding.width(), bounding.height(),
                         Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignTop, text)
        painter.restore()

    def sizeHint(self, option, index) -> QSize:  # type: ignore[override]
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        font = option.font
        metrics = QFontMetrics(font)
        max_w = int(option.rect.width() * self.MAX_WIDTH_RATIO) - 2 * self.PADDING
        if max_w <= 40:
            max_w = 200
        bounding = metrics.boundingRect(0, 0, max_w, 10000,
                                        Qt.TextFlag.TextWordWrap, text)
        return QSize(option.rect.width(), bounding.height() + 2 * self.PADDING + 8)


class ChatWidget(QWidget):
    user_message_sent = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._list = QListWidget()
        self._list.setItemDelegate(_BubbleDelegate(self._list))
        self._list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self._list.setUniformItemSizes(False)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.setStyleSheet("background: transparent; border: none;")
        f = QFont("Inter", 10)
        self._list.setFont(f)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Ask AutoIC to modify or explain the design…")
        self._send = QPushButton("Send")
        self._send.setProperty("primary", True)
        self._send.style().unpolish(self._send)
        self._send.style().polish(self._send)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self._input, 1)
        row.addWidget(self._send, 0)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self._list, 1)
        layout.addLayout(row)

        self._send.clicked.connect(self._submit)
        self._input.returnPressed.connect(self._submit)

        self._stream_timer: QTimer | None = None

    # -- public API ------------------------------------------------------
    def add_message(self, role: str, text: str) -> QListWidgetItem:
        item = QListWidgetItem(text)
        item.setData(Qt.ItemDataRole.UserRole, role)
        self._list.addItem(item)
        self._list.scrollToBottom()
        return item

    def stream_into(self, item: QListWidgetItem, full_text: str,
                    interval_ms: int = 12) -> None:
        """Type tokens into a bubble token-by-token using a QTimer."""
        if self._stream_timer is not None:
            self._stream_timer.stop()
        words = full_text.split(" ")
        idx = {"i": 0, "buf": ""}
        timer = QTimer(self)
        timer.setInterval(interval_ms)

        def tick() -> None:
            if idx["i"] >= len(words):
                timer.stop()
                return
            idx["buf"] = (idx["buf"] + (" " if idx["buf"] else "") + words[idx["i"]])
            item.setText(idx["buf"])
            idx["i"] += 1
            self._list.scrollToBottom()

        timer.timeout.connect(tick)
        timer.start()
        self._stream_timer = timer

    def clear(self) -> None:
        self._list.clear()

    # -- internal --------------------------------------------------------
    def _submit(self) -> None:
        text = self._input.text().strip()
        if not text:
            return
        self.add_message(ROLE_USER, text)
        self._input.clear()
        self.user_message_sent.emit(text)
