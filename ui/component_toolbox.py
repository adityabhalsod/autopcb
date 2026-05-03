"""Left-dock component toolbox — searchable tree with drag-and-drop.

Each item starts a ``QDrag`` carrying the component id under MIME type
``application/x-autoic-component``. The schematic canvas accepts drops with
this MIME type.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, QMimeData, QPoint, QSize, pyqtSignal
from PyQt6.QtGui import QColor, QDrag, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QStyle, QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from core.component_library import (
    CATEGORY_COLORS, ComponentDef, ComponentLibrary,
)
from core.component_help import friendly_text, tooltip_for

MIME_COMPONENT = "application/x-autoic-component"


# ---------------------------------------------------------------------------
# Symbol mini-painter — renders a tiny IEEE preview into a QPixmap.
# ---------------------------------------------------------------------------
def render_symbol_pixmap(comp: ComponentDef, size: int = 22,
                         color: str = "#cdd6f4",
                         bg: str = "transparent") -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(QColor(0, 0, 0, 0) if bg == "transparent" else QColor(bg))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color))
    pen.setWidthF(1.4)
    p.setPen(pen)
    s = comp.symbol_type or comp.id
    m = 3
    if s == "RES":
        # Zigzag
        pts = [(m, size//2)]
        seg = (size - 2*m) / 6
        x = m
        for i in range(6):
            x += seg
            y = size//2 - 4 if i % 2 == 0 else size//2 + 4
            pts.append((x, y))
        pts.append((size - m, size//2))
        for i in range(len(pts) - 1):
            p.drawLine(int(pts[i][0]), int(pts[i][1]),
                       int(pts[i+1][0]), int(pts[i+1][1]))
    elif s == "CAP":
        cy = size // 2
        p.drawLine(m, cy, size//2 - 2, cy)
        p.drawLine(size//2 + 2, cy, size - m, cy)
        p.drawLine(size//2 - 2, m + 2, size//2 - 2, size - m - 2)
        p.drawLine(size//2 + 2, m + 2, size//2 + 2, size - m - 2)
    elif s == "IND":
        cy = size // 2
        p.drawLine(m, cy, m + 3, cy)
        p.drawArc(m + 2, cy - 3, 4, 6, 0, 180 * 16)
        p.drawArc(m + 6, cy - 3, 4, 6, 0, 180 * 16)
        p.drawArc(m + 10, cy - 3, 4, 6, 0, 180 * 16)
        p.drawLine(m + 14, cy, size - m, cy)
    elif s in ("DIODE", "ZENER", "LED"):
        cy = size // 2
        p.drawLine(m, cy, size//2 - 2, cy)
        p.drawLine(size//2 - 2, m + 2, size//2 - 2, size - m - 2)
        p.drawLine(size//2 - 2, cy - 5, size//2 + 4, cy)
        p.drawLine(size//2 - 2, cy + 5, size//2 + 4, cy)
        p.drawLine(size//2 + 4, m + 2, size//2 + 4, size - m - 2)
        p.drawLine(size//2 + 4, cy, size - m, cy)
    elif s in ("NMOS", "PMOS"):
        x = size // 2
        p.drawLine(m + 2, m + 2, m + 2, size - m - 2)  # gate
        p.drawLine(x, m + 2, x, size - m - 2)          # channel
        p.drawLine(m + 4, x, x, x)
        p.drawLine(x, m + 2, size - m, m + 2)          # drain
        p.drawLine(x, size - m - 2, size - m, size - m - 2)  # source
    elif s in ("NPN", "PNP"):
        cx, cy = size // 2, size // 2
        p.drawEllipse(cx - 6, cy - 6, 12, 12)
        p.drawLine(m + 1, cy, cx - 3, cy)
        p.drawLine(cx - 3, cy - 4, cx + 4, cy - 8)
        p.drawLine(cx - 3, cy + 4, cx + 4, cy + 8)
    elif s == "OPAMP":
        # Triangle
        pts = [(m, m + 1), (m, size - m - 1), (size - m, size//2)]
        for i in range(len(pts)):
            p.drawLine(int(pts[i][0]), int(pts[i][1]),
                       int(pts[(i+1) % 3][0]), int(pts[(i+1) % 3][1]))
        p.drawText(m + 2, m + 6, "+")
        p.drawText(m + 2, size - m - 1, "-")
    elif s in ("AND", "NAND"):
        p.drawLine(m, m + 1, m + 6, m + 1)
        p.drawLine(m, size - m - 1, m + 6, size - m - 1)
        p.drawArc(m + 6, m, size - 2*m - 6, size - 2*m, -90 * 16, 180 * 16)
        if s == "NAND":
            p.drawEllipse(size - m - 4, size//2 - 2, 4, 4)
    elif s in ("OR", "NOR", "XOR", "XNOR"):
        path = [(m, m + 1), (m + 4, size//2), (m, size - m - 1)]
        for i in range(2):
            p.drawLine(int(path[i][0]), int(path[i][1]),
                       int(path[i+1][0]), int(path[i+1][1]))
        p.drawArc(m + 2, m, size - 2*m - 2, size - 2*m, -60 * 16, 120 * 16)
        if s in ("NOR", "XNOR"):
            p.drawEllipse(size - m - 4, size//2 - 2, 4, 4)
        if s in ("XOR", "XNOR"):
            p.drawArc(m - 2, m, size - 2*m - 4, size - 2*m, -60 * 16, 120 * 16)
    elif s == "NOT" or s == "BUF":
        pts = [(m, m + 1), (m, size - m - 1), (size - m - 3, size//2)]
        for i in range(3):
            p.drawLine(int(pts[i][0]), int(pts[i][1]),
                       int(pts[(i+1) % 3][0]), int(pts[(i+1) % 3][1]))
        if s == "NOT":
            p.drawEllipse(size - m - 4, size//2 - 2, 4, 4)
    elif s == "DFF" or s == "BLOCK" or s == "MUX":
        p.drawRect(m, m + 1, size - 2*m, size - 2*m - 2)
    elif s == "VDD":
        p.drawLine(size//2, m, size//2, size - m - 4)
        p.drawLine(size//2 - 5, m + 2, size//2 + 5, m + 2)
    elif s == "GND":
        cx = size // 2
        p.drawLine(cx, m, cx, size//2)
        p.drawLine(cx - 6, size//2, cx + 6, size//2)
        p.drawLine(cx - 4, size//2 + 2, cx + 4, size//2 + 2)
        p.drawLine(cx - 2, size//2 + 4, cx + 2, size//2 + 4)
    else:
        p.drawRect(m, m + 1, size - 2*m, size - 2*m - 2)
        p.drawText(m + 2, size - m - 4, comp.id[:3])
    p.end()
    return pm


# ---------------------------------------------------------------------------
# Drag-enabled tree
# ---------------------------------------------------------------------------
class _ComponentTree(QTreeWidget):
    component_hovered = pyqtSignal(object)        # ComponentDef | None

    def __init__(self) -> None:
        super().__init__()
        self.setHeaderHidden(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setMouseTracking(True)
        self.setAnimated(True)
        self.setIndentation(14)
        self.setUniformRowHeights(False)
        self.setIconSize(QSize(22, 22))
        self.itemEntered.connect(self._on_item_hovered)
        self.currentItemChanged.connect(self._on_current_changed)

    def _on_item_hovered(self, item, _col=0) -> None:
        comp = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        if isinstance(comp, ComponentDef):
            self.component_hovered.emit(comp)

    def _on_current_changed(self, item, _prev) -> None:
        comp = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        if isinstance(comp, ComponentDef):
            self.component_hovered.emit(comp)

    def startDrag(self, _supportedActions) -> None:  # noqa: N802
        item = self.currentItem()
        if item is None:
            return
        comp = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(comp, ComponentDef):
            return
        mime = QMimeData()
        mime.setData(MIME_COMPONENT, comp.id.encode("utf-8"))
        mime.setText(comp.id)
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.setPixmap(render_symbol_pixmap(comp, size=32))
        drag.setHotSpot(QPoint(16, 16))
        drag.exec(Qt.DropAction.CopyAction)


# ---------------------------------------------------------------------------
# Toolbox widget
# ---------------------------------------------------------------------------
class ComponentToolbox(QWidget):
    """Left-dock palette: search + category tree + preview."""

    component_activated = pyqtSignal(str)   # double-click → component id

    QUICK_IDS = ("R", "C", "L", "NMOS", "PMOS", "NPN", "VDD", "GND",
                 "AND2", "DFF", "OPAMP")

    def __init__(self) -> None:
        super().__init__()
        self._lib = ComponentLibrary.instance()
        self._build()
        self._populate()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # Search
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search components…")
        self._search.textChanged.connect(self._on_search)
        layout.addWidget(self._search)

        # Quick toolbar
        quick = QHBoxLayout()
        quick.setSpacing(2)
        quick.setContentsMargins(0, 0, 0, 0)
        for cid in self.QUICK_IDS:
            comp = self._lib.by_id(cid)
            if not comp:
                continue
            btn = QToolButton()
            btn.setIcon(QIcon(render_symbol_pixmap(comp, size=22)))
            btn.setIconSize(QSize(20, 20))
            btn.setToolTip(tooltip_for(comp))
            btn.clicked.connect(lambda _=False, c=comp: self.component_activated.emit(c.id))
            quick.addWidget(btn)
        quick.addStretch(1)
        quick_w = QWidget()
        quick_w.setLayout(quick)
        layout.addWidget(quick_w)

        # Tree
        self._tree = _ComponentTree()
        self._tree.itemDoubleClicked.connect(self._on_double_click)
        self._tree.component_hovered.connect(self._update_preview)
        layout.addWidget(self._tree, 1)

        # Preview
        preview_box = QFrame()
        preview_box.setFrameShape(QFrame.Shape.StyledPanel)
        preview_layout = QVBoxLayout(preview_box)
        preview_layout.setContentsMargins(8, 6, 8, 8)
        preview_layout.setSpacing(4)
        self._preview_label = QLabel()
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setMinimumHeight(80)
        self._preview_name = QLabel("Hover a component")
        self._preview_name.setObjectName("accent")
        self._preview_desc = QLabel("")
        self._preview_desc.setWordWrap(True)
        self._preview_desc.setObjectName("muted")
        preview_layout.addWidget(self._preview_label)
        preview_layout.addWidget(self._preview_name)
        preview_layout.addWidget(self._preview_desc)
        layout.addWidget(preview_box)

    def _populate(self, query: str = "") -> None:
        self._tree.clear()
        for cat in self._lib.categories():
            comps = [c for c in self._lib.by_category(cat)
                     if not query or query.lower() in c.name.lower()
                     or query.lower() in c.id.lower()]
            if not comps:
                continue
            cat_item = QTreeWidgetItem([cat])
            cat_item.setForeground(0, QColor(CATEGORY_COLORS.get(cat, "#cdd6f4")))
            f = cat_item.font(0)
            f.setBold(True)
            cat_item.setFont(0, f)
            cat_item.setFlags(cat_item.flags() & ~Qt.ItemFlag.ItemIsDragEnabled)
            self._tree.addTopLevelItem(cat_item)
            for comp in comps:
                child = QTreeWidgetItem([f"  {comp.name}  ·  {comp.id}"])
                child.setIcon(0, QIcon(render_symbol_pixmap(comp, size=22)))
                child.setData(0, Qt.ItemDataRole.UserRole, comp)
                child.setToolTip(0, tooltip_for(comp))
                cat_item.addChild(child)
            cat_item.setExpanded(True)

    def _on_search(self, text: str) -> None:
        self._populate(text)

    def _on_double_click(self, item: QTreeWidgetItem, _col: int) -> None:
        comp = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(comp, ComponentDef):
            self.component_activated.emit(comp.id)

    def _update_preview(self, comp: Optional[ComponentDef]) -> None:
        if not isinstance(comp, ComponentDef):
            return
        pm = render_symbol_pixmap(comp, size=80)
        self._preview_label.setPixmap(pm)
        self._preview_name.setText(f"{comp.name}  ({comp.id})")
        pin_count = len(comp.pins)
        self._preview_desc.setText(
            f"{comp.category} · {pin_count} pin{'s' if pin_count != 1 else ''}\n"
            f"{friendly_text(comp)}".strip()
        )

    def refresh(self) -> None:
        """Re-read the library — call after plugins register components."""
        self._populate(self._search.text())
