"""Interactive schematic canvas (QGraphicsView/QGraphicsScene).

Renders an :class:`ICDesign` as a 2D schematic with IEEE symbols, Manhattan-routed
nets, junction dots, zoom, pan, and SVG/PNG export. No QWebEngineView — pure Qt.
"""

from __future__ import annotations

import math
from typing import Optional

from PyQt6.QtCore import Qt, QPointF, QRectF, pyqtSignal, QSize
from PyQt6.QtGui import (
    QBrush, QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPolygonF,
    QTransform, QPixmap,
)
from PyQt6.QtWidgets import (
    QGraphicsItem, QGraphicsScene, QGraphicsView, QGraphicsPathItem,
    QGraphicsLineItem, QGraphicsEllipseItem, QGraphicsTextItem, QGraphicsRectItem,
)
from PyQt6.QtSvg import QSvgGenerator

from core.design_engine import Component, ICDesign, Net
from core.component_library import ComponentLibrary, ComponentDef


# ---------------------------------------------------------------------------
# Visual constants
# ---------------------------------------------------------------------------
COLOR_BG = QColor("#1a1a28")
COLOR_GRID = QColor("#252535")
COLOR_GRID_MAJOR = QColor("#2f2f45")
COLOR_SYMBOL = QColor("#cdd6f4")
COLOR_SELECTED = QColor("#7c3aed")
COLOR_PIN = QColor("#f9e2af")
COLOR_NET = QColor("#94e2d5")
COLOR_NET_POWER = QColor("#fab387")
COLOR_NET_GROUND = QColor("#a6adc8")
COLOR_NET_CLOCK = QColor("#89b4fa")
COLOR_LABEL = QColor("#cdd6f4")

PIN_RADIUS = 3.0
SYMBOL_W = 80.0
SYMBOL_H = 60.0


def _net_color(net: Net) -> QColor:
    return {
        "power": COLOR_NET_POWER,
        "ground": COLOR_NET_GROUND,
        "clock": COLOR_NET_CLOCK,
    }.get(net.net_type, COLOR_NET)


# ---------------------------------------------------------------------------
# Symbol items — one class, switch on type for the path
# ---------------------------------------------------------------------------
class ComponentItem(QGraphicsItem):
    """A single component drawn as an IEEE symbol."""

    def __init__(self, component: Component) -> None:
        super().__init__()
        self.component = component
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
            | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setPos(component.position)
        self._pin_anchors: dict[str, QPointF] = {}
        self._compute_pin_anchors()
        # Friendly tooltip for non-technical users.
        try:
            from core.component_help import tooltip_for
            comp_def = ComponentLibrary.instance().by_id(component.type)
            if comp_def is not None:
                self.setToolTip(tooltip_for(comp_def))
            else:
                # Fallback: still useful info from the placed instance.
                self.setToolTip(
                    f"<b>{component.id}</b> &mdash; {component.type}"
                    f"<br><i>{component.value or ''}</i>"
                    f"<br><small>Drag to move. Drag from a pin to wire.</small>"
                )
        except Exception:  # noqa: BLE001
            pass

    # -- public helpers --------------------------------------------------
    def pin_at(self, scene_pos: QPointF, tol: float = 8.0) -> Optional[str]:
        """Return the pin name nearest to *scene_pos* within *tol* px, else None."""
        best: Optional[str] = None
        best_d2 = tol * tol
        for name, anchor in self._pin_anchors.items():
            world = self.mapToScene(anchor)
            dx = world.x() - scene_pos.x()
            dy = world.y() - scene_pos.y()
            d2 = dx * dx + dy * dy
            if d2 <= best_d2:
                best = name
                best_d2 = d2
        return best

    def itemChange(self, change, value):  # noqa: D401
        # Snap-to-grid while dragging.
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            grid = 20.0
            return QPointF(round(value.x() / grid) * grid,
                           round(value.y() / grid) * grid)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.component.position = self.pos()
            scene = self.scene()
            if scene is not None:
                view = scene.views()[0] if scene.views() else None
                if view is not None and hasattr(view, "_on_component_moved"):
                    view._on_component_moved(self)
        return super().itemChange(change, value)

    # -- geometry --------------------------------------------------------
    def boundingRect(self) -> QRectF:
        return QRectF(-SYMBOL_W / 2 - 12, -SYMBOL_H / 2 - 12,
                      SYMBOL_W + 24, SYMBOL_H + 36)  # extra room for labels

    def shape(self) -> QPainterPath:
        p = QPainterPath()
        p.addRect(QRectF(-SYMBOL_W / 2, -SYMBOL_H / 2, SYMBOL_W, SYMBOL_H))
        return p

    # -- pin layout -----------------------------------------------------
    def _compute_pin_anchors(self) -> None:
        pins = self.component.pins or []
        n = len(pins)
        if n == 0:
            return
        # Default: input pins on left, output pins on right.
        # Heuristic: last pin is output, others input. Power/ground pins on top/bottom.
        left, right, top, bottom = [], [], [], []
        for p in pins:
            up = p.upper()
            if up in ("VDD", "VCC"):
                top.append(p)
            elif up in ("GND", "VSS"):
                bottom.append(p)
            elif up in ("Y", "Q", "OUT", "OUTPUT", "Z"):
                right.append(p)
            else:
                left.append(p)
        if not right and left:
            right.append(left.pop())  # ensure at least one output side

        def _stack(side: list[str], x: float, y0: float, y1: float) -> None:
            if not side:
                return
            count = len(side)
            for i, name in enumerate(side):
                y = y0 + (i + 1) * (y1 - y0) / (count + 1)
                self._pin_anchors[name] = QPointF(x, y)

        _stack(left,  -SYMBOL_W / 2, -SYMBOL_H / 2, SYMBOL_H / 2)
        _stack(right, SYMBOL_W / 2, -SYMBOL_H / 2, SYMBOL_H / 2)
        for i, name in enumerate(top):
            x = -SYMBOL_W / 2 + (i + 1) * SYMBOL_W / (len(top) + 1)
            self._pin_anchors[name] = QPointF(x, -SYMBOL_H / 2)
        for i, name in enumerate(bottom):
            x = -SYMBOL_W / 2 + (i + 1) * SYMBOL_W / (len(bottom) + 1)
            self._pin_anchors[name] = QPointF(x, SYMBOL_H / 2)

    def pin_scene_pos(self, pin_name: str) -> Optional[QPointF]:
        anchor = self._pin_anchors.get(pin_name)
        if anchor is None:
            return None
        return self.mapToScene(anchor)

    # -- painting --------------------------------------------------------
    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(COLOR_SELECTED if self.isSelected() else COLOR_SYMBOL)
        pen.setWidthF(1.6)
        painter.setPen(pen)
        painter.setBrush(QBrush(QColor("#1e1e2e")))

        t = (self.component.type or "").upper()
        if t in ("AND2", "NAND2"):
            self._paint_and(painter, inverted=t == "NAND2")
        elif t in ("OR2", "NOR2", "XOR2"):
            self._paint_or(painter, exclusive=t == "XOR2", inverted=t == "NOR2")
        elif t in ("NOT", "BUF"):
            self._paint_not(painter, inverted=t == "NOT")
        elif t in ("DFF", "TFF", "JKFF", "LATCH"):
            self._paint_ff(painter)
        elif t in ("MUX2", "MUX4"):
            self._paint_mux(painter)
        elif t == "RES":
            self._paint_res(painter)
        elif t == "CAP":
            self._paint_cap(painter)
        elif t == "IND":
            self._paint_ind(painter)
        elif t == "DIODE":
            self._paint_diode(painter)
        elif t in ("NMOS", "PMOS"):
            self._paint_mos(painter, p_type=(t == "PMOS"))
        elif t == "BJT":
            self._paint_bjt(painter)
        elif t == "OPAMP":
            self._paint_opamp(painter)
        elif t in ("VDD", "VCC"):
            self._paint_vdd(painter)
        elif t in ("GND", "VSS"):
            self._paint_gnd(painter)
        else:
            self._paint_box(painter, t)

        # Pins
        painter.setBrush(QBrush(COLOR_PIN))
        painter.setPen(QPen(COLOR_PIN, 1))
        for name, anchor in self._pin_anchors.items():
            painter.drawEllipse(anchor, PIN_RADIUS, PIN_RADIUS)
            self._paint_pin_label(painter, name, anchor)

        # Reference + value labels
        painter.setPen(QPen(COLOR_LABEL))
        font = QFont("monospace", 8)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(QRectF(-SYMBOL_W / 2 - 6, -SYMBOL_H / 2 - 26, SYMBOL_W + 12, 14),
                         Qt.AlignmentFlag.AlignCenter, self.component.id)
        if self.component.value:
            font.setBold(False)
            painter.setFont(font)
            painter.setPen(QPen(QColor("#a6adc8")))
            painter.drawText(QRectF(-SYMBOL_W / 2 - 6, SYMBOL_H / 2 + 4, SYMBOL_W + 12, 14),
                             Qt.AlignmentFlag.AlignCenter, self.component.value)

    def _paint_pin_label(self, painter: QPainter, name: str, anchor: QPointF) -> None:
        painter.setPen(QPen(QColor("#a6adc8")))
        font = QFont("monospace", 7)
        painter.setFont(font)
        if anchor.x() < 0:
            rect = QRectF(anchor.x() + 4, anchor.y() - 8, 30, 12)
            align = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        elif anchor.x() > 0:
            rect = QRectF(anchor.x() - 34, anchor.y() - 8, 30, 12)
            align = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        elif anchor.y() < 0:
            rect = QRectF(anchor.x() - 14, anchor.y() + 2, 28, 10)
            align = Qt.AlignmentFlag.AlignCenter
        else:
            rect = QRectF(anchor.x() - 14, anchor.y() - 12, 28, 10)
            align = Qt.AlignmentFlag.AlignCenter
        painter.drawText(rect, align, name)

    # -- shape painters --------------------------------------------------
    def _paint_box(self, painter: QPainter, label: str) -> None:
        rect = QRectF(-SYMBOL_W / 2, -SYMBOL_H / 2, SYMBOL_W, SYMBOL_H)
        painter.drawRoundedRect(rect, 4, 4)
        painter.setPen(QPen(COLOR_LABEL))
        font = QFont("monospace", 9)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)

    def _paint_and(self, painter: QPainter, inverted: bool) -> None:
        path = QPainterPath()
        path.moveTo(-SYMBOL_W / 2, -SYMBOL_H / 2)
        path.lineTo(0, -SYMBOL_H / 2)
        path.arcTo(QRectF(-SYMBOL_H / 2, -SYMBOL_H / 2, SYMBOL_H, SYMBOL_H), 90, -180)
        path.lineTo(-SYMBOL_W / 2, SYMBOL_H / 2)
        path.closeSubpath()
        painter.drawPath(path)
        if inverted:
            painter.drawEllipse(QPointF(SYMBOL_H / 2 + 5, 0), 4, 4)

    def _paint_or(self, painter: QPainter, exclusive: bool, inverted: bool) -> None:
        path = QPainterPath()
        path.moveTo(-SYMBOL_W / 2, -SYMBOL_H / 2)
        path.quadTo(QPointF(-SYMBOL_W / 4, 0), QPointF(-SYMBOL_W / 2, SYMBOL_H / 2))
        path.quadTo(QPointF(0, SYMBOL_H / 2), QPointF(SYMBOL_W / 2 - 4, 0))
        path.quadTo(QPointF(0, -SYMBOL_H / 2), QPointF(-SYMBOL_W / 2, -SYMBOL_H / 2))
        painter.drawPath(path)
        if exclusive:
            arc = QPainterPath()
            arc.moveTo(-SYMBOL_W / 2 - 8, -SYMBOL_H / 2)
            arc.quadTo(QPointF(-SYMBOL_W / 4 - 8, 0),
                       QPointF(-SYMBOL_W / 2 - 8, SYMBOL_H / 2))
            painter.drawPath(arc)
        if inverted:
            painter.drawEllipse(QPointF(SYMBOL_W / 2, 0), 4, 4)

    def _paint_not(self, painter: QPainter, inverted: bool) -> None:
        tri = QPolygonF([
            QPointF(-SYMBOL_W / 2, -SYMBOL_H / 2),
            QPointF(SYMBOL_W / 2 - 8, 0),
            QPointF(-SYMBOL_W / 2, SYMBOL_H / 2),
        ])
        painter.drawPolygon(tri)
        if inverted:
            painter.drawEllipse(QPointF(SYMBOL_W / 2 - 4, 0), 4, 4)

    def _paint_ff(self, painter: QPainter) -> None:
        rect = QRectF(-SYMBOL_W / 2, -SYMBOL_H / 2, SYMBOL_W, SYMBOL_H)
        painter.drawRect(rect)
        # Clock triangle
        path = QPainterPath()
        path.moveTo(-SYMBOL_W / 2, SYMBOL_H / 4)
        path.lineTo(-SYMBOL_W / 2 + 8, SYMBOL_H / 4 + 6)
        path.lineTo(-SYMBOL_W / 2, SYMBOL_H / 4 + 12)
        painter.drawPath(path)
        painter.setPen(QPen(COLOR_LABEL))
        font = QFont("monospace", 8)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter,
                         self.component.type.upper())

    def _paint_mux(self, painter: QPainter) -> None:
        poly = QPolygonF([
            QPointF(-SYMBOL_W / 2, -SYMBOL_H / 2),
            QPointF(SYMBOL_W / 2, -SYMBOL_H / 2 + 14),
            QPointF(SYMBOL_W / 2, SYMBOL_H / 2 - 14),
            QPointF(-SYMBOL_W / 2, SYMBOL_H / 2),
        ])
        painter.drawPolygon(poly)
        painter.setPen(QPen(COLOR_LABEL))
        painter.drawText(QRectF(-SYMBOL_W / 2, -SYMBOL_H / 2, SYMBOL_W, SYMBOL_H),
                         Qt.AlignmentFlag.AlignCenter, "MUX")

    def _paint_res(self, painter: QPainter) -> None:
        # Zigzag
        path = QPainterPath()
        path.moveTo(-SYMBOL_W / 2, 0)
        path.lineTo(-SYMBOL_W / 2 + 12, 0)
        zig_x0 = -SYMBOL_W / 2 + 12
        zig_x1 = SYMBOL_W / 2 - 12
        steps = 6
        for i in range(steps):
            x = zig_x0 + (zig_x1 - zig_x0) * (i + 1) / steps
            y = -8 if i % 2 == 0 else 8
            path.lineTo(x, y)
        path.lineTo(zig_x1, 0)
        path.lineTo(SYMBOL_W / 2, 0)
        painter.drawPath(path)

    def _paint_cap(self, painter: QPainter) -> None:
        painter.drawLine(QPointF(-SYMBOL_W / 2, 0), QPointF(-6, 0))
        painter.drawLine(QPointF(-6, -16), QPointF(-6, 16))
        painter.drawLine(QPointF(6, -16), QPointF(6, 16))
        painter.drawLine(QPointF(6, 0), QPointF(SYMBOL_W / 2, 0))

    def _paint_ind(self, painter: QPainter) -> None:
        path = QPainterPath()
        path.moveTo(-SYMBOL_W / 2, 0)
        path.lineTo(-SYMBOL_W / 2 + 8, 0)
        for i in range(4):
            cx = -SYMBOL_W / 2 + 14 + i * 12
            path.arcTo(QRectF(cx - 6, -8, 12, 12), 180, -180)
        path.lineTo(SYMBOL_W / 2, 0)
        painter.drawPath(path)

    def _paint_diode(self, painter: QPainter) -> None:
        painter.drawLine(QPointF(-SYMBOL_W / 2, 0), QPointF(-8, 0))
        tri = QPolygonF([QPointF(-8, -10), QPointF(-8, 10), QPointF(8, 0)])
        painter.drawPolygon(tri)
        painter.drawLine(QPointF(8, -10), QPointF(8, 10))
        painter.drawLine(QPointF(8, 0), QPointF(SYMBOL_W / 2, 0))

    def _paint_mos(self, painter: QPainter, p_type: bool) -> None:
        # Vertical channel line
        painter.drawLine(QPointF(0, -SYMBOL_H / 2 + 8),
                         QPointF(0, SYMBOL_H / 2 - 8))
        # Gate stub
        painter.drawLine(QPointF(-SYMBOL_W / 2, 0), QPointF(-10, 0))
        painter.drawLine(QPointF(-10, -16), QPointF(-10, 16))
        # Drain / Source stubs
        painter.drawLine(QPointF(0, -SYMBOL_H / 2 + 8),
                         QPointF(SYMBOL_W / 2, -SYMBOL_H / 2 + 8))
        painter.drawLine(QPointF(0, SYMBOL_H / 2 - 8),
                         QPointF(SYMBOL_W / 2, SYMBOL_H / 2 - 8))
        # Arrow
        if p_type:
            arrow = QPolygonF([QPointF(-2, 0), QPointF(-8, -3), QPointF(-8, 3)])
        else:
            arrow = QPolygonF([QPointF(0, 0), QPointF(-6, -3), QPointF(-6, 3)])
        painter.setBrush(QBrush(COLOR_SYMBOL))
        painter.drawPolygon(arrow)

    def _paint_bjt(self, painter: QPainter) -> None:
        painter.drawLine(QPointF(-SYMBOL_W / 2, 0), QPointF(-6, 0))
        painter.drawLine(QPointF(-6, -16), QPointF(-6, 16))
        painter.drawLine(QPointF(-6, -10), QPointF(SYMBOL_W / 2, -SYMBOL_H / 2 + 8))
        painter.drawLine(QPointF(-6, 10), QPointF(SYMBOL_W / 2, SYMBOL_H / 2 - 8))

    def _paint_opamp(self, painter: QPainter) -> None:
        tri = QPolygonF([
            QPointF(-SYMBOL_W / 2, -SYMBOL_H / 2),
            QPointF(-SYMBOL_W / 2, SYMBOL_H / 2),
            QPointF(SYMBOL_W / 2 - 4, 0),
        ])
        painter.drawPolygon(tri)
        painter.setPen(QPen(COLOR_LABEL))
        painter.drawText(QRectF(-SYMBOL_W / 2 + 4, -SYMBOL_H / 2 + 4, 16, 12),
                         Qt.AlignmentFlag.AlignCenter, "+")
        painter.drawText(QRectF(-SYMBOL_W / 2 + 4, SYMBOL_H / 2 - 16, 16, 12),
                         Qt.AlignmentFlag.AlignCenter, "−")

    def _paint_vdd(self, painter: QPainter) -> None:
        painter.drawLine(QPointF(0, SYMBOL_H / 2), QPointF(0, -SYMBOL_H / 4))
        painter.drawLine(QPointF(0, -SYMBOL_H / 4), QPointF(-12, -SYMBOL_H / 4 + 10))
        painter.drawLine(QPointF(0, -SYMBOL_H / 4), QPointF(12, -SYMBOL_H / 4 + 10))
        painter.setPen(QPen(COLOR_LABEL))
        font = QFont("monospace", 9)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(QRectF(-20, -SYMBOL_H / 2 - 4, 40, 14),
                         Qt.AlignmentFlag.AlignCenter, "VDD")

    def _paint_gnd(self, painter: QPainter) -> None:
        painter.drawLine(QPointF(0, -SYMBOL_H / 2), QPointF(0, 0))
        painter.drawLine(QPointF(-14, 0), QPointF(14, 0))
        painter.drawLine(QPointF(-9, 6), QPointF(9, 6))
        painter.drawLine(QPointF(-4, 12), QPointF(4, 12))


# ---------------------------------------------------------------------------
# WireItem — user-drawn pin-to-pin connection
# ---------------------------------------------------------------------------
class WireItem(QGraphicsPathItem):
    """L-shaped Manhattan wire that follows two component pins.

    The wire stores references to the source/destination ``ComponentItem`` and
    pin names, plus the ``Net`` it belongs to.  When either component moves
    (or rotates), call :meth:`update_geometry` to repaint.
    """

    def __init__(self, src_item: "ComponentItem", src_pin: str,
                 dst_item: "ComponentItem", dst_pin: str,
                 net, color: QColor) -> None:
        super().__init__()
        self.src_item = src_item
        self.src_pin = src_pin
        self.dst_item = dst_item
        self.dst_pin = dst_pin
        self.net = net
        pen = QPen(color)
        pen.setWidthF(1.8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        self.setPen(pen)
        self.setZValue(-1)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.update_geometry()

    def set_color(self, color: QColor) -> None:
        pen = self.pen()
        pen.setColor(color)
        self.setPen(pen)

    def update_geometry(self) -> None:
        a = self.src_item.pin_scene_pos(self.src_pin)
        b = self.dst_item.pin_scene_pos(self.dst_pin)
        if a is None or b is None:
            return
        path = QPainterPath()
        path.moveTo(a)
        # L-shape: horizontal first, then vertical (good default for IEEE schematics)
        mid = QPointF(b.x(), a.y())
        path.lineTo(mid)
        path.lineTo(b)
        self.setPath(path)


# ---------------------------------------------------------------------------
# Canvas
# ---------------------------------------------------------------------------
class SchematicCanvas(QGraphicsView):
    component_selected = pyqtSignal(object)  # Component or None
    design_changed = pyqtSignal()            # emitted when EDIT mode mutates

    MIME_COMPONENT = "application/x-autoic-component"
    GRID_SNAP = 20.0

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        scene = QGraphicsScene(self)
        scene.setBackgroundBrush(QBrush(COLOR_BG))
        self.setScene(scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        # Repaint the entire viewport on any change so drag previews,
        # rubber-band rectangles and theme switches never leave trails.
        self.setViewportUpdateMode(
            QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._zoom = 1.0
        self._panning = False
        self._pan_start = QPointF()
        self._items: list[ComponentItem] = []
        self._wires: list[WireItem] = []
        self._design: Optional[ICDesign] = None
        self._edit_mode = False
        self._auto_id_counter: dict[str, int] = {}
        self._wire_net_counter = 0
        # Wire-drawing state
        self._wiring: bool = False
        self._wire_src: Optional[tuple[ComponentItem, str]] = None
        self._wire_preview: Optional[QGraphicsPathItem] = None
        scene.selectionChanged.connect(self._on_selection_changed)

    # -- API -------------------------------------------------------------
    def render_design(self, design: ICDesign) -> None:
        self._design = design
        scene = self.scene()
        scene.clear()
        self._items.clear()
        self._draw_grid(design)

        if not design.components:
            placeholder = QGraphicsTextItem("No components yet — generate a design.")
            placeholder.setDefaultTextColor(QColor("#6c7086"))
            placeholder.setPos(20, 20)
            scene.addItem(placeholder)
            return

        anchors: dict[str, QPointF] = {}
        for comp in design.components:
            item = ComponentItem(comp)
            scene.addItem(item)
            self._items.append(item)
            for pin_name in comp.pins:
                pos = item.pin_scene_pos(pin_name)
                if pos is not None:
                    anchors[f"{comp.id}.{pin_name}"] = pos

        # Route nets
        for net in design.nets:
            color = _net_color(net)
            connected = [anchors[p] for p in net.connected_pins if p in anchors]
            if len(connected) < 2:
                continue
            self._route_net(connected, color, net.name)

        # Fit view
        rect = scene.itemsBoundingRect().adjusted(-40, -40, 40, 40)
        scene.setSceneRect(rect)
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        self._zoom = self.transform().m11()

    def export_svg(self, filepath: str) -> None:
        scene = self.scene()
        rect = scene.itemsBoundingRect().adjusted(-40, -40, 40, 40)
        gen = QSvgGenerator()
        gen.setFileName(filepath)
        gen.setSize(QSize(int(rect.width()), int(rect.height())))
        gen.setViewBox(rect)
        gen.setTitle(self._design.spec.name if self._design else "AutoIC schematic")
        gen.setDescription("Generated by AutoIC")
        painter = QPainter(gen)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        scene.render(painter, target=QRectF(0, 0, rect.width(), rect.height()),
                     source=rect)
        painter.end()

    def export_png(self, filepath: str, dpi: int = 300) -> None:
        scene = self.scene()
        rect = scene.itemsBoundingRect().adjusted(-40, -40, 40, 40)
        scale = dpi / 96.0
        img = QImage(int(rect.width() * scale), int(rect.height() * scale),
                     QImage.Format.Format_ARGB32)
        img.fill(COLOR_BG)
        painter = QPainter(img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        scene.render(painter, target=QRectF(0, 0, img.width(), img.height()),
                     source=rect)
        painter.end()
        img.save(filepath, "PNG")

    # -- routing ---------------------------------------------------------
    def _route_net(self, points: list[QPointF], color: QColor, label: str) -> None:
        scene = self.scene()
        pen = QPen(color)
        pen.setWidthF(1.6)
        # Choose a backbone Y (mean of all Y) and connect each pin via a vertical
        # then horizontal segment. Junction dots where ≥3 segments meet a node.
        if len(points) < 2:
            return
        # Manhattan two-segment routes between consecutive sorted points.
        sorted_pts = sorted(points, key=lambda p: (p.x(), p.y()))
        backbone_y = sum(p.y() for p in sorted_pts) / len(sorted_pts)
        # Vertical drop from each pin to backbone
        for pt in sorted_pts:
            line = QGraphicsLineItem(pt.x(), pt.y(), pt.x(), backbone_y)
            line.setPen(pen)
            line.setZValue(-1)
            scene.addItem(line)
        # Horizontal backbone
        x0 = sorted_pts[0].x()
        x1 = sorted_pts[-1].x()
        backbone = QGraphicsLineItem(x0, backbone_y, x1, backbone_y)
        backbone.setPen(pen)
        backbone.setZValue(-1)
        scene.addItem(backbone)
        # Junction dots
        if len(sorted_pts) >= 3:
            for pt in sorted_pts[1:-1]:
                dot = QGraphicsEllipseItem(pt.x() - 3, backbone_y - 3, 6, 6)
                dot.setBrush(QBrush(color))
                dot.setPen(QPen(color))
                dot.setZValue(0)
                scene.addItem(dot)
        # Net label near first segment
        text = QGraphicsTextItem(label)
        text.setDefaultTextColor(color)
        f = QFont("monospace", 7)
        text.setFont(f)
        text.setPos(x0 + 4, backbone_y - 14)
        text.setZValue(0)
        scene.addItem(text)

    # -- grid ------------------------------------------------------------
    def _draw_grid(self, design: ICDesign) -> None:
        scene = self.scene()
        if not design.components:
            scene.setSceneRect(-200, -200, 1200, 800)
            return
        xs = [c.position.x() for c in design.components]
        ys = [c.position.y() for c in design.components]
        rect = QRectF(min(xs) - 200, min(ys) - 200,
                      max(xs) - min(xs) + 800, max(ys) - min(ys) + 600)
        scene.setSceneRect(rect)

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        # Resolve colors from ThemeManager so they update on theme toggle.
        theme_name = ""
        try:
            from .theme_manager import ThemeManager
            _tm = ThemeManager.instance()
            theme_name = (getattr(_tm, "current", "") or "").lower()
            _bg = QColor(_tm.color("canvas_bg"))
            _grid = QColor(_tm.color("grid"))
            _grid_major = QColor(_tm.color("grid_major"))
        except Exception:  # ThemeManager not yet initialised (e.g. offscreen test)
            _bg = COLOR_BG
            _grid = COLOR_GRID
            _grid_major = COLOR_GRID_MAJOR

        # ---- PCB theme: render a realistic green fibreglass + copper look.
        if theme_name == "pcb":
            self._draw_pcb_background(painter, rect, _bg, _grid, _grid_major)
            return

        # ---- Standard schematic grid (dark / light).
        painter.fillRect(rect, _bg)
        step = 20
        left = int(rect.left()) - (int(rect.left()) % step)
        top = int(rect.top()) - (int(rect.top()) % step)
        pen = QPen(_grid)
        pen.setWidthF(0.5)
        painter.setPen(pen)
        x = left
        while x < rect.right():
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            x += step
        y = top
        while y < rect.bottom():
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            y += step
        # Major grid (every 5*step)
        pen.setColor(_grid_major)
        pen.setWidthF(0.8)
        painter.setPen(pen)
        x = left
        while x < rect.right():
            if x % (step * 5) == 0:
                painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            x += step
        y = top
        while y < rect.bottom():
            if y % (step * 5) == 0:
                painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            y += step

    # -- PCB renderer ---------------------------------------------------
    def _draw_pcb_background(self, painter: QPainter, rect: QRectF,
                             bg: QColor, grid: QColor, grid_major: QColor) -> None:
        """Draw a printed-circuit-board look: FR-4 substrate, copper traces,
        gold-plated through-hole pads, and silkscreen reference text.
        Used only when the active theme is ``pcb`` so the canvas resembles a
        real board rather than a flat schematic grid.
        """
        from PyQt6.QtCore import QRect
        from PyQt6.QtGui import QRadialGradient, QFont

        # 1. FR-4 substrate fill with subtle radial vignette.
        grad = QRadialGradient(rect.center(), max(rect.width(), rect.height()) / 1.2)
        grad.setColorAt(0.0, bg.lighter(115))
        grad.setColorAt(1.0, bg.darker(125))
        painter.fillRect(rect, grad)

        step = 40  # pad-to-pad spacing
        left = int(rect.left()) - (int(rect.left()) % step)
        top = int(rect.top()) - (int(rect.top()) % step)

        # 2. Copper trace lattice — translucent gold lines along the grid.
        copper = QColor(212, 175, 55, 70)  # gold, low alpha
        copper_pen = QPen(copper)
        copper_pen.setWidthF(2.2)
        copper_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(copper_pen)
        # Vertical traces every 2 cells, horizontal traces every 2 cells (offset)
        x = left
        col = 0
        while x < rect.right():
            if col % 2 == 0:
                painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            x += step
            col += 1
        y = top
        row = 0
        while y < rect.bottom():
            if row % 2 == 1:
                painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            y += step
            row += 1

        # 3. Solder mask "scratches" — faint major grid for a sense of scale.
        major_pen = QPen(QColor(grid_major.red(), grid_major.green(),
                                grid_major.blue(), 40))
        major_pen.setWidthF(0.6)
        painter.setPen(major_pen)
        x = left
        while x < rect.right():
            if x % (step * 4) == 0:
                painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            x += step
        y = top
        while y < rect.bottom():
            if y % (step * 4) == 0:
                painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            y += step

        # 4. Through-hole pads at every grid intersection.
        pad_outer = QColor(20, 70, 50)        # darker copper-on-mask ring
        pad_gold = QColor(230, 195, 80)       # plated gold
        pad_drill = QColor(20, 30, 25)        # drill hole
        painter.setPen(Qt.PenStyle.NoPen)
        x = left
        while x < rect.right():
            y = top
            while y < rect.bottom():
                # Outer copper ring
                painter.setBrush(pad_outer)
                painter.drawEllipse(QPointF(x, y), 5.5, 5.5)
                # Gold plating
                painter.setBrush(pad_gold)
                painter.drawEllipse(QPointF(x, y), 4.0, 4.0)
                # Drill
                painter.setBrush(pad_drill)
                painter.drawEllipse(QPointF(x, y), 1.4, 1.4)
                y += step
            x += step

        # 5. Silkscreen reference marks every 8 cells (white text).
        silk = QColor(240, 235, 215, 180)
        painter.setPen(silk)
        font = QFont()
        font.setPointSizeF(7.0)
        font.setBold(True)
        painter.setFont(font)
        big = step * 8
        sx = int(rect.left()) - (int(rect.left()) % big)
        sy = int(rect.top()) - (int(rect.top()) % big)
        ref_idx = 0
        x = sx
        while x < rect.right():
            y = sy
            while y < rect.bottom():
                # Tiny corner tick + label
                painter.drawLine(QPointF(x + 8, y + 4), QPointF(x + 18, y + 4))
                painter.drawLine(QPointF(x + 8, y + 4), QPointF(x + 8, y + 12))
                label = f"R{(ref_idx % 99) + 1:02d}"
                painter.drawText(QRect(int(x + 12), int(y + 8), 40, 14), 0, label)
                ref_idx += 1
                y += big
            x += big

    # -- input ----------------------------------------------------------
    def wheelEvent(self, event) -> None:
        mods = event.modifiers()
        # Some platforms swap to angleDelta().x() when Alt is held; fall back to y.
        ad = event.angleDelta()
        delta = ad.y() if ad.y() != 0 else ad.x()
        if delta == 0:
            return
        if mods & Qt.KeyboardModifier.ControlModifier:
            # Ctrl + wheel → zoom in/out
            factor = 1.15 if delta > 0 else 1 / 1.15
            new_zoom = self._zoom * factor
            if 0.1 <= new_zoom <= 8.0:
                self.scale(factor, factor)
                self._zoom = new_zoom
        elif mods & Qt.KeyboardModifier.AltModifier:
            # Alt + wheel → horizontal scroll
            step = -delta // 2
            bar = self.horizontalScrollBar()
            bar.setValue(bar.value() + step)
        else:
            # Normal wheel → vertical scroll
            step = -delta // 2
            bar = self.verticalScrollBar()
            bar.setValue(bar.value() + step)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_start = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        # In EDIT mode, LMB on a pin starts a wire (suppresses component drag).
        if (self._edit_mode and event.button() == Qt.MouseButton.LeftButton
                and not self._wiring):
            scene_pos = self.mapToScene(event.position().toPoint())
            hit = self._pin_hit(scene_pos)
            if hit is not None:
                item, pin_name = hit
                self._begin_wire(item, pin_name)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._panning:
            delta = event.position() - self._pan_start
            self._pan_start = event.position()
            self.horizontalScrollBar().setValue(int(self.horizontalScrollBar().value() - delta.x()))
            self.verticalScrollBar().setValue(int(self.verticalScrollBar().value() - delta.y()))
            event.accept()
            return
        if self._wiring and self._wire_preview is not None and self._wire_src is not None:
            scene_pos = self.mapToScene(event.position().toPoint())
            self._update_wire_preview(scene_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.MiddleButton and self._panning:
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        if self._wiring and event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.position().toPoint())
            hit = self._pin_hit(scene_pos)
            if hit is not None and self._wire_src is not None:
                src_item, src_pin = self._wire_src
                dst_item, dst_pin = hit
                # Reject self-pin / same-component-same-pin wires.
                if not (src_item is dst_item and src_pin == dst_pin):
                    self._commit_wire(src_item, src_pin, dst_item, dst_pin)
            self._cancel_wire()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _on_selection_changed(self) -> None:
        items = self.scene().selectedItems()
        for it in items:
            if isinstance(it, ComponentItem):
                self.component_selected.emit(it.component)
                return
        self.component_selected.emit(None)

    # -- EDIT mode -------------------------------------------------------
    def set_edit_mode(self, enabled: bool) -> None:
        self._edit_mode = bool(enabled)

    @property
    def edit_mode(self) -> bool:
        return self._edit_mode

    def _snap(self, pt: QPointF) -> QPointF:
        g = self.GRID_SNAP
        return QPointF(round(pt.x() / g) * g, round(pt.y() / g) * g)

    def _next_ref(self, comp_id: str) -> str:
        n = self._auto_id_counter.get(comp_id, 0) + 1
        self._auto_id_counter[comp_id] = n
        return f"{comp_id}{n}"

    def _ensure_design(self) -> ICDesign:
        if self._design is None:
            from core.spec_parser import ICSpec
            self._design = ICDesign(
                spec=ICSpec(name="untitled", ic_type="digital",
                            functional_description="Manual schematic"),
                components=[], nets=[], rationale={}, timing_estimates={},
                power_estimate_mw=0.0, area_estimate_um2=0.0,
            )
            self._draw_grid(self._design)
        return self._design

    def add_component_at(self, comp_id: str, scene_pos: QPointF,
                         params: Optional[dict] = None) -> Optional[Component]:
        """Instantiate a ComponentDef onto the canvas (EDIT mode helper)."""
        cdef = ComponentLibrary.instance().by_id(comp_id)
        if cdef is None:
            return None
        design = self._ensure_design()
        ref = self._next_ref(comp_id)
        merged_params = dict(cdef.default_params)
        if params:
            merged_params.update(params)
        value_str = " ".join(f"{k}={v}" for k, v in merged_params.items()
                             if k in ("value", "voltage", "vout", "vref"))
        comp = Component(
            id=ref,
            type=cdef.id,
            value=str(merged_params.get("value") or value_str or ""),
            model=str(merged_params.get("model") or ""),
            pins=[p.name for p in cdef.pins],
            position=self._snap(scene_pos),
            rationale=f"User-placed {cdef.name}.",
        )
        design.components.append(comp)
        item = ComponentItem(comp)
        self.scene().addItem(item)
        self._items.append(item)
        item.setSelected(True)
        self.design_changed.emit()
        return comp

    def remove_selected(self) -> int:
        """Delete selected components and wires (EDIT mode)."""
        removed = 0
        for it in list(self.scene().selectedItems()):
            if isinstance(it, ComponentItem):
                # Drop wires attached to this component.
                for w in list(self._wires):
                    if w.src_item is it or w.dst_item is it:
                        if self._design and w.net in self._design.nets:
                            self._design.nets.remove(w.net)
                        self.scene().removeItem(w)
                        self._wires.remove(w)
                if self._design and it.component in self._design.components:
                    self._design.components.remove(it.component)
                if it in self._items:
                    self._items.remove(it)
                self.scene().removeItem(it)
                removed += 1
            elif isinstance(it, WireItem):
                if self._design and it.net in self._design.nets:
                    self._design.nets.remove(it.net)
                self.scene().removeItem(it)
                if it in self._wires:
                    self._wires.remove(it)
                removed += 1
        if removed:
            self.design_changed.emit()
        return removed

    def rotate_selected(self, degrees: int = 90) -> None:
        for it in self.scene().selectedItems():
            if isinstance(it, ComponentItem):
                it.setRotation((it.rotation() + degrees) % 360)
                self._on_component_moved(it)

    def get_current_design(self) -> Optional[ICDesign]:
        """Return the current EDIT-mode design (or AI-rendered design)."""
        if self._design is None:
            return None
        # Sync component positions back to dataclasses.
        for it in self._items:
            it.component.position = it.pos()
        return self._design

    def clear_canvas(self) -> None:
        self._design = None
        self._items.clear()
        self._wires.clear()
        self._auto_id_counter.clear()
        self._wire_net_counter = 0
        self._cancel_wire()
        self.scene().clear()

    # -- drag and drop ---------------------------------------------------
    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasFormat(self.MIME_COMPONENT):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasFormat(self.MIME_COMPONENT):
            event.acceptProposedAction()
            # Force a full repaint each move so the OS-level drag pixmap
            # never leaves residual ghost copies on the scene background.
            self.viewport().update()
        else:
            super().dragMoveEvent(event)

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        self.viewport().update()
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802
        md = event.mimeData()
        if md.hasFormat(self.MIME_COMPONENT):
            comp_id = bytes(md.data(self.MIME_COMPONENT)).decode("utf-8")
            scene_pos = self.mapToScene(event.position().toPoint())
            comp = self.add_component_at(comp_id, scene_pos)
            if comp is not None:
                event.acceptProposedAction()
                # Wipe any leftover drag-pixmap pixels.
                self.viewport().update()
                return
        super().dropEvent(event)

    # -- keyboard --------------------------------------------------------
    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        if key == Qt.Key.Key_Escape and self._wiring:
            self._cancel_wire()
            event.accept()
            return
        if key == Qt.Key.Key_Delete or key == Qt.Key.Key_Backspace:
            if self.remove_selected():
                event.accept()
                return
        if key == Qt.Key.Key_R:
            self.rotate_selected(90)
            event.accept()
            return
        super().keyPressEvent(event)

    # -- wiring helpers --------------------------------------------------
    def _pin_hit(self, scene_pos: QPointF, tol: float = 8.0
                 ) -> Optional[tuple["ComponentItem", str]]:
        """Find the (item, pin) closest to *scene_pos* within *tol* px."""
        best = None
        for it in self._items:
            name = it.pin_at(scene_pos, tol=tol)
            if name is not None:
                return it, name
        return best

    def _begin_wire(self, item: "ComponentItem", pin_name: str) -> None:
        self._wiring = True
        self._wire_src = (item, pin_name)
        # Net colour from theme manager (signal by default).
        try:
            from .theme_manager import ThemeManager
            color = QColor(ThemeManager.instance().net_color("signal"))
        except Exception:  # noqa: BLE001
            color = COLOR_NET
        preview = QGraphicsPathItem()
        pen = QPen(color)
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setWidthF(1.5)
        preview.setPen(pen)
        preview.setZValue(10)
        self.scene().addItem(preview)
        self._wire_preview = preview
        self.setCursor(Qt.CursorShape.CrossCursor)
        start = item.pin_scene_pos(pin_name) or QPointF()
        self._update_wire_preview(start)

    def _update_wire_preview(self, scene_pos: QPointF) -> None:
        if self._wire_preview is None or self._wire_src is None:
            return
        item, pin = self._wire_src
        a = item.pin_scene_pos(pin)
        if a is None:
            return
        path = QPainterPath()
        path.moveTo(a)
        mid = QPointF(scene_pos.x(), a.y())
        path.lineTo(mid)
        path.lineTo(scene_pos)
        self._wire_preview.setPath(path)

    def _cancel_wire(self) -> None:
        if self._wire_preview is not None:
            self.scene().removeItem(self._wire_preview)
        self._wire_preview = None
        self._wire_src = None
        self._wiring = False
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def _commit_wire(self, src_item: "ComponentItem", src_pin: str,
                     dst_item: "ComponentItem", dst_pin: str) -> None:
        design = self._ensure_design()
        src_ref = f"{src_item.component.id}.{src_pin}"
        dst_ref = f"{dst_item.component.id}.{dst_pin}"

        # Try to merge into an existing net that already touches either pin.
        target_net: Optional[Net] = None
        for n in design.nets:
            if src_ref in n.connected_pins or dst_ref in n.connected_pins:
                target_net = n
                break
        if target_net is None:
            self._wire_net_counter += 1
            net_type = self._infer_net_type(src_item, src_pin, dst_item, dst_pin)
            target_net = Net(
                id=f"N{self._wire_net_counter}",
                name=f"net_{self._wire_net_counter}",
                connected_pins=[],
                net_type=net_type,
            )
            design.nets.append(target_net)
        if src_ref not in target_net.connected_pins:
            target_net.connected_pins.append(src_ref)
        if dst_ref not in target_net.connected_pins:
            target_net.connected_pins.append(dst_ref)

        try:
            from .theme_manager import ThemeManager
            color = QColor(ThemeManager.instance().net_color(target_net.net_type))
        except Exception:  # noqa: BLE001
            color = _net_color(target_net)
        wire = WireItem(src_item, src_pin, dst_item, dst_pin, target_net, color)
        self.scene().addItem(wire)
        self._wires.append(wire)
        self.design_changed.emit()

    @staticmethod
    def _infer_net_type(src_item: "ComponentItem", src_pin: str,
                        dst_item: "ComponentItem", dst_pin: str) -> str:
        s_t = (src_item.component.type or "").upper()
        d_t = (dst_item.component.type or "").upper()
        if s_t in ("VDD", "VCC") or d_t in ("VDD", "VCC"):
            return "power"
        if s_t in ("GND", "VSS") or d_t in ("GND", "VSS"):
            return "ground"
        for pn in (src_pin.upper(), dst_pin.upper()):
            if pn in ("CLK", "CLOCK", "CK"):
                return "clock"
            if pn in ("VDD", "VCC"):
                return "power"
            if pn in ("GND", "VSS"):
                return "ground"
        return "signal"

    def _on_component_moved(self, item: "ComponentItem") -> None:
        """Called by ComponentItem.itemChange when its position changes."""
        for w in self._wires:
            if w.src_item is item or w.dst_item is item:
                w.update_geometry()
        if self._design is not None:
            self.design_changed.emit()
