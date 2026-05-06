"""Offline component library — IEEE EDA catalogue.

Defines every component the user can drag from the toolbox or that the AI can
reference. Each entry carries a SPICE template, a Verilog behavioural
template, pin definitions, and a category for colouring.

The library is a singleton; plugins register additional components via
:meth:`ComponentLibrary.register`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------
CAT_PASSIVE = "PASSIVE"
CAT_DIODE = "DIODES"
CAT_TRANSISTOR = "TRANSISTORS"
CAT_ANALOG = "ANALOG"
CAT_POWER = "POWER"
CAT_GATE = "DIGITAL GATES"
CAT_SEQ = "SEQUENTIAL"
CAT_COMB = "COMBINATIONAL"
CAT_MEMORY = "MEMORY"
CAT_INTERFACE = "INTERFACE"
CAT_POWER_SYM = "POWER SYMBOLS"
CAT_IO = "CONNECTORS / IO"

CATEGORY_COLORS = {
    CAT_PASSIVE: "#a0c4ff",
    CAT_DIODE: "#ffadad",
    CAT_TRANSISTOR: "#ffd6a5",
    CAT_ANALOG: "#caffbf",
    CAT_POWER: "#fdffb6",
    CAT_GATE: "#c77dff",
    CAT_SEQ: "#9d4edd",
    CAT_COMB: "#7b2d8b",
    CAT_MEMORY: "#ff9e00",
    CAT_INTERFACE: "#48cae4",
    CAT_POWER_SYM: "#ff6b6b",
    CAT_IO: "#b7e4c7",
}

CATEGORY_ORDER = [
    CAT_PASSIVE,
    CAT_DIODE,
    CAT_TRANSISTOR,
    CAT_ANALOG,
    CAT_POWER,
    CAT_GATE,
    CAT_SEQ,
    CAT_COMB,
    CAT_MEMORY,
    CAT_INTERFACE,
    CAT_POWER_SYM,
    CAT_IO,
]


# ---------------------------------------------------------------------------
# Pin + component definitions
# ---------------------------------------------------------------------------
@dataclass
class PinDef:
    name: str
    direction: str = "inout"  # input | output | inout | power | ground
    side: str = "left"  # left | right | top | bottom — hint for symbol


@dataclass
class ComponentDef:
    id: str
    name: str
    category: str
    subcategory: str = ""
    symbol_type: str = ""
    pins: list[PinDef] = field(default_factory=list)
    default_params: dict = field(default_factory=dict)
    param_schema: dict = field(default_factory=dict)
    spice_template: str = ""
    verilog_template: str = ""
    color: str = "#cdd6f4"
    icon_path: str = ""
    description: str = ""

    def make_instance_params(self) -> dict:
        return dict(self.default_params)


# ---------------------------------------------------------------------------
# Default catalogue
# ---------------------------------------------------------------------------
def _p(name: str, direction: str = "inout", side: str = "left") -> PinDef:
    return PinDef(name=name, direction=direction, side=side)


def _build_default_catalogue() -> list[ComponentDef]:
    items: list[ComponentDef] = []

    # ---------- PASSIVE ------------------------------------------------
    items += [
        ComponentDef(
            id="R",
            name="Resistor",
            category=CAT_PASSIVE,
            symbol_type="RES",
            pins=[_p("1", side="left"), _p("2", side="right")],
            default_params={"value": "10k", "tolerance": "1%", "power": "0.25W"},
            param_schema={"value": "str", "tolerance": "str", "power": "str"},
            spice_template="R{ref} {n1} {n2} {value}",
            color=CATEGORY_COLORS[CAT_PASSIVE],
            description="Fixed-value resistor.",
        ),
        ComponentDef(
            id="C",
            name="Capacitor",
            category=CAT_PASSIVE,
            symbol_type="CAP",
            pins=[_p("1", side="top"), _p("2", side="bottom")],
            default_params={"value": "100n", "voltage": "16V", "type": "ceramic"},
            param_schema={
                "value": "str",
                "voltage": "str",
                "type": "enum:ceramic|electrolytic|film",
            },
            spice_template="C{ref} {n1} {n2} {value}",
            color=CATEGORY_COLORS[CAT_PASSIVE],
            description="Capacitor.",
        ),
        ComponentDef(
            id="L",
            name="Inductor",
            category=CAT_PASSIVE,
            symbol_type="IND",
            pins=[_p("1", side="left"), _p("2", side="right")],
            default_params={"value": "10u", "current": "1A"},
            param_schema={"value": "str", "current": "str"},
            spice_template="L{ref} {n1} {n2} {value}",
            color=CATEGORY_COLORS[CAT_PASSIVE],
        ),
        ComponentDef(
            id="XTAL",
            name="Crystal",
            category=CAT_PASSIVE,
            symbol_type="XTAL",
            pins=[_p("1", side="left"), _p("2", side="right")],
            default_params={"frequency": "16MHz", "load_cap": "18pF"},
            param_schema={"frequency": "str", "load_cap": "str"},
            spice_template="* X{ref} {n1} {n2} crystal {frequency}",
            color=CATEGORY_COLORS[CAT_PASSIVE],
        ),
    ]

    # ---------- DIODES -------------------------------------------------
    items += [
        ComponentDef(
            id="D",
            name="Diode",
            category=CAT_DIODE,
            symbol_type="DIODE",
            pins=[_p("A", side="left"), _p("K", side="right")],
            default_params={"model": "1N4148"},
            param_schema={"model": "str"},
            spice_template="D{ref} {nA} {nK} {model}",
            color=CATEGORY_COLORS[CAT_DIODE],
        ),
        ComponentDef(
            id="DZ",
            name="Zener Diode",
            category=CAT_DIODE,
            symbol_type="ZENER",
            pins=[_p("A", side="left"), _p("K", side="right")],
            default_params={"vz": "5.1V"},
            param_schema={"vz": "str"},
            spice_template="D{ref} {nA} {nK} DZENER",
            color=CATEGORY_COLORS[CAT_DIODE],
        ),
        ComponentDef(
            id="LED",
            name="LED",
            category=CAT_DIODE,
            symbol_type="LED",
            pins=[_p("A", side="left"), _p("K", side="right")],
            default_params={"color": "red", "vf": "2.0V"},
            param_schema={"color": "enum:red|green|blue|white|yellow", "vf": "str"},
            spice_template="D{ref} {nA} {nK} DLED",
            color=CATEGORY_COLORS[CAT_DIODE],
        ),
    ]

    # ---------- TRANSISTORS -------------------------------------------
    items += [
        ComponentDef(
            id="NMOS",
            name="NMOS",
            category=CAT_TRANSISTOR,
            symbol_type="NMOS",
            pins=[_p("D", side="top"), _p("G", side="left"), _p("S", side="bottom")],
            default_params={"W": "2u", "L": "180n", "model": "NMOS_180N"},
            param_schema={"W": "str", "L": "str", "model": "str"},
            spice_template="M{ref} {nD} {nG} {nS} {nS} {model} W={W} L={L}",
            color=CATEGORY_COLORS[CAT_TRANSISTOR],
        ),
        ComponentDef(
            id="PMOS",
            name="PMOS",
            category=CAT_TRANSISTOR,
            symbol_type="PMOS",
            pins=[_p("D", side="bottom"), _p("G", side="left"), _p("S", side="top")],
            default_params={"W": "4u", "L": "180n", "model": "PMOS_180N"},
            param_schema={"W": "str", "L": "str", "model": "str"},
            spice_template="M{ref} {nD} {nG} {nS} {nS} {model} W={W} L={L}",
            color=CATEGORY_COLORS[CAT_TRANSISTOR],
        ),
        ComponentDef(
            id="NPN",
            name="NPN BJT",
            category=CAT_TRANSISTOR,
            symbol_type="NPN",
            pins=[_p("C", side="top"), _p("B", side="left"), _p("E", side="bottom")],
            default_params={"model": "2N3904"},
            param_schema={"model": "str"},
            spice_template="Q{ref} {nC} {nB} {nE} {model}",
            color=CATEGORY_COLORS[CAT_TRANSISTOR],
        ),
        ComponentDef(
            id="PNP",
            name="PNP BJT",
            category=CAT_TRANSISTOR,
            symbol_type="PNP",
            pins=[_p("C", side="bottom"), _p("B", side="left"), _p("E", side="top")],
            default_params={"model": "2N3906"},
            param_schema={"model": "str"},
            spice_template="Q{ref} {nC} {nB} {nE} {model}",
            color=CATEGORY_COLORS[CAT_TRANSISTOR],
        ),
    ]

    # ---------- ANALOG -------------------------------------------------
    items += [
        ComponentDef(
            id="OPAMP",
            name="Op-Amp",
            category=CAT_ANALOG,
            symbol_type="OPAMP",
            pins=[
                _p("IN+", side="left"),
                _p("IN-", side="left"),
                _p("OUT", side="right"),
                _p("V+", side="top"),
                _p("V-", side="bottom"),
            ],
            default_params={"model": "LM741", "gbw": "1MHz"},
            param_schema={"model": "str", "gbw": "str"},
            spice_template="X{ref} {nIN+} {nIN-} {nV+} {nV-} {nOUT} {model}",
            color=CATEGORY_COLORS[CAT_ANALOG],
        ),
        ComponentDef(
            id="CMP",
            name="Comparator",
            category=CAT_ANALOG,
            symbol_type="OPAMP",
            pins=[_p("IN+", side="left"), _p("IN-", side="left"), _p("OUT", side="right")],
            default_params={"model": "LM393"},
            param_schema={"model": "str"},
            spice_template="X{ref} {nIN+} {nIN-} {nOUT} CMP",
            color=CATEGORY_COLORS[CAT_ANALOG],
        ),
        ComponentDef(
            id="VREF",
            name="Voltage Reference",
            category=CAT_ANALOG,
            symbol_type="VREF",
            pins=[_p("OUT", side="right"), _p("GND", direction="ground", side="bottom")],
            default_params={"vref": "1.25V"},
            param_schema={"vref": "str"},
            spice_template="V{ref} {nOUT} {nGND} {vref}",
            color=CATEGORY_COLORS[CAT_ANALOG],
        ),
    ]

    # ---------- POWER (regulators) ------------------------------------
    items += [
        ComponentDef(
            id="LDO",
            name="LDO Regulator",
            category=CAT_POWER,
            symbol_type="BLOCK",
            pins=[
                _p("VIN", side="left", direction="power"),
                _p("VOUT", side="right", direction="power"),
                _p("GND", side="bottom", direction="ground"),
                _p("EN", side="top", direction="input"),
            ],
            default_params={"vout": "3.3V", "iout": "500mA"},
            param_schema={"vout": "str", "iout": "str"},
            spice_template="* LDO {ref}: {nVIN} -> {nVOUT}",
            color=CATEGORY_COLORS[CAT_POWER],
        ),
        ComponentDef(
            id="BUCK",
            name="Buck Converter",
            category=CAT_POWER,
            symbol_type="BLOCK",
            pins=[
                _p("VIN", side="left", direction="power"),
                _p("VOUT", side="right", direction="power"),
                _p("GND", side="bottom", direction="ground"),
                _p("SW", side="top", direction="output"),
            ],
            default_params={"vout": "3.3V", "fsw": "1MHz"},
            param_schema={"vout": "str", "fsw": "str"},
            spice_template="* BUCK {ref}: {nVIN} -> {nVOUT}",
            color=CATEGORY_COLORS[CAT_POWER],
        ),
    ]

    # ---------- GATES --------------------------------------------------
    gate_specs = [
        ("AND2", "AND (2-in)", "AND", 2, "Y = A & B;"),
        ("AND3", "AND (3-in)", "AND", 3, "Y = A & B & C;"),
        ("OR2", "OR (2-in)", "OR", 2, "Y = A | B;"),
        ("NOT", "Inverter", "NOT", 1, "Y = ~A;"),
        ("NAND2", "NAND (2-in)", "NAND", 2, "Y = ~(A & B);"),
        ("NOR2", "NOR (2-in)", "NOR", 2, "Y = ~(A | B);"),
        ("XOR2", "XOR (2-in)", "XOR", 2, "Y = A ^ B;"),
        ("XNOR2", "XNOR (2-in)", "XNOR", 2, "Y = ~(A ^ B);"),
        ("BUF", "Buffer", "BUF", 1, "Y = A;"),
    ]
    for gid, name, sym, n_in, body in gate_specs:
        in_pins = ["A", "B", "C", "D"][:n_in]
        pins = [_p(p, "input", "left") for p in in_pins] + [_p("Y", "output", "right")]
        items.append(
            ComponentDef(
                id=gid,
                name=name,
                category=CAT_GATE,
                symbol_type=sym,
                pins=pins,
                color=CATEGORY_COLORS[CAT_GATE],
                verilog_template=f"// {gid}\nassign {{Y}} = {body};",
            )
        )

    # ---------- SEQUENTIAL --------------------------------------------
    items += [
        ComponentDef(
            id="DFF",
            name="D Flip-Flop",
            category=CAT_SEQ,
            symbol_type="DFF",
            pins=[
                _p("D", "input", "left"),
                _p("CLK", "input", "left"),
                _p("RST", "input", "left"),
                _p("Q", "output", "right"),
                _p("QN", "output", "right"),
            ],
            color=CATEGORY_COLORS[CAT_SEQ],
            verilog_template=(
                "always @(posedge CLK or posedge RST)\n" "    if (RST) Q <= 0; else Q <= D;"
            ),
        ),
        ComponentDef(
            id="JKFF",
            name="JK Flip-Flop",
            category=CAT_SEQ,
            symbol_type="DFF",
            pins=[
                _p("J", "input", "left"),
                _p("K", "input", "left"),
                _p("CLK", "input", "left"),
                _p("Q", "output", "right"),
                _p("QN", "output", "right"),
            ],
            color=CATEGORY_COLORS[CAT_SEQ],
        ),
        ComponentDef(
            id="TFF",
            name="T Flip-Flop",
            category=CAT_SEQ,
            symbol_type="DFF",
            pins=[
                _p("T", "input", "left"),
                _p("CLK", "input", "left"),
                _p("Q", "output", "right"),
            ],
            color=CATEGORY_COLORS[CAT_SEQ],
        ),
        ComponentDef(
            id="SR4",
            name="Shift Reg (4-bit)",
            category=CAT_SEQ,
            symbol_type="BLOCK",
            pins=[
                _p("DIN", "input", "left"),
                _p("CLK", "input", "left"),
                _p("Q0", "output", "right"),
                _p("Q1", "output", "right"),
                _p("Q2", "output", "right"),
                _p("Q3", "output", "right"),
            ],
            color=CATEGORY_COLORS[CAT_SEQ],
        ),
        ComponentDef(
            id="CNT4",
            name="Counter (4-bit)",
            category=CAT_SEQ,
            symbol_type="BLOCK",
            pins=[
                _p("CLK", "input", "left"),
                _p("RST", "input", "left"),
                _p("EN", "input", "left"),
                _p("Q0", "output", "right"),
                _p("Q1", "output", "right"),
                _p("Q2", "output", "right"),
                _p("Q3", "output", "right"),
            ],
            color=CATEGORY_COLORS[CAT_SEQ],
        ),
    ]

    # ---------- COMBINATIONAL ----------------------------------------
    items += [
        ComponentDef(
            id="MUX2",
            name="MUX 2:1",
            category=CAT_COMB,
            symbol_type="MUX",
            pins=[
                _p("I0", "input", "left"),
                _p("I1", "input", "left"),
                _p("S", "input", "bottom"),
                _p("Y", "output", "right"),
            ],
            color=CATEGORY_COLORS[CAT_COMB],
            verilog_template="assign Y = S ? I1 : I0;",
        ),
        ComponentDef(
            id="MUX4",
            name="MUX 4:1",
            category=CAT_COMB,
            symbol_type="MUX",
            pins=[
                _p("I0", "input", "left"),
                _p("I1", "input", "left"),
                _p("I2", "input", "left"),
                _p("I3", "input", "left"),
                _p("S0", "input", "bottom"),
                _p("S1", "input", "bottom"),
                _p("Y", "output", "right"),
            ],
            color=CATEGORY_COLORS[CAT_COMB],
        ),
        ComponentDef(
            id="DEC2_4",
            name="Decoder 2:4",
            category=CAT_COMB,
            symbol_type="BLOCK",
            pins=[
                _p("A0", "input", "left"),
                _p("A1", "input", "left"),
                _p("Y0", "output", "right"),
                _p("Y1", "output", "right"),
                _p("Y2", "output", "right"),
                _p("Y3", "output", "right"),
            ],
            color=CATEGORY_COLORS[CAT_COMB],
        ),
        ComponentDef(
            id="HADD",
            name="Half Adder",
            category=CAT_COMB,
            symbol_type="BLOCK",
            pins=[
                _p("A", "input", "left"),
                _p("B", "input", "left"),
                _p("S", "output", "right"),
                _p("C", "output", "right"),
            ],
            color=CATEGORY_COLORS[CAT_COMB],
        ),
        ComponentDef(
            id="FADD",
            name="Full Adder",
            category=CAT_COMB,
            symbol_type="BLOCK",
            pins=[
                _p("A", "input", "left"),
                _p("B", "input", "left"),
                _p("CIN", "input", "left"),
                _p("S", "output", "right"),
                _p("COUT", "output", "right"),
            ],
            color=CATEGORY_COLORS[CAT_COMB],
        ),
        ComponentDef(
            id="ALU4",
            name="4-bit ALU",
            category=CAT_COMB,
            symbol_type="BLOCK",
            pins=[
                _p("A", "input", "left"),
                _p("B", "input", "left"),
                _p("OP", "input", "bottom"),
                _p("Y", "output", "right"),
                _p("CO", "output", "right"),
            ],
            color=CATEGORY_COLORS[CAT_COMB],
        ),
    ]

    # ---------- MEMORY -----------------------------------------------
    items += [
        ComponentDef(
            id="SRAM6T",
            name="SRAM Cell (6T)",
            category=CAT_MEMORY,
            symbol_type="BLOCK",
            pins=[
                _p("WL", "input", "top"),
                _p("BL", "inout", "left"),
                _p("BLB", "inout", "right"),
            ],
            color=CATEGORY_COLORS[CAT_MEMORY],
        ),
        ComponentDef(
            id="ROM",
            name="ROM (LUT)",
            category=CAT_MEMORY,
            symbol_type="BLOCK",
            pins=[_p("ADDR", "input", "left"), _p("DATA", "output", "right")],
            color=CATEGORY_COLORS[CAT_MEMORY],
        ),
        ComponentDef(
            id="REGFILE",
            name="Register File 4x8",
            category=CAT_MEMORY,
            symbol_type="BLOCK",
            pins=[
                _p("RA", "input", "left"),
                _p("WA", "input", "left"),
                _p("WD", "input", "left"),
                _p("WE", "input", "left"),
                _p("RD", "output", "right"),
            ],
            color=CATEGORY_COLORS[CAT_MEMORY],
        ),
        ComponentDef(
            id="FIFO",
            name="FIFO 16x8",
            category=CAT_MEMORY,
            symbol_type="BLOCK",
            pins=[
                _p("WR", "input", "left"),
                _p("RD", "input", "left"),
                _p("DIN", "input", "left"),
                _p("DOUT", "output", "right"),
                _p("FULL", "output", "right"),
                _p("EMPTY", "output", "right"),
            ],
            color=CATEGORY_COLORS[CAT_MEMORY],
        ),
    ]

    # ---------- INTERFACE -------------------------------------------
    items += [
        ComponentDef(
            id="UART",
            name="UART TX/RX",
            category=CAT_INTERFACE,
            symbol_type="BLOCK",
            pins=[
                _p("CLK", "input", "left"),
                _p("TXD", "output", "right"),
                _p("RXD", "input", "left"),
                _p("BUSY", "output", "right"),
            ],
            color=CATEGORY_COLORS[CAT_INTERFACE],
        ),
        ComponentDef(
            id="SPI",
            name="SPI Master",
            category=CAT_INTERFACE,
            symbol_type="BLOCK",
            pins=[
                _p("SCLK", "output", "right"),
                _p("MOSI", "output", "right"),
                _p("MISO", "input", "left"),
                _p("CS", "output", "right"),
            ],
            color=CATEGORY_COLORS[CAT_INTERFACE],
        ),
        ComponentDef(
            id="I2C",
            name="I2C Master",
            category=CAT_INTERFACE,
            symbol_type="BLOCK",
            pins=[_p("SCL", "inout", "right"), _p("SDA", "inout", "right")],
            color=CATEGORY_COLORS[CAT_INTERFACE],
        ),
        ComponentDef(
            id="PWM",
            name="PWM Generator",
            category=CAT_INTERFACE,
            symbol_type="BLOCK",
            pins=[
                _p("CLK", "input", "left"),
                _p("DUTY", "input", "left"),
                _p("OUT", "output", "right"),
            ],
            color=CATEGORY_COLORS[CAT_INTERFACE],
        ),
    ]

    # ---------- POWER SYMBOLS ---------------------------------------
    items += [
        ComponentDef(
            id="VDD",
            name="VDD",
            category=CAT_POWER_SYM,
            symbol_type="VDD",
            pins=[_p("V", "power", "bottom")],
            default_params={"voltage": "3.3V"},
            param_schema={"voltage": "enum:1.2V|1.8V|2.5V|3.3V|5V|12V"},
            spice_template="V{ref} {nV} 0 {voltage}",
            color=CATEGORY_COLORS[CAT_POWER_SYM],
        ),
        ComponentDef(
            id="GND",
            name="GND",
            category=CAT_POWER_SYM,
            symbol_type="GND",
            pins=[_p("G", "ground", "top")],
            color=CATEGORY_COLORS[CAT_POWER_SYM],
        ),
        ComponentDef(
            id="AGND",
            name="Analog GND",
            category=CAT_POWER_SYM,
            symbol_type="GND",
            pins=[_p("G", "ground", "top")],
            color=CATEGORY_COLORS[CAT_POWER_SYM],
        ),
        ComponentDef(
            id="VREF_SYM",
            name="VREF",
            category=CAT_POWER_SYM,
            symbol_type="VDD",
            pins=[_p("V", "power", "bottom")],
            default_params={"vref": "1.25V"},
            param_schema={"vref": "str"},
            color=CATEGORY_COLORS[CAT_POWER_SYM],
        ),
        ComponentDef(
            id="NLABEL",
            name="Net Label",
            category=CAT_POWER_SYM,
            symbol_type="LABEL",
            pins=[_p("N", "inout", "left")],
            default_params={"name": "NET1"},
            param_schema={"name": "str"},
            color=CATEGORY_COLORS[CAT_POWER_SYM],
        ),
    ]

    # ---------- CONNECTORS / IO -------------------------------------
    items += [
        ComponentDef(
            id="PORT_IN",
            name="Input Port",
            category=CAT_IO,
            symbol_type="PORT_IN",
            pins=[_p("P", "input", "right")],
            default_params={"name": "IN"},
            param_schema={"name": "str"},
            color=CATEGORY_COLORS[CAT_IO],
        ),
        ComponentDef(
            id="PORT_OUT",
            name="Output Port",
            category=CAT_IO,
            symbol_type="PORT_OUT",
            pins=[_p("P", "output", "left")],
            default_params={"name": "OUT"},
            param_schema={"name": "str"},
            color=CATEGORY_COLORS[CAT_IO],
        ),
        ComponentDef(
            id="PORT_IO",
            name="Bidir Port",
            category=CAT_IO,
            symbol_type="PORT_IO",
            pins=[_p("P", "inout", "left")],
            default_params={"name": "IO"},
            param_schema={"name": "str"},
            color=CATEGORY_COLORS[CAT_IO],
        ),
        ComponentDef(
            id="BUS",
            name="Bus",
            category=CAT_IO,
            symbol_type="BUS",
            pins=[_p("B", "inout", "left")],
            default_params={"width": 8, "name": "BUS"},
            param_schema={"width": "int", "name": "str"},
            color=CATEGORY_COLORS[CAT_IO],
        ),
    ]

    return items


# ---------------------------------------------------------------------------
# Singleton library
# ---------------------------------------------------------------------------
class ComponentLibrary:
    _instance: "ComponentLibrary | None" = None

    def __init__(self) -> None:
        self._items: dict[str, ComponentDef] = {}
        for c in _build_default_catalogue():
            self._items[c.id] = c

    # -- access -----------------------------------------------------------
    @classmethod
    def instance(cls) -> "ComponentLibrary":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def all(self) -> list[ComponentDef]:
        return list(self._items.values())

    def by_category(self, category: str) -> list[ComponentDef]:
        return [c for c in self._items.values() if c.category == category]

    def by_id(self, comp_id: str) -> ComponentDef | None:
        return self._items.get(comp_id)

    def categories(self) -> list[str]:
        seen: list[str] = []
        for c in CATEGORY_ORDER:
            if any(x.category == c for x in self._items.values()) and c not in seen:
                seen.append(c)
        # Append any plugin-only category at the end.
        for x in self._items.values():
            if x.category not in seen:
                seen.append(x.category)
        return seen

    def search(self, query: str) -> list[ComponentDef]:
        q = (query or "").lower().strip()
        if not q:
            return self.all()
        return [
            c
            for c in self._items.values()
            if q in c.id.lower()
            or q in c.name.lower()
            or q in c.category.lower()
            or q in c.subcategory.lower()
        ]

    # -- mutation (used by plugins) --------------------------------------
    def register(self, comp: ComponentDef) -> None:
        if not comp.id:
            raise ValueError("ComponentDef.id required")
        self._items[comp.id] = comp

    def register_many(self, comps: Iterable[ComponentDef]) -> None:
        for c in comps:
            self.register(c)


__all__ = [
    "ComponentDef",
    "PinDef",
    "ComponentLibrary",
    "CATEGORY_COLORS",
    "CATEGORY_ORDER",
    "CAT_PASSIVE",
    "CAT_DIODE",
    "CAT_TRANSISTOR",
    "CAT_ANALOG",
    "CAT_POWER",
    "CAT_GATE",
    "CAT_SEQ",
    "CAT_COMB",
    "CAT_MEMORY",
    "CAT_INTERFACE",
    "CAT_POWER_SYM",
    "CAT_IO",
]
