"""Bill-of-materials generator. Pure stdlib (csv, json)."""

from __future__ import annotations

import csv
import io
import json
from collections import OrderedDict
from dataclasses import asdict, dataclass

from .design_engine import ICDesign


@dataclass
class BOMEntry:
    reference: str
    component_type: str
    value: str
    model: str
    description: str
    quantity: int

    def to_dict(self) -> dict:
        return asdict(self)


_DESCRIPTIONS = {
    "RES": "Resistor",
    "CAP": "Capacitor",
    "IND": "Inductor",
    "NMOS": "N-channel MOSFET",
    "PMOS": "P-channel MOSFET",
    "BJT": "Bipolar junction transistor",
    "OPAMP": "Operational amplifier",
    "DIODE": "Diode",
    "AND2": "2-input AND gate",
    "OR2": "2-input OR gate",
    "NAND2": "2-input NAND gate",
    "NOR2": "2-input NOR gate",
    "XOR2": "2-input XOR gate",
    "NOT": "Inverter",
    "DFF": "D flip-flop",
    "MUX2": "2:1 multiplexer",
    "VDD": "Supply rail",
    "GND": "Ground reference",
    "VSRC": "Voltage source",
}


class BOMGenerator:

    def generate(self, design: ICDesign) -> list[BOMEntry]:
        # Aggregate by (type, value, model)
        buckets: "OrderedDict[tuple[str,str,str], list[str]]" = OrderedDict()
        for c in design.components:
            key = (c.type.upper(), c.value or "", c.model or "")
            buckets.setdefault(key, []).append(c.id)
        entries: list[BOMEntry] = []
        for (ctype, value, model), refs in buckets.items():
            entries.append(BOMEntry(
                reference=", ".join(sorted(refs)),
                component_type=ctype,
                value=value,
                model=model,
                description=_DESCRIPTIONS.get(ctype, ctype.title()),
                quantity=len(refs),
            ))
        return entries

    @staticmethod
    def to_csv(entries: list[BOMEntry]) -> str:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["Reference", "Type", "Value", "Model", "Description", "Quantity"])
        for e in entries:
            writer.writerow([e.reference, e.component_type, e.value, e.model,
                             e.description, e.quantity])
        return buf.getvalue()

    @staticmethod
    def to_json(entries: list[BOMEntry]) -> str:
        return json.dumps([e.to_dict() for e in entries], indent=2)
