"""Left-hand spec panel + chat."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .widgets.chat_widget import ChatWidget

IC_TYPES = [
    ("Digital", "digital"),
    ("Analog", "analog"),
    ("Mixed-Signal", "mixed"),
    ("Power", "power"),
]


class SpecPanel(QWidget):
    spec_ready = pyqtSignal(str, str, str)  # name, ic_type, description
    chat_message = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)

        spec_box = QGroupBox("IC Specification")
        form = QFormLayout(spec_box)
        self._name = QLineEdit()
        self._name.setPlaceholderText("e.g. Adder4")
        self._type = QComboBox()
        for label, value in IC_TYPES:
            self._type.addItem(label, value)
        self._desc = QTextEdit()
        self._desc.setPlaceholderText(
            "e.g. Design a 5V to 3.3V LDO voltage regulator with 500mA output current"
        )
        self._desc.setMinimumHeight(100)
        form.addRow("Name:", self._name)
        form.addRow("Type:", self._type)
        form.addRow("Description:", self._desc)

        self._generate_btn = QPushButton("⚡ Generate IC Design")
        self._generate_btn.setProperty("primary", True)
        self._generate_btn.style().unpolish(self._generate_btn)
        self._generate_btn.style().polish(self._generate_btn)
        self._generate_btn.clicked.connect(self._on_generate)

        chat_box = QGroupBox("AutoPCB Assistant")
        chat_layout = QVBoxLayout(chat_box)
        self._chat = ChatWidget()
        self._chat.user_message_sent.connect(self.chat_message)
        chat_layout.addWidget(self._chat)

        splitter = QSplitter(Qt.Orientation.Vertical)
        top = QWidget()
        top_layout = QVBoxLayout(top)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.addWidget(spec_box)
        top_layout.addWidget(self._generate_btn)
        splitter.addWidget(top)
        splitter.addWidget(chat_box)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([320, 360])

        outer.addWidget(splitter, 1)

    # -- public API ------------------------------------------------------
    def chat(self) -> ChatWidget:
        return self._chat

    def set_busy(self, busy: bool) -> None:
        self._generate_btn.setEnabled(not busy)
        self._generate_btn.setText("Generating…" if busy else "⚡ Generate IC Design")

    def current_values(self) -> tuple[str, str, str]:
        return (
            self._name.text().strip(),
            self._type.currentData(),
            self._desc.toPlainText().strip(),
        )

    def set_values(self, name: str, ic_type: str, description: str) -> None:
        self._name.setText(name or "")
        idx = max(
            0,
            [v for _, v in IC_TYPES].index(ic_type) if ic_type in [v for _, v in IC_TYPES] else 0,
        )
        self._type.setCurrentIndex(idx)
        self._desc.setPlainText(description or "")

    # -- internal --------------------------------------------------------
    def _on_generate(self) -> None:
        name, ic_type, desc = self.current_values()
        if not name or not desc:
            return
        self.spec_ready.emit(name, ic_type, desc)
