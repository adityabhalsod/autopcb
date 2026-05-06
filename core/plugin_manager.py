"""AutoPCB plugin system.

A plugin is any Python module that exposes a top-level :func:`register`
function taking a :class:`PluginContext`. Plugins can:

* Add new draggable components to the toolbox
  (:meth:`PluginContext.register_component`)
* Register new AI providers
  (:meth:`PluginContext.register_ai_provider`)
* Add custom export formats
  (:meth:`PluginContext.register_exporter`)
* Add DRC rules
  (:meth:`PluginContext.register_drc_rule`)
* Inject menu / toolbar actions
  (:meth:`PluginContext.register_action`)

Plugins are discovered from two locations (created if missing):

* ``<repo>/plugins/``           — bundled examples
* ``~/.autopcb/plugins/``        — user plugins

Each ``.py`` file at the top level is loaded once at startup. Errors are
logged but never crash the app.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

log = logging.getLogger("autopcb.plugins")


# ---------------------------------------------------------------------------
# Plugin metadata
# ---------------------------------------------------------------------------
@dataclass
class PluginInfo:
    name: str
    version: str = "0.0.0"
    author: str = ""
    description: str = ""
    api_version: int = 1
    module_path: str = ""


@dataclass
class PluginAction:
    """A menu/toolbar action contributed by a plugin."""

    plugin: str
    title: str
    callback: Callable[[Any], None]  # receives MainWindow
    menu: str = "Plugins"
    icon: str = ""
    shortcut: str = ""
    tooltip: str = ""


@dataclass
class PluginExporter:
    """A custom exporter contributed by a plugin."""

    plugin: str
    name: str
    extensions: list[str]  # e.g. [".kicad_sch", ".gbr"]
    description: str
    callback: Callable[[Any, Path], None]  # (ICDesign, Path) -> writes file


@dataclass
class PluginDRCRule:
    """A custom DRC rule contributed by a plugin."""

    plugin: str
    rule_id: str
    description: str
    severity: str  # "PASS" | "WARN" | "FAIL"
    callback: Callable[[Any], list]  # (ICDesign) -> list[DRCViolation]


# ---------------------------------------------------------------------------
# Context — what plugins receive
# ---------------------------------------------------------------------------
class PluginContext:
    """The handle a plugin uses to register its contributions."""

    PLUGIN_API_VERSION = 1

    def __init__(self, manager: "PluginManager", info: PluginInfo) -> None:
        self._manager = manager
        self.info = info
        self.log = logging.getLogger(f"autopcb.plugin.{info.name}")

    # -- info -------------------------------------------------------------
    def declare(
        self,
        *,
        name: str,
        version: str = "0.0.0",
        author: str = "",
        description: str = "",
        api_version: int = PLUGIN_API_VERSION,
    ) -> None:
        """Idempotent metadata setter; called from the plugin's register()."""
        self.info.name = name or self.info.name
        self.info.version = version
        self.info.author = author
        self.info.description = description
        self.info.api_version = api_version

    # -- component library -----------------------------------------------
    def register_component(self, component: Any) -> None:
        from core.component_library import ComponentDef, ComponentLibrary

        if not isinstance(component, ComponentDef):
            raise TypeError("expected ComponentDef")
        ComponentLibrary.instance().register(component)
        self._manager._components.setdefault(self.info.name, []).append(component.id)
        self.log.info("Registered component %s", component.id)

    # -- AI providers ----------------------------------------------------
    def register_ai_provider(self, key: str, provider_cls: type) -> None:
        from core.ai_provider import AIProviderFactory

        AIProviderFactory.register(key, provider_cls)
        self._manager._providers.setdefault(self.info.name, []).append(key)
        self.log.info("Registered AI provider %s", key)

    # -- exporters --------------------------------------------------------
    def register_exporter(
        self,
        name: str,
        extensions: list[str],
        callback: Callable[[Any, Path], None],
        description: str = "",
    ) -> None:
        exp = PluginExporter(
            plugin=self.info.name,
            name=name,
            extensions=list(extensions),
            description=description,
            callback=callback,
        )
        self._manager._exporters.append(exp)
        self.log.info("Registered exporter %s", name)

    # -- DRC rules --------------------------------------------------------
    def register_drc_rule(
        self,
        rule_id: str,
        callback: Callable[[Any], list],
        severity: str = "WARN",
        description: str = "",
    ) -> None:
        rule = PluginDRCRule(
            plugin=self.info.name,
            rule_id=rule_id,
            description=description,
            severity=severity,
            callback=callback,
        )
        self._manager._drc_rules.append(rule)
        self.log.info("Registered DRC rule %s", rule_id)

    # -- menu/toolbar actions --------------------------------------------
    def register_action(
        self,
        title: str,
        callback: Callable[[Any], None],
        menu: str = "Plugins",
        icon: str = "",
        shortcut: str = "",
        tooltip: str = "",
    ) -> None:
        act = PluginAction(
            plugin=self.info.name,
            title=title,
            callback=callback,
            menu=menu,
            icon=icon,
            shortcut=shortcut,
            tooltip=tooltip,
        )
        self._manager._actions.append(act)
        self.log.info("Registered action %s", title)


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------
class PluginManager:
    """Discovers, loads, and tracks plugins."""

    def __init__(self, search_paths: Iterable[Path]) -> None:
        self.search_paths: list[Path] = [Path(p) for p in search_paths]
        self.plugins: list[PluginInfo] = []
        self._actions: list[PluginAction] = []
        self._exporters: list[PluginExporter] = []
        self._drc_rules: list[PluginDRCRule] = []
        self._components: dict[str, list[str]] = {}
        self._providers: dict[str, list[str]] = {}
        self._failed: list[tuple[str, str]] = []  # (path, error)

    # -- discovery --------------------------------------------------------
    def discover(self) -> None:
        for base in self.search_paths:
            if not base.exists():
                try:
                    base.mkdir(parents=True, exist_ok=True)
                except OSError:
                    continue
            for py in sorted(base.glob("*.py")):
                if py.name.startswith("_"):
                    continue
                self._load_one(py)
        log.info("Loaded %d plugin(s); %d failed", len(self.plugins), len(self._failed))

    def _load_one(self, path: Path) -> None:
        mod_name = f"autopcb_plugin_{path.stem}"
        try:
            spec = importlib.util.spec_from_file_location(mod_name, path)
            if spec is None or spec.loader is None:
                raise ImportError(f"could not create import spec for {path}")
            mod = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = mod
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            register = getattr(mod, "register", None)
            if not callable(register):
                raise AttributeError(f"{path.name}: missing top-level register(ctx) function")
            info = PluginInfo(name=path.stem, module_path=str(path))
            ctx = PluginContext(self, info)
            register(ctx)
            self.plugins.append(info)
            log.info("Plugin loaded: %s v%s by %s", info.name, info.version, info.author or "anon")
        except Exception as e:  # noqa: BLE001
            self._failed.append((str(path), str(e)))
            log.exception("Plugin failed to load: %s", path)

    # -- queries ----------------------------------------------------------
    @property
    def actions(self) -> list[PluginAction]:
        return list(self._actions)

    @property
    def exporters(self) -> list[PluginExporter]:
        return list(self._exporters)

    @property
    def drc_rules(self) -> list[PluginDRCRule]:
        return list(self._drc_rules)

    @property
    def failed(self) -> list[tuple[str, str]]:
        return list(self._failed)

    def summary(self) -> str:
        lines = [f"Plugins loaded: {len(self.plugins)}"]
        for p in self.plugins:
            lines.append(f"  • {p.name} v{p.version} — {p.description or '(no description)'}")
        if self._failed:
            lines.append(f"Failed: {len(self._failed)}")
            for path, err in self._failed:
                lines.append(f"  ✗ {Path(path).name}: {err}")
        return "\n".join(lines)


__all__ = [
    "PluginContext",
    "PluginManager",
    "PluginInfo",
    "PluginAction",
    "PluginExporter",
    "PluginDRCRule",
]
