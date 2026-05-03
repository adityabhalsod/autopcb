"""IC design engine.

Owns the dataclasses that flow through the pipeline (`Component`, `Net`,
`ICDesign`) plus a deterministic auto-placer that assigns `QPointF` positions
to components in a readable grid (power top, signal middle, ground bottom).

The Claude calls themselves live in :mod:`core.ai_engine`; this module wires
the spec-to-design stages together asynchronously via callbacks so the UI can
show progress between each stage.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Optional

from PyQt6.QtCore import QObject, QPointF, pyqtSignal

from .ai_engine import AIEngine, AIWorker
from .spec_parser import ICSpec, SpecParser

log = logging.getLogger("autoic.design")


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------
@dataclass
class Component:
    id: str
    type: str
    value: str = ""
    model: str = ""
    pins: list[str] = field(default_factory=list)
    position: QPointF = field(default_factory=lambda: QPointF(0, 0))
    rationale: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "value": self.value,
            "model": self.model,
            "pins": list(self.pins),
            "position": [self.position.x(), self.position.y()],
            "rationale": self.rationale,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "Component":
        pos = raw.get("position") or [0, 0]
        if isinstance(pos, dict):
            pos = [pos.get("x", 0), pos.get("y", 0)]
        return cls(
            id=str(raw.get("id", "")),
            type=str(raw.get("type", "")).upper(),
            value=str(raw.get("value", "")),
            model=str(raw.get("model", "")),
            pins=[str(p) for p in (raw.get("pins") or [])],
            position=QPointF(float(pos[0]), float(pos[1])) if len(pos) >= 2 else QPointF(0, 0),
            rationale=str(raw.get("rationale", "")),
        )


@dataclass
class Net:
    id: str
    name: str
    connected_pins: list[str] = field(default_factory=list)
    net_type: str = "signal"  # power|signal|clock|ground

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict) -> "Net":
        return cls(
            id=str(raw.get("id", "")),
            name=str(raw.get("name", "")),
            connected_pins=[str(p) for p in (raw.get("connected_pins") or [])],
            net_type=str(raw.get("net_type", "signal")).lower(),
        )


@dataclass
class ICDesign:
    spec: ICSpec
    components: list[Component] = field(default_factory=list)
    nets: list[Net] = field(default_factory=list)
    rationale: dict[str, Any] = field(default_factory=dict)
    timing_estimates: dict[str, float] = field(default_factory=dict)
    power_estimate_mw: float = 0.0
    area_estimate_um2: float = 0.0

    def to_dict(self) -> dict:
        return {
            "spec": self.spec.to_dict(),
            "components": [c.to_dict() for c in self.components],
            "nets": [n.to_dict() for n in self.nets],
            "rationale": dict(self.rationale),
            "timing_estimates": dict(self.timing_estimates),
            "power_estimate_mw": self.power_estimate_mw,
            "area_estimate_um2": self.area_estimate_um2,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "ICDesign":
        spec_raw = raw.get("spec") or {}
        spec = SpecParser().parse(spec_raw) if spec_raw else ICSpec(name="unnamed", ic_type="digital")
        return cls(
            spec=spec,
            components=[Component.from_dict(c) for c in raw.get("components", [])],
            nets=[Net.from_dict(n) for n in raw.get("nets", [])],
            rationale=dict(raw.get("rationale") or {}),
            timing_estimates={k: float(v) for k, v in (raw.get("timing_estimates") or {}).items()
                              if isinstance(v, (int, float))},
            power_estimate_mw=float(raw.get("power_estimate_mw", 0.0) or 0.0),
            area_estimate_um2=float(raw.get("area_estimate_um2", 0.0) or 0.0),
        )

    # -- helpers ---------------------------------------------------------
    def find_component(self, comp_id: str) -> Optional[Component]:
        for c in self.components:
            if c.id == comp_id:
                return c
        return None

    def pin_to_net(self) -> dict[str, Net]:
        m: dict[str, Net] = {}
        for net in self.nets:
            for pin in net.connected_pins:
                m[pin] = net
        return m


# ---------------------------------------------------------------------------
# Auto-placer
# ---------------------------------------------------------------------------
# Spacing between component slots. Increased so labels (reference, value,
# pin names) never overlap with neighbouring symbols on dense schematics.
GRID_X = 180   # horizontal spacing between components in a row
GRID_Y = 160   # vertical spacing between rows
ROW_MARGIN_X = 100
ROW_MARGIN_Y = 100
MAX_ROW_LEN = 10  # break long signal rows so the canvas isn't a single line

# Backwards compat — older callers may still import GRID.
GRID = GRID_X
ROW_POWER = 0
ROW_INPUT = 1
ROW_SIGNAL = 2
ROW_OUTPUT = 3
ROW_GROUND = 4

# Component-type → row mapping for the auto-placer.
POWER_TYPES = {"VDD", "VSRC", "ISRC"}
GROUND_TYPES = {"GND", "VSS"}
PASSIVE_TYPES = {"RES", "CAP", "IND", "DIODE"}
ACTIVE_TYPES = {
    "NMOS", "PMOS", "BJT", "OPAMP", "AND2", "OR2", "NAND2", "NOR2", "XOR2",
    "NOT", "MUX2", "MUX4", "DFF", "TFF", "JKFF", "LATCH", "BUF", "ADDER", "FA", "HA",
}


def _row_for(comp_type: str, direction: Optional[str] = None) -> int:
    t = comp_type.upper()
    if t in POWER_TYPES:
        return ROW_POWER
    if t in GROUND_TYPES:
        return ROW_GROUND
    if t.startswith("IN_") or direction == "input":
        return ROW_INPUT
    if t.startswith("OUT_") or direction == "output":
        return ROW_OUTPUT
    if t in PASSIVE_TYPES or t in ACTIVE_TYPES:
        return ROW_SIGNAL
    return ROW_SIGNAL


def auto_place(components: list[Component]) -> None:
    """Assign grid positions in-place using a tidy row-based layout.

    Components are bucketed into 5 horizontal "lanes" — power, inputs,
    signal/active, outputs, ground. Long signal rows wrap onto a second
    line so dense schematics don't end up as one giant horizontal strip.
    Spacing uses :data:`GRID_X` / :data:`GRID_Y` so reference labels and
    pin names have room to breathe.
    """
    rows: dict[int, list[Component]] = {}
    for c in components:
        r = _row_for(c.type)
        rows.setdefault(r, []).append(c)

    # Place each row, wrapping if it has more than MAX_ROW_LEN entries.
    next_extra_row = max(ROW_GROUND, ROW_OUTPUT) + 1
    for r in sorted(rows):
        items = sorted(rows[r], key=lambda c: c.id)
        # Split into chunks of MAX_ROW_LEN so very wide rows wrap.
        for chunk_idx in range(0, len(items), MAX_ROW_LEN):
            chunk = items[chunk_idx:chunk_idx + MAX_ROW_LEN]
            # The first chunk stays on the original row; later chunks go
            # below all standard rows so we don't collide with other lanes.
            row_y_index = r if chunk_idx == 0 else next_extra_row
            if chunk_idx > 0:
                next_extra_row += 1
            for col, comp in enumerate(chunk):
                # Stagger every other component vertically by a half-cell so
                # neighbouring labels don't visually merge.
                stagger = (GRID_Y // 6) if (col % 2) else 0
                comp.position = QPointF(
                    ROW_MARGIN_X + col * GRID_X,
                    ROW_MARGIN_Y + row_y_index * GRID_Y + stagger,
                )


# ---------------------------------------------------------------------------
# DesignEngine
# ---------------------------------------------------------------------------
class DesignEngine(QObject):
    """Sequence the AI calls that turn an ICSpec into an ICDesign.

    Emits `progress(str)` updates and `design_ready(ICDesign)` /
    `error(str)` when the pipeline finishes. Internally chains workers
    so the Qt event loop is never blocked.
    """

    progress = pyqtSignal(str)
    design_ready = pyqtSignal(object)   # ICDesign
    verilog_ready = pyqtSignal(str)
    spice_ready = pyqtSignal(str)
    drc_ready = pyqtSignal(object)      # DRCReport
    bom_ready = pyqtSignal(list)        # list[BOMEntry]
    pipeline_finished = pyqtSignal(object)  # full ICDesign + artifacts dict
    error = pyqtSignal(str)

    def __init__(self, ai: AIEngine, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._ai = ai
        self._current_worker: Optional[AIWorker] = None

    # -- single-step API -------------------------------------------------
    def design(self, spec: ICSpec,
               on_done: Callable[[ICDesign], None],
               on_error: Callable[[str], None]) -> AIWorker:
        """Run only the design (topology+components+nets+rationale) stage."""
        self.progress.emit("Designing topology…")
        worker = self._ai.generate_design(spec.to_dict())

        def _ready(payload: object) -> None:
            try:
                if not isinstance(payload, dict):
                    raise ValueError("design payload not a dict")
                design = ICDesign(
                    spec=spec,
                    components=[Component.from_dict(c) for c in payload.get("components", [])],
                    nets=[Net.from_dict(n) for n in payload.get("nets", [])],
                    rationale=dict(payload.get("rationale") or {}),
                    timing_estimates={k: float(v) for k, v in (payload.get("timing_estimates") or {}).items()
                                      if isinstance(v, (int, float))},
                    power_estimate_mw=float(payload.get("power_estimate_mw") or 0.0),
                    area_estimate_um2=float(payload.get("area_estimate_um2") or 0.0),
                )
                # Ensure VDD/GND nets exist.
                names = {n.name.upper() for n in design.nets}
                if "VDD" not in names:
                    design.nets.append(Net(id=f"N_VDD", name="VDD",
                                           connected_pins=[], net_type="power"))
                if "GND" not in names:
                    design.nets.append(Net(id=f"N_GND", name="GND",
                                           connected_pins=[], net_type="ground"))
                auto_place(design.components)
                self.design_ready.emit(design)
                on_done(design)
            except Exception as e:  # noqa: BLE001
                msg = f"Failed to materialise design: {e}"
                log.exception(msg)
                self.error.emit(msg)
                on_error(msg)

        worker.progress.connect(self.progress)
        worker.response_ready.connect(_ready)
        worker.error.connect(lambda m: (self.error.emit(m), on_error(m)))
        return worker
