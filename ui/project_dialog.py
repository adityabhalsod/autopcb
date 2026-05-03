"""Project dialog — New / Open / Version history."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QHeaderView,
    QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

from core.project_store import ProjectStore


IC_TYPES = [("Digital", "digital"), ("Analog", "analog"),
            ("Mixed-Signal", "mixed"), ("Power", "power")]


class _NewTab(QWidget):
    create_requested = pyqtSignal(str, str, str)  # name, ic_type, description

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._name = QLineEdit()
        self._type = QComboBox()
        for label, value in IC_TYPES:
            self._type.addItem(label, value)
        self._desc = QTextEdit()
        self._desc.setMinimumHeight(120)
        form.addRow("Name:", self._name)
        form.addRow("Type:", self._type)
        form.addRow("Description:", self._desc)
        btn = QPushButton("Create Project")
        btn.setProperty("primary", True)
        btn.clicked.connect(self._on_create)
        layout.addLayout(form)
        layout.addStretch(1)
        layout.addWidget(btn)

    def _on_create(self) -> None:
        name = self._name.text().strip()
        if not name:
            QMessageBox.warning(self, "AutoIC", "Project name required.")
            return
        self.create_requested.emit(name, self._type.currentData(),
                                   self._desc.toPlainText().strip())


class _OpenTab(QWidget):
    open_requested = pyqtSignal(int)
    delete_requested = pyqtSignal(int)

    def __init__(self, store: ProjectStore) -> None:
        super().__init__()
        self._store = store
        layout = QVBoxLayout(self)
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Name", "Type", "Updated", "Versions"])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table, 1)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self._open_btn = QPushButton("Open")
        self._open_btn.setProperty("primary", True)
        self._delete_btn = QPushButton("Delete")
        self._delete_btn.setProperty("danger", True)
        btn_row.addWidget(self._delete_btn)
        btn_row.addWidget(self._open_btn)
        layout.addLayout(btn_row)
        self._open_btn.clicked.connect(self._open)
        self._delete_btn.clicked.connect(self._delete)
        self.refresh()

    def refresh(self) -> None:
        rows = self._store.list_projects()
        self._table.setRowCount(len(rows))
        for r, p in enumerate(rows):
            for c, key in enumerate(("name", "ic_type", "updated_at", "versions")):
                item = QTableWidgetItem(str(p.get(key, "")))
                item.setData(Qt.ItemDataRole.UserRole, p["id"])
                self._table.setItem(r, c, item)

    def _selected_id(self) -> Optional[int]:
        items = self._table.selectedItems()
        if not items:
            return None
        return items[0].data(Qt.ItemDataRole.UserRole)

    def _open(self) -> None:
        pid = self._selected_id()
        if pid is not None:
            self.open_requested.emit(int(pid))

    def _delete(self) -> None:
        pid = self._selected_id()
        if pid is None:
            return
        if QMessageBox.question(self, "Delete project",
                                "Delete this project and all versions?") \
                == QMessageBox.StandardButton.Yes:
            self._store.delete_project(int(pid))
            self.refresh()
            self.delete_requested.emit(int(pid))


class _VersionsTab(QWidget):
    load_requested = pyqtSignal(int)

    def __init__(self, store: ProjectStore) -> None:
        super().__init__()
        self._store = store
        self._project_id: Optional[int] = None
        layout = QVBoxLayout(self)
        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Version", "Created", "Version ID"])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table, 1)
        btn = QPushButton("Load Selected Version")
        btn.setProperty("primary", True)
        btn.clicked.connect(self._load)
        layout.addWidget(btn)

    def set_project(self, project_id: Optional[int]) -> None:
        self._project_id = project_id
        if project_id is None:
            self._table.setRowCount(0)
            return
        rows = self._store.list_versions(project_id)
        self._table.setRowCount(len(rows))
        for r, v in enumerate(rows):
            self._table.setItem(r, 0, QTableWidgetItem(f"v{v['version_num']}"))
            self._table.setItem(r, 1, QTableWidgetItem(v["created_at"]))
            id_item = QTableWidgetItem(str(v["id"]))
            id_item.setData(Qt.ItemDataRole.UserRole, v["id"])
            self._table.setItem(r, 2, id_item)

    def _load(self) -> None:
        items = self._table.selectedItems()
        if not items:
            return
        vid = items[-1].data(Qt.ItemDataRole.UserRole)
        if vid is not None:
            self.load_requested.emit(int(vid))


class ProjectDialog(QDialog):
    project_created = pyqtSignal(int, str, str, str)
    project_opened = pyqtSignal(int)
    version_loaded = pyqtSignal(int)

    def __init__(self, store: ProjectStore, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("AutoIC — Projects")
        self.resize(720, 460)
        self._store = store

        self._tabs = QTabWidget()
        self._new = _NewTab()
        self._open = _OpenTab(store)
        self._versions = _VersionsTab(store)
        self._tabs.addTab(self._new, "New")
        self._tabs.addTab(self._open, "Open")
        self._tabs.addTab(self._versions, "Version History")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(self._tabs, 1)
        layout.addWidget(buttons)

        self._new.create_requested.connect(self._on_create)
        self._open.open_requested.connect(self._on_open)
        self._open.delete_requested.connect(lambda _id: self._versions.set_project(None))

    def _on_create(self, name: str, ic_type: str, description: str) -> None:
        pid = self._store.create_project(name, ic_type)
        self.project_created.emit(pid, name, ic_type, description)
        self.accept()

    def _on_open(self, pid: int) -> None:
        self.project_opened.emit(pid)
        self._versions.set_project(pid)
        self._tabs.setCurrentWidget(self._versions)
