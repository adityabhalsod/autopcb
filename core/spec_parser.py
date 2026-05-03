"""IC spec parser — Claude JSON → typed dataclasses.

Pure stdlib + dataclasses; no Qt imports so this module is safe to use from
worker threads or unit tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Iterable

VALID_IC_TYPES = {"digital", "analog", "mixed", "power"}
VALID_PIN_TYPES = {"power", "signal", "clock", "ground"}
VALID_DIRECTIONS = {"input", "output", "inout"}


class SpecValidationError(ValueError):
    """Raised when a Claude-generated spec dict fails validation."""

    def __init__(self, message: str, *, field_path: str = "") -> None:
        self.field_path = field_path
        super().__init__(f"{field_path}: {message}" if field_path else message)


@dataclass
class PinDef:
    name: str
    direction: str
    voltage_level: str = ""
    pin_type: str = "signal"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict, *, path: str = "pin") -> "PinDef":
        if not isinstance(raw, dict):
            raise SpecValidationError("must be an object", field_path=path)
        name = str(raw.get("name", "")).strip()
        if not name:
            raise SpecValidationError("missing 'name'", field_path=path)
        direction = str(raw.get("direction", "input")).lower()
        if direction not in VALID_DIRECTIONS:
            direction = "input"
        pin_type = str(raw.get("pin_type", "signal")).lower()
        if pin_type not in VALID_PIN_TYPES:
            pin_type = "signal"
        return cls(
            name=name,
            direction=direction,
            voltage_level=str(raw.get("voltage_level", "")),
            pin_type=pin_type,
        )


@dataclass
class ICSpec:
    name: str
    ic_type: str
    technology_node: str = "180nm"
    supply_voltage: float = 3.3
    input_pins: list[PinDef] = field(default_factory=list)
    output_pins: list[PinDef] = field(default_factory=list)
    functional_description: str = ""
    performance_targets: dict[str, Any] = field(default_factory=dict)
    constraints: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "ic_type": self.ic_type,
            "technology_node": self.technology_node,
            "supply_voltage": self.supply_voltage,
            "input_pins": [p.to_dict() for p in self.input_pins],
            "output_pins": [p.to_dict() for p in self.output_pins],
            "functional_description": self.functional_description,
            "performance_targets": dict(self.performance_targets),
            "constraints": list(self.constraints),
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "ICSpec":
        return SpecParser().parse(raw)


class SpecParser:
    """Validate and convert raw Claude JSON into an :class:`ICSpec`."""

    REQUIRED = ("name", "ic_type")

    def parse(self, raw: Any) -> ICSpec:
        if not isinstance(raw, dict):
            raise SpecValidationError("spec must be a JSON object")

        for key in self.REQUIRED:
            if key not in raw or not raw[key]:
                raise SpecValidationError(f"missing required field '{key}'")

        ic_type = str(raw["ic_type"]).lower().strip()
        if ic_type not in VALID_IC_TYPES:
            raise SpecValidationError(
                f"ic_type must be one of {sorted(VALID_IC_TYPES)}, got '{ic_type}'",
                field_path="ic_type",
            )

        try:
            supply = float(raw.get("supply_voltage", 3.3))
        except (TypeError, ValueError) as e:
            raise SpecValidationError(f"supply_voltage must be numeric: {e}",
                                      field_path="supply_voltage") from e

        input_pins = self._parse_pins(raw.get("input_pins", []), "input", "input_pins")
        output_pins = self._parse_pins(raw.get("output_pins", []), "output", "output_pins")

        if not input_pins and not output_pins:
            # Provide minimal defaults so downstream stages never crash.
            input_pins = [PinDef(name="VDD", direction="input",
                                 voltage_level=f"{supply}V", pin_type="power"),
                          PinDef(name="GND", direction="input",
                                 voltage_level="0V", pin_type="ground")]

        perf = raw.get("performance_targets") or {}
        if not isinstance(perf, dict):
            perf = {}
        constraints = raw.get("constraints") or []
        if not isinstance(constraints, list):
            constraints = [str(constraints)]

        return ICSpec(
            name=str(raw["name"]).strip(),
            ic_type=ic_type,
            technology_node=str(raw.get("technology_node", "180nm")),
            supply_voltage=supply,
            input_pins=input_pins,
            output_pins=output_pins,
            functional_description=str(raw.get("functional_description", "")),
            performance_targets={str(k): v for k, v in perf.items()},
            constraints=[str(c) for c in constraints],
        )

    def _parse_pins(self, raw_pins: Any, default_direction: str,
                    field_path: str) -> list[PinDef]:
        if raw_pins is None:
            return []
        if not isinstance(raw_pins, Iterable) or isinstance(raw_pins, (str, bytes)):
            raise SpecValidationError("must be a list", field_path=field_path)
        pins: list[PinDef] = []
        for idx, p in enumerate(raw_pins):
            if isinstance(p, str):
                pins.append(PinDef(name=p, direction=default_direction))
                continue
            pin = PinDef.from_dict(p, path=f"{field_path}[{idx}]")
            if pin.direction not in VALID_DIRECTIONS:
                pin.direction = default_direction
            pins.append(pin)
        return pins

    # -- clarification helpers ------------------------------------------
    @staticmethod
    def to_clarification_questions(partial: ICSpec) -> list[str]:
        q: list[str] = []
        if not partial.name:
            q.append("What name should the IC have?")
        if partial.ic_type not in VALID_IC_TYPES:
            q.append("What is the IC type — digital, analog, mixed-signal, or power?")
        if not partial.functional_description:
            q.append("Describe the IC's functional behaviour in one sentence.")
        if partial.supply_voltage <= 0:
            q.append("What supply voltage (V) does the IC use?")
        if not partial.input_pins:
            q.append("List the input pins (name, direction, voltage level).")
        if not partial.output_pins:
            q.append("List the output pins (name, direction, voltage level).")
        return q
