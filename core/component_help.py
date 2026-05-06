"""Plain-English descriptions of every component & schematic concept.

These strings are shown as tooltips throughout the UI for users who are
NOT electronics designers. Keep them short (1–3 sentences), concrete, and
free of EE jargon. Each tooltip explains:

* What this part does in everyday language.
* A real-world analogy.
* When you would use it.

Lookup is by ``ComponentDef.symbol_type`` first, then ``ComponentDef.id``.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Per-symbol explanations
# ---------------------------------------------------------------------------
FRIENDLY_DESCRIPTIONS: dict[str, str] = {
    # ---- Passive components -------------------------------------------
    "RES": (
        "Resistor — slows down the flow of electricity.\n"
        "Like a narrow pipe in a water system, it limits current so other "
        "parts don't get damaged. Used almost everywhere on a board."
    ),
    "CAP": (
        "Capacitor — a tiny rechargeable battery that fills and empties "
        "very fast.\nSmooths out bumps in the power supply and helps "
        "circuits remember signals for a moment."
    ),
    "IND": (
        "Inductor — a coil of wire that resists sudden changes in current.\n"
        "Like a flywheel keeping a wheel spinning. Used to filter noise "
        "and to step voltage up or down in power supplies."
    ),
    "XTAL": (
        "Crystal — a precise, ticking 'metronome' for the chip.\n"
        "Vibrates at an exact frequency so the circuit knows when to do "
        "each step. Found in clocks, radios and microcontrollers."
    ),
    # ---- Discrete actives ---------------------------------------------
    "DIODE": (
        "Diode — a one-way valve for electricity.\n"
        "Lets current flow forward but blocks it from going backward. "
        "Protects circuits and turns AC into DC."
    ),
    "LED": (
        "LED — a tiny light that turns on when current flows through it.\n"
        "Used as indicators ('power on', 'error') and in display screens."
    ),
    "ZENER": (
        "Zener diode — a voltage 'pressure-release valve'.\n"
        "Holds the voltage at a fixed level, like a regulator on a gas "
        "tank. Used to make a stable reference voltage."
    ),
    "NMOS": (
        "N-MOSFET — an electronic switch controlled by voltage.\n"
        "Like a faucet you open with a small touch instead of force. "
        "The basic building block of every digital chip."
    ),
    "PMOS": (
        "P-MOSFET — the mirror image of an N-MOSFET.\n"
        "Switches OFF when the control voltage is high. Used together "
        "with N-MOSFETs to build logic gates that use almost no power."
    ),
    "BJT": (
        "Bipolar transistor — an old-style electronic amplifier/switch.\n"
        "A small input current controls a much larger output current. "
        "Used in audio amps and analog circuits."
    ),
    "OPAMP": (
        "Op-amp — a tiny precision amplifier.\n"
        "Takes a very small voltage difference and makes it bigger. "
        "Used in sensors, audio gear and analog filters."
    ),
    # ---- Power / supply ------------------------------------------------
    "VSRC": (
        "Voltage source — the 'battery' of the circuit.\n"
        "Provides a steady supply voltage (e.g. 5 V) that everything "
        "else runs from."
    ),
    "VDD": (
        "VDD rail — the positive power line of the chip.\n"
        "Think of it as the '+' terminal of a battery; every component "
        "that needs power connects here."
    ),
    "GND": (
        "Ground (GND) — the 'return path' or 0-volt reference.\n"
        "All voltages are measured against ground; every circuit must "
        "have one. Like the ground wire in your house wiring."
    ),
    # ---- Digital cells -------------------------------------------------
    "AND2": (
        "AND gate — outputs ON only when BOTH inputs are ON.\n"
        "Like a door that needs two keys turned at once."
    ),
    "OR2": (
        "OR gate — outputs ON if ANY input is ON.\n"
        "Like a doorbell that rings whether the front or back button is pressed."
    ),
    "NOT": (
        "NOT gate (inverter) — flips the signal.\n"
        "ON becomes OFF and OFF becomes ON. The simplest possible logic."
    ),
    "NAND2": (
        "NAND gate — opposite of AND.\n"
        "Outputs OFF only when both inputs are ON. The 'universal gate' "
        "from which every other gate can be built."
    ),
    "NOR2": ("NOR gate — opposite of OR.\n" "Outputs ON only when both inputs are OFF."),
    "XOR2": (
        "XOR gate — outputs ON when inputs DIFFER.\n"
        "Useful for adders, comparators and 'is the bit changed?' checks."
    ),
    "XNOR2": (
        "XNOR gate — outputs ON when inputs MATCH.\n"
        "The opposite of XOR; checks if two bits are equal."
    ),
    "DFF": (
        "Flip-flop (D-FF) — a 1-bit memory cell.\n"
        "Remembers its input value at each tick of the clock. "
        "Stack thousands together and you have a chip's RAM."
    ),
    "MUX2": (
        "Multiplexer — a controlled switch with 2 inputs and 1 output.\n"
        "Picks which input to forward, like a railway track switch."
    ),
    "BUF": (
        "Buffer — passes the signal through without changing it.\n"
        "Used to boost weak signals and to isolate parts of the circuit."
    ),
    # ---- Connectors / I/O ---------------------------------------------
    "PIN_IN": ("Input pin — where a signal enters this chip from the outside world."),
    "PIN_OUT": ("Output pin — where a signal leaves this chip to drive other circuits."),
    "PIN_IO": (
        "I/O pin — a pin that can be used for input OR output, depending "
        "on how the chip is configured."
    ),
    # ---- Sensors -------------------------------------------------------
    "ADC": (
        "ADC (analog-to-digital converter) — the chip's 'ears'.\n"
        "Measures a real-world voltage (sound, temperature, light) and "
        "turns it into numbers the digital part can read."
    ),
    "DAC": (
        "DAC (digital-to-analog converter) — the chip's 'voice'.\n"
        "Turns digital numbers back into a real voltage to drive speakers, "
        "displays or motors."
    ),
}


# Common aliases so we cover both ``id`` and ``symbol_type`` usage.
_ALIASES: dict[str, str] = {
    "R": "RES",
    "C": "CAP",
    "L": "IND",
    "Q_NPN": "BJT",
    "Q_PNP": "BJT",
    "M_NMOS": "NMOS",
    "M_PMOS": "PMOS",
    "D": "DIODE",
    "D_LED": "LED",
    "D_ZENER": "ZENER",
}


def friendly_text(comp_def) -> str:
    """Return a non-technical tooltip for a :class:`ComponentDef`."""
    keys = (
        getattr(comp_def, "symbol_type", "") or "",
        getattr(comp_def, "id", "") or "",
    )
    for key in keys:
        if not key:
            continue
        if key in FRIENDLY_DESCRIPTIONS:
            return FRIENDLY_DESCRIPTIONS[key]
        alias = _ALIASES.get(key)
        if alias and alias in FRIENDLY_DESCRIPTIONS:
            return FRIENDLY_DESCRIPTIONS[alias]
    # Fallback: combine the proper name and any existing description.
    name = getattr(comp_def, "name", "") or "Component"
    desc = getattr(comp_def, "description", "")
    if desc:
        return f"{name}\n{desc}"
    return f"{name} — drag this onto the canvas to add it to your circuit."


def tooltip_for(comp_def) -> str:
    """HTML-friendly tooltip with a heading and the plain-English text."""
    name = getattr(comp_def, "name", "") or "Component"
    text = friendly_text(comp_def).replace("\n", "<br>")
    pin_count = len(getattr(comp_def, "pins", []) or [])
    pin_line = (
        (f"<br><i>{pin_count} pin" f"{'s' if pin_count != 1 else ''}</i>") if pin_count else ""
    )
    return (
        f"<div style='max-width:320px'>"
        f"<b>{name}</b>{pin_line}<br>{text}"
        f"<br><br><small>Tip: drag onto the canvas, "
        f"then drag from a pin to connect.</small></div>"
    )


__all__ = ["FRIENDLY_DESCRIPTIONS", "friendly_text", "tooltip_for"]
