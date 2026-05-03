"""Animated AI progress widget (label + indeterminate bar)."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QWidget


class ProgressWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._label = QLabel("Idle")
        self._label.setObjectName("muted")
        self._bar = QProgressBar()
        self._bar.setRange(0, 0)  # indeterminate
        self._bar.setVisible(False)
        self._bar.setMaximumWidth(180)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.addWidget(self._label, 1)
        layout.addWidget(self._bar, 0)
        self._timeout = QTimer(self)
        self._timeout.setSingleShot(True)
        self._timeout.timeout.connect(self.stop)

    def start(self, text: str = "Working…") -> None:
        self._label.setText(text)
        self._bar.setVisible(True)

    def update_text(self, text: str) -> None:
        self._label.setText(text)

    def stop(self, text: str = "Ready") -> None:
        self._label.setText(text)
        self._bar.setVisible(False)
