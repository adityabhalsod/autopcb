"""DRC engine — deterministic rules + AI-judged rules + auto-fix."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from typing import Iterable

from .design_engine import ICDesign, Component, Net

log = logging.getLogger("autoic.drc")

SEV_PASS = "PASS"
SEV_WARN = "WARN"
SEV_FAIL = "FAIL"


@dataclass
class DRCViolation:
    rule_id: str
    severity: str
    component_ref: str
    message: str
    suggested_fix: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DRCReport:
    violations: list[DRCViolation] = field(default_factory=list)
    pass_count: int = 0
    warn_count: int = 0
    fail_count: int = 0
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "violations": [v.to_dict() for v in self.violations],
            "pass_count": self.pass_count,
            "warn_count": self.warn_count,
            "fail_count": self.fail_count,
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "DRCReport":
        rep = cls(
            violations=[DRCViolation(**v) for v in raw.get("violations", [])
                        if isinstance(v, dict)],
        )
        rep.recount()
        rep.summary = str(raw.get("summary", "")) or rep.summary
        return rep

    def recount(self) -> None:
        self.pass_count = sum(1 for v in self.violations if v.severity == SEV_PASS)
        self.warn_count = sum(1 for v in self.violations if v.severity == SEV_WARN)
        self.fail_count = sum(1 for v in self.violations if v.severity == SEV_FAIL)
        self.summary = (
            f"{self.fail_count} FAIL · {self.warn_count} WARN · {self.pass_count} PASS"
        )


# ---------------------------------------------------------------------------
# DRCEngine
# ---------------------------------------------------------------------------
class DRCEngine:
    """Pure-Python deterministic checks plus optional AI-judged extension."""

    DIGITAL_TYPES = {"AND2", "OR2", "NAND2", "NOR2", "XOR2", "NOT", "DFF",
                     "TFF", "JKFF", "LATCH", "MUX2", "MUX4", "BUF"}
    ANALOG_TYPES = {"OPAMP", "BJT", "NMOS", "PMOS", "DIODE", "RES", "CAP", "IND"}

    def __init__(self) -> None:
        # plugin-registered rules: id -> (callback, severity, description)
        self._extra_rules: dict[str, tuple] = {}

    def register_rule(self, rule_id: str, callback,
                      severity: str = SEV_WARN, description: str = "") -> None:
        """Register a plugin DRC rule.

        ``callback(design)`` must return an iterable of :class:`DRCViolation`
        (or dicts with the same fields). Raises ``ValueError`` if the id is
        already taken or the callback is not callable.
        """
        if not callable(callback):
            raise ValueError("DRC rule callback must be callable")
        if rule_id in self._extra_rules:
            raise ValueError(f"DRC rule '{rule_id}' already registered")
        self._extra_rules[rule_id] = (callback, severity, description)

    def _run_extra_rules(self, design: ICDesign) -> list[DRCViolation]:
        out: list[DRCViolation] = []
        for rule_id, (cb, default_sev, _desc) in self._extra_rules.items():
            try:
                results = cb(design) or []
            except Exception as e:  # noqa: BLE001
                log.warning("Plugin DRC rule '%s' raised: %s", rule_id, e)
                continue
            for r in results:
                if isinstance(r, DRCViolation):
                    out.append(r)
                elif isinstance(r, dict):
                    out.append(DRCViolation(
                        rule_id=str(r.get("rule_id", rule_id)),
                        severity=str(r.get("severity", default_sev)),
                        component_ref=str(r.get("component_ref", "*")),
                        message=str(r.get("message", "")),
                        suggested_fix=str(r.get("suggested_fix", "")),
                    ))
        return out

    def run_deterministic(self, design: ICDesign) -> DRCReport:
        rep = DRCReport()
        ic_type = design.spec.ic_type
        # Build pin-net map
        pin_to_net = design.pin_to_net()
        all_pin_refs = {f"{c.id}.{p}" for c in design.components for p in c.pins}

        # Unconnected pins
        unconnected = [pin for pin in all_pin_refs if pin not in pin_to_net]
        for pin in unconnected:
            rep.violations.append(DRCViolation(
                rule_id="DET-001", severity=SEV_FAIL, component_ref=pin.split(".")[0],
                message=f"Pin {pin} is not connected to any net",
                suggested_fix="Connect the pin to an existing net or remove the component.",
            ))

        # Power & ground presence
        net_names = {n.name.upper() for n in design.nets}
        if "VDD" not in net_names:
            rep.violations.append(DRCViolation(
                rule_id="DET-002", severity=SEV_FAIL, component_ref="*",
                message="No VDD power net defined",
                suggested_fix="Add a VDD net and connect supply pins to it.",
            ))
        if "GND" not in net_names and "0" not in net_names:
            rep.violations.append(DRCViolation(
                rule_id="DET-003", severity=SEV_FAIL, component_ref="*",
                message="No GND/ground net defined",
                suggested_fix="Add a GND net (or alias node 0) and tie sources to it.",
            ))

        # Floating nets
        for net in design.nets:
            if len(net.connected_pins) < 2 and net.net_type not in ("power", "ground"):
                rep.violations.append(DRCViolation(
                    rule_id="DET-004", severity=SEV_FAIL,
                    component_ref=net.name,
                    message=f"Net '{net.name}' has fewer than 2 connections",
                    suggested_fix="Connect the net to at least one driver and one load.",
                ))

        if ic_type == "digital":
            # Fan-out check
            fanout: dict[str, int] = {}
            for net in design.nets:
                if net.net_type in ("power", "ground"):
                    continue
                fanout[net.name] = max(0, len(net.connected_pins) - 1)
            for name, fo in fanout.items():
                if fo > 8:
                    rep.violations.append(DRCViolation(
                        rule_id="DET-010", severity=SEV_WARN, component_ref=name,
                        message=f"Net '{name}' fan-out is {fo} (>8)",
                        suggested_fix="Insert buffers to split the fan-out tree.",
                    ))
            # Undriven inputs (best-effort: any net only connecting to inputs)
            # We don't have direction metadata per pin here, so this is best-effort.

        if ic_type in ("analog", "mixed", "power"):
            # Missing bypass cap on supplies
            has_bypass = any(c.type.upper() == "CAP" and any(
                p.upper() in ("VDD", "GND") for p in c.pins
            ) for c in design.components)
            if not has_bypass:
                rep.violations.append(DRCViolation(
                    rule_id="DET-020", severity=SEV_WARN, component_ref="*",
                    message="No bypass capacitor across VDD/GND",
                    suggested_fix="Add a 100nF capacitor between VDD and GND.",
                ))

        if not rep.violations:
            rep.violations.append(DRCViolation(
                rule_id="DET-OK", severity=SEV_PASS, component_ref="*",
                message="Deterministic DRC passed", suggested_fix="",
            ))
        # Plugin-registered DRC rules (run last so they appear in the report).
        rep.violations.extend(self._run_extra_rules(design))
        rep.recount()
        return rep

    @staticmethod
    def merge(*reports: DRCReport) -> DRCReport:
        merged = DRCReport()
        for r in reports:
            merged.violations.extend(r.violations)
        merged.recount()
        return merged

    @staticmethod
    def from_ai(payload: dict) -> DRCReport:
        return DRCReport.from_dict(payload)

    @staticmethod
    def apply_autofix(payload: dict) -> ICDesign:
        return ICDesign.from_dict(payload)
