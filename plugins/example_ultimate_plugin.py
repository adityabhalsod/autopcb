"""Ultimate AutoPCB Plugin — exhaustive reference example.

Demonstrates **every** plugin extension point in a single file:

1. `register_component` — add a custom component (NE555 timer).
2. `register_ai_provider` — add an offline "echo" AI provider for testing.
3. `register_exporter` — export the design as a KiCad-style flat netlist.
4. `register_drc_rule` — flag ICs that lack a nearby decoupling capacitor.
5. `register_action` — menu action: "Insert Power Tree" drops VDD/GND/decap
   onto the canvas.

Drop this file into ``~/.autopcb/plugins/`` (or keep it bundled in the repo's
``plugins/`` folder) — it loads automatically on next launch.
"""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Any

log = logging.getLogger("autopcb.plugin.ultimate")


# ===========================================================================
# 1) Custom component — 555 Timer
# ===========================================================================
def _build_555_component():
    from core.component_library import (
        CAT_ANALOG,
        ComponentDef,
        PinDef,
    )

    pins = [
        PinDef("GND", "ground", "bottom"),
        PinDef("TRIG", "input", "left"),
        PinDef("OUT", "output", "right"),
        PinDef("RESET", "input", "left"),
        PinDef("CTRL", "input", "left"),
        PinDef("THR", "input", "left"),
        PinDef("DIS", "io", "right"),
        PinDef("VCC", "power", "top"),
    ]
    return ComponentDef(
        id="TIMER555",
        name="NE555 Timer",
        category=CAT_ANALOG,
        subcategory="Timer",
        symbol_type="BLOCK",
        pins=pins,
        default_params={"mode": "astable", "frequency": "1kHz", "duty": "0.5"},
        param_schema={
            "mode": "enum:astable,monostable,bistable",
            "frequency": "string",
            "duty": "string",
        },
        spice_template=(
            "* NE555 timer subcircuit reference\n"
            "X{ref} {GND} {TRIG} {OUT} {RESET} {CTRL} {THR} {DIS} {VCC} NE555\n"
        ),
        verilog_template="",
        color="#ffd43b",
        description="Classic NE555 timer (astable / monostable / bistable).",
    )


# ===========================================================================
# 2) Custom AI provider — offline canned responder, useful for demos & tests
# ===========================================================================
def _build_echo_provider_class():
    from core.ai_provider import AIProvider, AIProviderError

    CANNED_SPEC = {
        "name": "echo_design",
        "ic_type": "digital",
        "functional_description": "Offline echo provider stub design.",
        "inputs": [{"name": "A", "width": 1}, {"name": "B", "width": 1}],
        "outputs": [{"name": "Y", "width": 1}],
        "parameters": {},
        "constraints": {},
    }

    class EchoProvider(AIProvider):
        """A no-network provider that returns deterministic JSON.

        Pick this in Settings → AI Provider when you want to demo the UI on
        a machine with no internet access.
        """

        label = "Echo (offline stub)"
        requires_key = False

        def complete(
            self, system: str, user: str, *, max_tokens: int = 8000, temperature: float = 0.2
        ) -> str:
            text = f"{system}\n---\n{user}".lower()
            if "ic_spec" in text or "specification" in text:
                return json.dumps(CANNED_SPEC)
            if "verilog" in text:
                return (
                    "module echo_top(input A, B, output Y);\n"
                    "  assign Y = A & B;\n"
                    "endmodule\n"
                )
            if "spice" in text or "netlist" in text:
                return (
                    "* Echo SPICE stub\n"
                    ".SUBCKT echo_top A B Y VDD GND\n"
                    "M1 Y A VDD VDD PMOS W=2u L=180n\n"
                    "M2 Y B GND GND NMOS W=1u L=180n\n"
                    ".ENDS\n"
                )
            if "drc" in text:
                return json.dumps(
                    {
                        "violations": [
                            {
                                "rule_id": "ECHO-OK",
                                "severity": "PASS",
                                "component_ref": "*",
                                "message": "Echo provider passes everything.",
                                "suggested_fix": "",
                            }
                        ]
                    }
                )
            return json.dumps({"message": "Echo provider response.", "design_patch": None})

        def health_check(self) -> bool:
            return True

    return EchoProvider


# ===========================================================================
# 3) Custom exporter — flat KiCad-style netlist (.net)
# ===========================================================================
def _export_kicad_netlist(design: Any, path: Path) -> None:
    lines: list[str] = ["(export (version D)", "  (design", "    (source autopcb))"]
    lines.append("  (components")
    for c in design.components:
        lines.append(f"    (comp (ref {c.id})")
        lines.append(f'      (value "{c.value}")')
        lines.append(f'      (footprint "{c.type}")')
        lines.append("    )")
    lines.append("  )")
    lines.append("  (nets")
    for i, net in enumerate(design.nets, start=1):
        lines.append(f'    (net (code {i}) (name "{net.name}")')
        for pin_ref in net.connected_pins:
            comp_id, _, pin = pin_ref.partition(".")
            lines.append(f"      (node (ref {comp_id}) (pin {pin}))")
        lines.append("    )")
    lines.append("  )")
    lines.append(")")
    Path(path).write_text("\n".join(lines), encoding="utf-8")
    log.info("KiCad netlist written to %s", path)


# ===========================================================================
# 4) Custom DRC rule — every IC needs decoupling within 5 pins
# ===========================================================================
_IC_TYPES = {
    "OPAMP",
    "DFF",
    "JKFF",
    "TFF",
    "MUX2",
    "MUX4",
    "ALU4",
    "TIMER555",
    "REGFILE",
    "SRAM6T",
    "UART",
    "SPI",
    "I2C",
    "PWM",
}


def _drc_decoupling(design: Any) -> list[dict]:
    """Warn for every IC that has no capacitor wired to its VDD/VCC pin."""
    out: list[dict] = []

    # Map: net name -> list of (component_id, pin_name)
    pin_to_net: dict[str, str] = {}
    for net in design.nets:
        for pin_ref in net.connected_pins:
            pin_to_net[pin_ref] = net.name

    cap_nets: set[str] = set()
    for c in design.components:
        if c.type.upper() == "CAP":
            for pin in c.pins:
                ref = f"{c.id}.{pin}"
                if ref in pin_to_net:
                    cap_nets.add(pin_to_net[ref])

    for c in design.components:
        if c.type.upper() not in _IC_TYPES:
            continue
        # Find this IC's power pin net.
        power_net = None
        for pin in c.pins:
            if pin.upper() in ("VDD", "VCC"):
                power_net = pin_to_net.get(f"{c.id}.{pin}")
                break
        if power_net is None:
            continue
        if power_net not in cap_nets:
            out.append(
                {
                    "rule_id": "ULT-001",
                    "severity": "WARN",
                    "component_ref": c.id,
                    "message": f"{c.id} ({c.type}) has no decoupling capacitor on {power_net}.",
                    "suggested_fix": f"Add a 100nF cap from {power_net} to GND near {c.id}.",
                }
            )
    return out


# ===========================================================================
# 5) Custom action — Insert Power Tree (VDD + GND + 100nF decap)
# ===========================================================================
def _action_insert_power_tree(main_window: Any) -> None:
    """Drop a tidy VDD/GND/decap stack onto the canvas."""
    from PyQt6.QtCore import QPointF

    canvas = getattr(main_window, "_canvas", None)
    if canvas is None:
        log.warning("Insert Power Tree: no canvas on main window")
        return

    base_x, base_y = 0.0, 0.0
    canvas.add_component_at("VDD", QPointF(base_x, base_y))
    canvas.add_component_at("GND", QPointF(base_x, base_y + 200))
    canvas.add_component_at("C", QPointF(base_x + 120, base_y + 100))

    if hasattr(main_window, "_status"):
        main_window._status.showMessage("Power tree inserted (VDD + GND + decoupling cap).", 4000)


# ===========================================================================
# Plugin entry point
# ===========================================================================
def register(ctx) -> None:
    ctx.declare(
        name="Ultimate Plugin",
        version="1.0.0",
        author="AutoPCB examples",
        description=(
            "Exhaustive reference plugin demonstrating components, AI providers, "
            "exporters, DRC rules, and menu actions."
        ),
    )

    # 1) Component
    try:
        ctx.register_component(_build_555_component())
    except Exception as e:  # noqa: BLE001
        ctx.log.warning("Component registration failed: %s", e)

    # 2) AI provider
    try:
        echo_cls = _build_echo_provider_class()
        ctx.register_ai_provider("echo", echo_cls)
    except Exception as e:  # noqa: BLE001
        ctx.log.warning("AI provider registration failed: %s", e)

    # 3) Exporter
    ctx.register_exporter(
        name="KiCad Netlist",
        extensions=[".net"],
        callback=_export_kicad_netlist,
        description="Flat KiCad-style .net netlist export.",
    )

    # 4) DRC rule
    ctx.register_drc_rule(
        rule_id="ULT-001",
        callback=_drc_decoupling,
        severity="WARN",
        description="Each IC must have a decoupling capacitor on its supply net.",
    )

    # 5) Menu action
    ctx.register_action(
        title="Insert Power Tree (VDD/GND/100nF)",
        callback=_action_insert_power_tree,
        menu="Plugins",
        shortcut="Ctrl+Shift+P",
        tooltip="Insert a VDD/GND/decoupling-cap power tree on the canvas.",
    )
