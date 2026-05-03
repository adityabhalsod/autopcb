"""Bottom dock — Verilog | SPICE | BOM | DRC | AI Log tabs."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QGuiApplication, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import (
    QCheckBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QPlainTextEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QTabWidget, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from core.ai_log import AILogBus, AILogRecord
from core.bom_generator import BOMEntry, BOMGenerator
from core.drc_engine import DRCReport, DRCViolation, SEV_FAIL, SEV_PASS, SEV_WARN
from .widgets.code_editor import CodeEditor


class _CodeTab(QWidget):
    def __init__(self, language: str, default_filename: str) -> None:
        super().__init__()
        self.editor = CodeEditor(language=language)
        self._default = default_filename

        copy_btn = QPushButton("Copy")
        save_btn = QPushButton("Save…")
        copy_btn.clicked.connect(self._copy)
        save_btn.clicked.connect(self._save)
        toolbar = QHBoxLayout()
        toolbar.addStretch(1)
        toolbar.addWidget(copy_btn)
        toolbar.addWidget(save_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.editor, 1)
        layout.addLayout(toolbar)

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self.editor.toPlainText())

    def _save(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save", self._default)
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.editor.toPlainText())


class _BOMTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Reference", "Type", "Value", "Model", "Description", "Qty"])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        export_csv = QPushButton("Export CSV…")
        export_json = QPushButton("Export JSON…")
        export_csv.clicked.connect(self._export_csv)
        export_json.clicked.connect(self._export_json)
        toolbar = QHBoxLayout()
        toolbar.addStretch(1)
        toolbar.addWidget(export_csv)
        toolbar.addWidget(export_json)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.table, 1)
        layout.addLayout(toolbar)
        self._entries: list[BOMEntry] = []

    def load(self, entries: list[BOMEntry]) -> None:
        self._entries = entries or []
        self.table.setRowCount(len(self._entries))
        for r, e in enumerate(self._entries):
            for c, v in enumerate([e.reference, e.component_type, e.value,
                                   e.model, e.description, str(e.quantity)]):
                self.table.setItem(r, c, QTableWidgetItem(v))

    def _export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export BOM", "bom.csv",
                                              "CSV (*.csv)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(BOMGenerator.to_csv(self._entries))

    def _export_json(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export BOM", "bom.json",
                                              "JSON (*.json)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(BOMGenerator.to_json(self._entries))


class _DRCTab(QWidget):
    autofix_requested = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Rule", "Component", "Message", "Suggested fix"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setColumnWidth(0, 110)
        self.tree.setColumnWidth(1, 110)
        self.tree.setColumnWidth(2, 320)

        self.autofix_btn = QPushButton("Auto-Fix All")
        self.autofix_btn.setProperty("primary", True)
        self.autofix_btn.clicked.connect(self.autofix_requested)
        toolbar = QHBoxLayout()
        toolbar.addStretch(1)
        toolbar.addWidget(self.autofix_btn)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.tree, 1)
        layout.addLayout(toolbar)

    def load(self, report: DRCReport) -> None:
        self.tree.clear()
        sev_buckets: dict[str, QTreeWidgetItem] = {
            SEV_FAIL: QTreeWidgetItem([f"FAIL ({report.fail_count})"]),
            SEV_WARN: QTreeWidgetItem([f"WARN ({report.warn_count})"]),
            SEV_PASS: QTreeWidgetItem([f"PASS ({report.pass_count})"]),
        }
        sev_buckets[SEV_FAIL].setForeground(0, QBrush(QColor("#f38ba8")))
        sev_buckets[SEV_WARN].setForeground(0, QBrush(QColor("#f9e2af")))
        sev_buckets[SEV_PASS].setForeground(0, QBrush(QColor("#a6e3a1")))
        for bucket in sev_buckets.values():
            self.tree.addTopLevelItem(bucket)
        for v in report.violations:
            child = QTreeWidgetItem([v.rule_id, v.component_ref, v.message,
                                     v.suggested_fix])
            color = {
                SEV_FAIL: QColor("#f38ba8"),
                SEV_WARN: QColor("#f9e2af"),
                SEV_PASS: QColor("#a6e3a1"),
            }.get(v.severity, QColor("#cdd6f4"))
            child.setForeground(0, QBrush(color))
            sev_buckets.get(v.severity, sev_buckets[SEV_PASS]).addChild(child)
        for bucket in sev_buckets.values():
            bucket.setExpanded(True)
        self.autofix_btn.setEnabled(report.fail_count + report.warn_count > 0)


# ---------------------------------------------------------------------------
# AI Log tab
# ---------------------------------------------------------------------------
class _AILogTab(QWidget):
    """Live, colour-coded transcript of every AI request, response and error."""

    LEVEL_COLOURS = {
        "INFO": QColor("#9cdcfe"),
        "WARN": QColor("#dcdcaa"),
        "ERROR": QColor("#f48771"),
        "DEBUG": QColor("#808080"),
    }

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._view = QPlainTextEdit()
        self._view.setReadOnly(True)
        self._view.setMaximumBlockCount(5000)
        # Monospaced for log alignment.
        from PyQt6.QtGui import QFont
        font = QFont("monospace")
        font.setStyleHint(QFont.StyleHint.TypeWriter)
        self._view.setFont(font)

        self._auto_scroll = QCheckBox("Auto-scroll")
        self._auto_scroll.setChecked(True)
        clear_btn = QPushButton("Clear")
        copy_btn = QPushButton("Copy")
        save_btn = QPushButton("Save…")
        clear_btn.clicked.connect(self._clear)
        copy_btn.clicked.connect(self._copy)
        save_btn.clicked.connect(self._save)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("AI activity log"))
        toolbar.addStretch(1)
        toolbar.addWidget(self._auto_scroll)
        toolbar.addWidget(clear_btn)
        toolbar.addWidget(copy_btn)
        toolbar.addWidget(save_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(toolbar)
        layout.addWidget(self._view, 1)

        bus = AILogBus.instance()
        # Replay any buffered records.
        for rec in bus.records():
            self._append(rec)
        bus.record_added.connect(self._append)

    # -- handlers --------------------------------------------------------
    def _append(self, record: AILogRecord) -> None:
        cursor = self._view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QBrush(
            self.LEVEL_COLOURS.get(record.level, QColor("#d4d4d4"))))
        cursor.insertText(record.formatted() + "\n", fmt)
        if self._auto_scroll.isChecked():
            self._view.verticalScrollBar().setValue(
                self._view.verticalScrollBar().maximum())

    def _clear(self) -> None:
        self._view.clear()
        AILogBus.instance().clear()

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self._view.toPlainText())

    def _save(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save AI log", "ai_log.txt", "Text (*.txt);;All files (*)")
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(self._view.toPlainText())


class OutputPanel(QWidget):
    autofix_requested = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._tabs = QTabWidget()
        self._verilog = _CodeTab("verilog", "design.v")
        self._spice = _CodeTab("spice", "design.sp")
        self._bom = _BOMTab()
        self._drc = _DRCTab()
        self._ai_log = _AILogTab()
        self._tabs.addTab(self._verilog, "Verilog")
        self._tabs.addTab(self._spice, "SPICE")
        self._tabs.addTab(self._bom, "BOM")
        self._tabs.addTab(self._drc, "DRC Report")
        self._tabs.addTab(self._ai_log, "AI Log")
        self._drc.autofix_requested.connect(self.autofix_requested)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._tabs)

    # -- API -------------------------------------------------------------
    def load_verilog(self, code: str) -> None:
        self._verilog.editor.set_code(code)

    def load_spice(self, code: str) -> None:
        self._spice.editor.set_code(code)

    def load_bom(self, entries: list[BOMEntry]) -> None:
        self._bom.load(entries)

    def load_drc(self, report: DRCReport) -> None:
        self._drc.load(report)

    def show_drc(self) -> None:
        self._tabs.setCurrentWidget(self._drc)

    def show_ai_log(self) -> None:
        self._tabs.setCurrentWidget(self._ai_log)
