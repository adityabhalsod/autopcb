"""Status-bar widget showing AI online/offline + provider + model."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget

_STATE_COLORS = {
    "online": "#10b981",
    "offline": "#ef4444",
    "connecting": "#f59e0b",
}


class _Dot(QWidget):
    def __init__(self, color: str = "#888888") -> None:
        super().__init__()
        self._color = QColor(color)
        self.setFixedSize(12, 12)

    def set_color(self, color: str) -> None:
        self._color = QColor(color)
        self.update()

    def paintEvent(self, _evt) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(self._color)
        p.setPen(Qt.PenStyle.NoPen)
        r = min(self.width(), self.height()) - 2
        x = (self.width() - r) // 2
        y = (self.height() - r) // 2
        p.drawEllipse(x, y, r, r)


class ModeIndicator(QWidget):
    """Inline indicator: ``● AI ONLINE · Ollama · llama3.2``."""

    def __init__(self) -> None:
        super().__init__()
        self._dot = _Dot(_STATE_COLORS["offline"])
        self._label = QLabel("OFFLINE · Manual Mode")
        self._label.setObjectName("muted")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(6)
        layout.addWidget(self._dot)
        layout.addWidget(self._label)
        self.setToolTip("AI provider status")

    def set_status(
        self, *, online: bool, provider: str = "", model: str = "", state: str | None = None
    ) -> None:
        if state is None:
            state = "online" if online else "offline"
        self._dot.set_color(_STATE_COLORS.get(state, "#888888"))
        if state == "connecting":
            self._label.setText(f"Connecting · {provider}")
        elif online:
            text = f"AI ONLINE · {provider}"
            if model:
                text += f" · {model}"
            self._label.setText(text)
        else:
            self._label.setText("OFFLINE · Manual Mode")
        self._label.setObjectName("accent" if online else "muted")
        # Force re-style after objectName change
        self._label.style().unpolish(self._label)
        self._label.style().polish(self._label)
