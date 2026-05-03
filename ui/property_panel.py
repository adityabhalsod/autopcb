"""Right-hand property panel — component info, AI rationale, pin table."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFormLayout, QGroupBox, QHeaderView, QLabel, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout, QWidget,
)

from core.design_engine import Component, ICDesign, Net


class PropertyPanel(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._design: Optional[ICDesign] = None
        self._build_ui()
        self.clear()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(10)

        # Component info
        info_box = QGroupBox("Component")
        info_layout = QFormLayout(info_box)
        info_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self._lbl_ref = QLabel("—")
        self._lbl_type = QLabel("—")
        self._lbl_value = QLabel("—")
        self._lbl_model = QLabel("—")
        info_layout.addRow("Reference:", self._lbl_ref)
        info_layout.addRow("Type:", self._lbl_type)
        info_layout.addRow("Value:", self._lbl_value)
        info_layout.addRow("Model:", self._lbl_model)
        outer.addWidget(info_box)

        # Rationale
        rat_box = QGroupBox("AI Rationale")
        rat_layout = QVBoxLayout(rat_box)
        self._rationale = QTextEdit()
        self._rationale.setReadOnly(True)
        self._rationale.setMinimumHeight(80)
        rat_layout.addWidget(self._rationale)
        outer.addWidget(rat_box)

        # Pin table
        pin_box = QGroupBox("Pins")
        pin_layout = QVBoxLayout(pin_box)
        self._pin_table = QTableWidget(0, 3)
        self._pin_table.setHorizontalHeaderLabels(["Pin", "Net", "Type"])
        self._pin_table.verticalHeader().setVisible(False)
        self._pin_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._pin_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        pin_layout.addWidget(self._pin_table)
        outer.addWidget(pin_box, 1)

        # Timing/power
        tp_box = QGroupBox("Estimates")
        tp_layout = QFormLayout(tp_box)
        self._lbl_delay = QLabel("—")
        self._lbl_power = QLabel("—")
        self._lbl_area = QLabel("—")
        tp_layout.addRow("Max delay:", self._lbl_delay)
        tp_layout.addRow("Power:", self._lbl_power)
        tp_layout.addRow("Area:", self._lbl_area)
        outer.addWidget(tp_box)

    # -- public API ------------------------------------------------------
    def set_design(self, design: Optional[ICDesign]) -> None:
        self._design = design
        if design is not None:
            t = design.timing_estimates or {}
            delay = t.get("max_delay_ns")
            self._lbl_delay.setText(f"{delay:.2f} ns" if isinstance(delay, (int, float)) else "—")
            self._lbl_power.setText(f"{design.power_estimate_mw:.2f} mW"
                                    if design.power_estimate_mw else "—")
            self._lbl_area.setText(f"{design.area_estimate_um2:.0f} µm²"
                                   if design.area_estimate_um2 else "—")
        else:
            self._lbl_delay.setText("—")
            self._lbl_power.setText("—")
            self._lbl_area.setText("—")

    def update_component(self, component: Component, rationale: str = "") -> None:
        self._lbl_ref.setText(component.id or "—")
        self._lbl_type.setText(component.type or "—")
        self._lbl_value.setText(component.value or "—")
        self._lbl_model.setText(component.model or "—")
        self._rationale.setPlainText(rationale or component.rationale or "—")

        # Build pin → net map
        pin_to_net: dict[str, Net] = self._design.pin_to_net() if self._design else {}
        self._pin_table.setRowCount(len(component.pins))
        for row, pin_name in enumerate(component.pins):
            ref = f"{component.id}.{pin_name}"
            net = pin_to_net.get(ref)
            self._pin_table.setItem(row, 0, QTableWidgetItem(pin_name))
            self._pin_table.setItem(row, 1, QTableWidgetItem(net.name if net else "—"))
            self._pin_table.setItem(row, 2, QTableWidgetItem(net.net_type if net else "—"))

    def clear(self) -> None:
        self._lbl_ref.setText("—")
        self._lbl_type.setText("—")
        self._lbl_value.setText("—")
        self._lbl_model.setText("—")
        self._rationale.setPlainText("Select a component in the schematic to inspect it.")
        self._pin_table.setRowCount(0)
