"""Example plugin — Capacitor Array.

The simplest possible AutoPCB plugin: registers a single new component (an
8-pin capacitor array) so it appears in the Components toolbox.

To use:
    cp plugins/example_capacitor_array.py ~/.autopcb/plugins/
    # or just leave it in repo's plugins/ directory
    # …then restart AutoPCB.
"""

from __future__ import annotations


def register(ctx) -> None:
    ctx.declare(
        name="Capacitor Array",
        version="0.1.0",
        author="AutoPCB examples",
        description="Adds an 8-pin capacitor array (CARRAY8) to the toolbox.",
    )

    # The plugin context exposes typed helpers — see core/plugin_manager.py.
    from core.component_library import CAT_PASSIVE, ComponentDef, PinDef

    pins = []
    for i in range(1, 9):
        pins.append(PinDef(name=f"P{i}", direction="passive", side="top"))
        pins.append(PinDef(name=f"N{i}", direction="passive", side="bottom"))

    comp = ComponentDef(
        id="CARRAY8",
        name="Capacitor Array (8x)",
        category=CAT_PASSIVE,
        subcategory="Array",
        symbol_type="BLOCK",
        pins=pins,
        default_params={"value": "100nF", "tolerance": "10%"},
        param_schema={"value": "string", "tolerance": "string"},
        spice_template=(
            "* CARRAY8 {ref}\n"
            "C{ref}_1 {P1} {N1} {value}\n"
            "C{ref}_2 {P2} {N2} {value}\n"
            "C{ref}_3 {P3} {N3} {value}\n"
            "C{ref}_4 {P4} {N4} {value}\n"
            "C{ref}_5 {P5} {N5} {value}\n"
            "C{ref}_6 {P6} {N6} {value}\n"
            "C{ref}_7 {P7} {N7} {value}\n"
            "C{ref}_8 {P8} {N8} {value}\n"
        ),
        verilog_template="",
        color="#74c0fc",
        description="8 independent capacitors in a single package.",
    )
    ctx.register_component(comp)
