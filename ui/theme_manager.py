"""Theme manager — runtime QSS swap, signals broadcast.

Singleton. Always go through this manager — never call
``QApplication.setStyleSheet`` directly.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication

log = logging.getLogger("autoic.theme")

THEME_DARK = "dark"
THEME_LIGHT = "light"
THEME_PCB = "pcb"
ALL_THEMES = (THEME_DARK, THEME_LIGHT, THEME_PCB)


# Net colors per theme — exposed so the schematic canvas can repaint.
THEME_NET_COLORS = {
    THEME_DARK: {
        "signal": "#00d4aa",
        "power": "#ff6b6b",
        "clock": "#ffd700",
        "ground": "#888888",
    },
    THEME_LIGHT: {
        "signal": "#007a5e",
        "power": "#cc0000",
        "clock": "#b8860b",
        "ground": "#555555",
    },
    # Real PCB colours — copper traces over green soldermask.
    THEME_PCB: {
        "signal": "#d4a017",   # gold-tinted copper
        "power": "#ff5252",    # red wire
        "clock": "#ffd54f",    # bright yellow
        "ground": "#c0c0c0",   # silver
    },
}

THEME_CANVAS_BG = {
    THEME_DARK: "#12121f",
    THEME_LIGHT: "#e8e8f0",
    THEME_PCB:  "#0e3d2b",   # FR4 dark green soldermask
}
THEME_GRID = {
    THEME_DARK: "#252535",
    THEME_LIGHT: "#cdd0dc",
    THEME_PCB:  "#155f3f",
}
THEME_GRID_MAJOR = {
    THEME_DARK: "#2f2f45",
    THEME_LIGHT: "#b6bccb",
    THEME_PCB:  "#1c7a52",
}
THEME_SYMBOL = {
    THEME_DARK: "#cdd6f4",
    THEME_LIGHT: "#1e1e2e",
    THEME_PCB:  "#f0e6c8",   # silkscreen white-cream
}
THEME_LABEL = {
    THEME_DARK: "#cdd6f4",
    THEME_LIGHT: "#1e1e2e",
    THEME_PCB:  "#f0e6c8",
}
THEME_PIN = {
    THEME_DARK: "#f9e2af",
    THEME_LIGHT: "#b58900",
    THEME_PCB:  "#ffd700",   # gold pad
}
THEME_SELECTED = {
    THEME_DARK: "#7c3aed",
    THEME_LIGHT: "#6d28d9",
    THEME_PCB:  "#ff8a00",   # orange highlight
}


class ThemeManager(QObject):
    """Singleton QSS loader."""

    theme_changed = pyqtSignal(str)
    _instance: "ThemeManager | None" = None

    def __init__(self, themes_dir: Path) -> None:
        super().__init__()
        self._themes_dir = Path(themes_dir)
        self._current: str = THEME_DARK
        self._qss: str = ""

    # -- singleton --------------------------------------------------------
    @classmethod
    def init(cls, themes_dir: Path) -> "ThemeManager":
        if cls._instance is None:
            cls._instance = cls(themes_dir)
        return cls._instance

    @classmethod
    def instance(cls) -> "ThemeManager":
        if cls._instance is None:
            raise RuntimeError("ThemeManager.init() not called")
        return cls._instance

    # -- public API -------------------------------------------------------
    @property
    def current(self) -> str:
        return self._current

    @property
    def qss(self) -> str:
        return self._qss

    def load(self, theme_name: str) -> bool:
        """Load and apply a theme. Returns True on success."""
        theme = (theme_name or "").lower()
        if theme not in ALL_THEMES:
            theme = THEME_DARK
        path = self._themes_dir / f"{theme}_theme.qss"
        if not path.exists():
            log.warning("Theme file missing: %s", path)
            self._qss = ""
        else:
            try:
                self._qss = path.read_text(encoding="utf-8")
            except OSError as e:
                log.error("Failed to read theme %s: %s", path, e)
                self._qss = ""
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(self._qss)
        self._current = theme
        self.theme_changed.emit(theme)
        log.info("Theme switched to %s", theme)
        return True

    def toggle(self) -> str:
        # Cycle: dark → light → pcb → dark
        cycle = {THEME_DARK: THEME_LIGHT, THEME_LIGHT: THEME_PCB, THEME_PCB: THEME_DARK}
        new = cycle.get(self._current, THEME_DARK)
        self.load(new)
        return new

    # -- color helpers (used by canvas) ----------------------------------
    def color(self, kind: str) -> str:
        table = {
            "canvas_bg": THEME_CANVAS_BG,
            "grid": THEME_GRID,
            "grid_major": THEME_GRID_MAJOR,
            "symbol": THEME_SYMBOL,
            "label": THEME_LABEL,
            "pin": THEME_PIN,
            "selected": THEME_SELECTED,
        }.get(kind, {})
        return table.get(self._current, "#ffffff")

    def net_color(self, net_type: str) -> str:
        return THEME_NET_COLORS[self._current].get(net_type,
                                                   THEME_NET_COLORS[self._current]["signal"])


__all__ = ["ThemeManager", "THEME_DARK", "THEME_LIGHT", "THEME_PCB", "ALL_THEMES"]
