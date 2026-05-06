"""SPICE netlist generator.

Like :mod:`verilog_generator`, this module post-processes Claude output and
provides a deterministic fallback. It also performs a node-set sanity check:
power rails defined, no nets that reference a single pin (floating).
"""

from __future__ import annotations

import datetime as _dt
import logging
import re
from typing import Iterable

from .design_engine import ICDesign

log = logging.getLogger("autopcb.spice")


SPICE_PRIMITIVE_PREFIXES = {"R", "C", "L", "M", "Q", "X", "V", "I", "D"}


class NetlistValidationError(ValueError):
    pass


class NetlistGenerator:

    @staticmethod
    def header(design: ICDesign) -> str:
        ts = _dt.datetime.now(_dt.timezone.utc).isoformat()
        spec = design.spec
        return (
            f"* AutoPCB SPICE netlist — {spec.name}\n"
            f"* Generated: {ts}\n"
            f"* IC type: {spec.ic_type} / Tech: {spec.technology_node} / Vdd: {spec.supply_voltage} V\n"
        )

    @classmethod
    def finalize(cls, design: ICDesign, raw_netlist: str) -> str:
        text = (raw_netlist or "").strip()
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)

        # Ensure required structure.
        lines = [ln.rstrip() for ln in text.splitlines()]
        if not lines or not lines[0].lower().startswith(".title"):
            lines.insert(0, f".title {design.spec.name}")
        if not any(ln.strip().lower() == ".end" for ln in lines):
            lines.append(".end")
        text = "\n".join(lines)

        # If anchor analyses missing, append sane defaults.
        if ".op" not in text.lower():
            text = text.replace(".end", ".op\n.end", 1)

        # Strict validation; if it fails fall back to deterministic generator.
        try:
            cls.validate(text)
        except NetlistValidationError as e:
            log.warning("Generated SPICE failed validation (%s) — using fallback", e)
            text = cls.fallback(design)

        return cls.header(design) + "\n" + text.strip() + "\n"

    # -- validation ------------------------------------------------------
    @staticmethod
    def validate(text: str) -> None:
        nodes: set[str] = set()
        node_refcount: dict[str, int] = {}
        has_vdd_source = False
        for raw in text.splitlines():
            ln = raw.strip()
            if not ln or ln.startswith("*"):
                continue
            if ln.startswith("."):
                continue
            head = ln[0].upper()
            if head not in SPICE_PRIMITIVE_PREFIXES:
                continue
            tokens = ln.split()
            if len(tokens) < 3:
                continue
            # Node tokens: between component name and value; conservative -
            # take all tokens after [0] up to the first that looks like a value.
            comp_nodes: list[str] = []
            for tok in tokens[1:]:
                if re.match(r"^[\-+]?\d", tok) or "=" in tok:
                    break
                comp_nodes.append(tok)
            for n in comp_nodes:
                nodes.add(n)
                node_refcount[n] = node_refcount.get(n, 0) + 1
            if head == "V" and any(n.upper() == "VDD" for n in comp_nodes):
                has_vdd_source = True
        if not nodes:
            raise NetlistValidationError("no component nodes found")
        if "0" not in nodes and "GND" not in {n.upper() for n in nodes}:
            raise NetlistValidationError("no ground (0/GND) node defined")
        if not has_vdd_source:
            # Not strictly fatal — many nets use external Vdd — only warn.
            log.info("SPICE: no explicit V* source on VDD — assuming external supply")
        floating = [n for n, c in node_refcount.items() if c < 2 and n.upper() not in {"0", "GND"}]
        if floating:
            log.info("SPICE floating-net candidates: %s", floating)

    # -- fallback --------------------------------------------------------
    @classmethod
    def fallback(cls, design: ICDesign) -> str:
        spec = design.spec
        lines = [f".title {spec.name}", "* AutoPCB fallback netlist"]
        lines.append(f"VDD VDD 0 DC {spec.supply_voltage}")
        # Emit primitives based on component type prefixes.
        for c in design.components:
            t = c.type.upper()
            pin_nets = " ".join(c.pins) if c.pins else "VDD 0"
            if t in ("RES",):
                lines.append(f"R{c.id} {pin_nets} {c.value or '1k'}")
            elif t in ("CAP",):
                lines.append(f"C{c.id} {pin_nets} {c.value or '1u'}")
            elif t in ("IND",):
                lines.append(f"L{c.id} {pin_nets} {c.value or '1u'}")
            elif t in ("NMOS", "PMOS"):
                model = c.model or ("nmos_default" if t == "NMOS" else "pmos_default")
                # MOSFET line: M<id> drain gate source body model
                pads = (list(c.pins) + ["VDD", "0", "0", "0"])[:4]
                lines.append(f"M{c.id} {' '.join(pads)} {model} {c.value or 'W=2u L=180n'}")
            elif t == "BJT":
                pads = (list(c.pins) + ["c", "b", "e"])[:3]
                lines.append(f"Q{c.id} {' '.join(pads)} {c.model or 'npn_default'}")
            elif t == "DIODE":
                pads = (list(c.pins) + ["a", "k"])[:2]
                lines.append(f"D{c.id} {' '.join(pads)} {c.model or 'D'}")
            elif t == "VSRC":
                pads = (list(c.pins) + ["VDD", "0"])[:2]
                lines.append(f"V{c.id} {' '.join(pads)} DC {c.value or '0'}")
            else:
                # Subcircuit fallback for digital cells.
                lines.append(f"X{c.id} {pin_nets} {c.model or t.lower()}")
        # Default models so ngspice doesn't choke on a smoke run.
        lines.extend(
            [
                ".model nmos_default NMOS (LEVEL=1 VTO=0.5 KP=120u)",
                ".model pmos_default PMOS (LEVEL=1 VTO=-0.5 KP=40u)",
                ".model npn_default NPN (BF=100)",
                ".model D D",
                ".op",
            ]
        )
        if spec.ic_type in ("digital", "power"):
            lines.append(".tran 1n 100n")
        if spec.ic_type == "analog":
            lines.append(".ac dec 10 1 1G")
        lines.append(".end")
        return "\n".join(lines)

    def generate_offline(self, design: ICDesign) -> str:
        return self.header(design) + "\n" + self.fallback(design)
