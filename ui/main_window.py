"""AutoPCB main window — wires every panel and the AI pipeline."""

from __future__ import annotations

import json
import logging
import os
import zipfile
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QSize, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QStatusBar,
    QTabWidget,
    QToolBar,
    QWidget,
)

from core.ai_engine import AIEngine
from core.ai_log import install_log_bridge
from core.ai_provider import (
    DEFAULT_BASE_URLS,
    DEFAULT_MODELS,
    PROVIDER_ANTHROPIC,
    PROVIDER_LABELS,
    AIProviderConfig,
    AIProviderError,
    AIProviderFactory,
)
from core.bom_generator import BOMEntry, BOMGenerator
from core.component_library import ComponentLibrary
from core.design_engine import Component, DesignEngine, ICDesign
from core.drc_engine import SEV_FAIL, SEV_PASS, SEV_WARN, DRCEngine, DRCReport, DRCViolation
from core.netlist_generator import NetlistGenerator
from core.plugin_manager import PluginManager
from core.project_store import ProjectStore
from core.spec_parser import ICSpec, SpecParser
from core.verilog_generator import VerilogGenerator

from .component_toolbox import ComponentToolbox
from .output_panel import OutputPanel
from .project_dialog import ProjectDialog
from .property_panel import PropertyPanel
from .schematic_canvas import SchematicCanvas
from .settings_dialog import SettingsDialog
from .spec_panel import SpecPanel
from .theme_manager import ThemeManager
from .widgets.chat_widget import ROLE_ASSISTANT, ROLE_SYSTEM, ROLE_USER
from .widgets.mode_indicator import ModeIndicator
from .widgets.progress_widget import ProgressWidget


def _config_to_provider(cfg: dict) -> AIProviderConfig:
    """Build an :class:`AIProviderConfig` from a saved config dict.

    Falls back to the legacy ``api_key``/``model`` keys (Anthropic).
    """
    section = cfg.get("ai_provider") if isinstance(cfg.get("ai_provider"), dict) else None
    if section and section.get("active"):
        active = section["active"]
        s = section.get(active, {}) or {}
        return AIProviderConfig(
            provider=active,
            base_url=s.get("base_url", DEFAULT_BASE_URLS.get(active, "")),
            api_key=s.get("api_key", ""),
            model=s.get("model", DEFAULT_MODELS.get(active, "")),
        )
    return AIProviderConfig(
        provider=PROVIDER_ANTHROPIC,
        api_key=cfg.get("api_key", ""),
        model=cfg.get("model", DEFAULT_MODELS[PROVIDER_ANTHROPIC]),
    )


class _AIDetectWorker(QThread):
    """Background probe of provider availability for the status indicator."""

    detected = pyqtSignal(bool)  # online?

    def __init__(self, config: AIProviderConfig) -> None:
        super().__init__()
        self._config = config

    def run(self) -> None:
        try:
            provider = AIProviderFactory.create(self._config)
            self.detected.emit(bool(provider.health_check()))
        except Exception:  # noqa: BLE001
            self.detected.emit(False)


log = logging.getLogger("autopcb.window")


class MainWindow(QMainWindow):
    def __init__(
        self,
        *,
        config: dict,
        config_path: Path,
        db_path: Path,
        icons_dir: Path,
        plugin_dirs: Optional[list[Path]] = None,
        theme_manager: Optional[ThemeManager] = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("AutoPCB — AI-Powered IC Design")
        self.setMinimumSize(1440, 900)

        self._config = dict(config or {})
        self._config_path = Path(config_path)
        self._icons_dir = Path(icons_dir)
        self._db_path = Path(db_path)
        self._theme_manager = theme_manager

        # Plugins discovered up front so menus/components can include them.
        self._plugins = PluginManager(plugin_dirs or [])
        try:
            self._plugins.discover()
        except Exception as e:  # noqa: BLE001
            log.warning("Plugin discovery failed: %s", e)

        # Engines
        self._provider_config = _config_to_provider(self._config)
        self._ai = AIEngine(provider_config=self._provider_config)
        self._design_engine = DesignEngine(self._ai, self)
        # Mirror AI logger output into the AI Log tab.
        install_log_bridge()
        self._verilog_gen = VerilogGenerator()
        self._netlist_gen = NetlistGenerator()
        self._bom_gen = BOMGenerator()
        self._drc_engine = DRCEngine()
        # Register plugin DRC rules.
        for rule in self._plugins.drc_rules:
            try:
                self._drc_engine.register_rule(
                    rule.rule_id,
                    rule.callback,
                    severity=rule.severity,
                    description=rule.description,
                )
            except Exception as e:  # noqa: BLE001
                log.warning("Plugin DRC rule '%s' rejected: %s", rule.rule_id, e)
        self._store = ProjectStore(self._db_path)

        # State
        self._current_project_id: Optional[int] = None
        self._current_design: Optional[ICDesign] = None
        self._current_verilog: str = ""
        self._current_spice: str = ""
        self._current_bom: list[BOMEntry] = []
        self._current_drc: Optional[DRCReport] = None
        self._busy = False
        self._ai_online = False
        self._detect_worker: Optional[_AIDetectWorker] = None

        self._build_ui()
        self._build_actions_menus_toolbar()
        self._wire_signals()
        self._wire_theme()

        # Status
        plugin_msg = ""
        if self._plugins.plugins:
            plugin_msg = f"  ·  {len(self._plugins.plugins)} plugin(s) loaded"
        if (
            not self._provider_config.api_key
            and self._provider_config.provider == PROVIDER_ANTHROPIC
        ):
            self._status.showMessage(
                "No AI provider configured — open Settings or work in offline drag-drop mode."
                + plugin_msg
            )
        else:
            self._status.showMessage("Ready." + plugin_msg)

        # Probe AI availability in background so the indicator settles.
        self._refresh_ai_status()

    # -- UI construction -------------------------------------------------
    def _icon(self, name: str) -> QIcon:
        path = self._icons_dir / f"{name}.svg"
        return QIcon(str(path)) if path.exists() else QIcon()

    def _build_ui(self) -> None:
        # Central canvas
        self._canvas = SchematicCanvas()
        # EDIT mode is always available alongside AI rendering.
        self._canvas.set_edit_mode(True)
        self.setCentralWidget(self._canvas)

        # Make sure plugin-registered components are reflected in the toolbox.
        ComponentLibrary.instance()  # ensure singleton built before toolbox queries

        # Left dock — tabbed: Components (toolbox) + Specification (AI).
        self._spec_panel = SpecPanel()
        self._toolbox = ComponentToolbox()
        self._left_tabs = QTabWidget()
        self._left_tabs.addTab(self._toolbox, "Components")
        self._left_tabs.addTab(self._spec_panel, "AI Design")
        self._spec_dock = QDockWidget("Design")
        self._spec_dock.setObjectName("SpecDock")
        self._spec_dock.setWidget(self._left_tabs)
        self._spec_dock.setMinimumWidth(340)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._spec_dock)

        # Property dock
        self._property_panel = PropertyPanel()
        self._prop_dock = QDockWidget("Properties")
        self._prop_dock.setObjectName("PropDock")
        self._prop_dock.setWidget(self._property_panel)
        self._prop_dock.setMinimumWidth(280)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._prop_dock)

        # Output dock
        self._output_panel = OutputPanel()
        self._output_dock = QDockWidget("Outputs")
        self._output_dock.setObjectName("OutDock")
        self._output_dock.setWidget(self._output_panel)
        self._output_dock.setMinimumHeight(220)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._output_dock)

        # Status bar
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._mode_indicator = ModeIndicator()
        self._mode_indicator.set_status(
            online=False,
            provider=PROVIDER_LABELS.get(
                self._provider_config.provider, self._provider_config.provider
            ),
            model=self._provider_config.model,
            state="connecting",
        )
        self._status.addPermanentWidget(self._mode_indicator)
        self._progress = ProgressWidget()
        self._status.addPermanentWidget(self._progress)

    def _build_actions_menus_toolbar(self) -> None:
        # Actions
        self.act_new = QAction(self._icon("new"), "&New project", self)
        self.act_open = QAction(self._icon("open"), "&Open project", self)
        self.act_save = QAction(self._icon("save"), "&Save version", self)
        self.act_export = QAction(self._icon("export"), "Export &ZIP…", self)
        self.act_quit = QAction("&Quit", self)
        self.act_settings = QAction(self._icon("settings"), "&Settings", self)
        self.act_generate = QAction(self._icon("generate"), "&Generate IC", self)
        self.act_drc = QAction(self._icon("drc"), "Run &DRC", self)
        self.act_autofix = QAction(self._icon("autofix"), "&Auto-fix DRC", self)
        self.act_stop_ai = QAction(self._icon("stop"), "&Stop AI", self)
        self.act_stop_ai.setToolTip("Forcefully cancel any running AI request (Esc)")
        self.act_stop_ai.setShortcut("Esc")
        self.act_stop_ai.setEnabled(False)
        self.act_export_svg = QAction("Export S&VG…", self)
        self.act_export_png = QAction("Export PN&G…", self)
        self.act_toggle_theme = QAction(self._icon("palette"), "Toggle &Theme", self)
        self.act_toggle_theme.setShortcut("Ctrl+T")
        self.act_toggle_theme.triggered.connect(self._toggle_theme)
        self.act_about = QAction("&About AutoPCB", self)
        self.act_toggle_spec = self._spec_dock.toggleViewAction()
        self.act_toggle_prop = self._prop_dock.toggleViewAction()
        self.act_toggle_out = self._output_dock.toggleViewAction()
        self.act_toggle_spec.setText("Show &Specification panel")
        self.act_toggle_prop.setText("Show &Properties panel")
        self.act_toggle_out.setText("Show &Outputs panel")

        for act in (
            self.act_generate,
            self.act_save,
            self.act_drc,
            self.act_autofix,
            self.act_export,
        ):
            act.setEnabled(False)

        self.act_quit.triggered.connect(self.close)
        self.act_new.triggered.connect(self._open_project_dialog)
        self.act_open.triggered.connect(self._open_project_dialog)
        self.act_save.triggered.connect(self._save_current_version)
        self.act_export.triggered.connect(self._export_zip)
        self.act_settings.triggered.connect(self._open_settings)
        self.act_generate.triggered.connect(self._on_generate_pipeline)
        self.act_drc.triggered.connect(self._run_drc)
        self.act_autofix.triggered.connect(self._auto_fix)
        self.act_stop_ai.triggered.connect(self._stop_ai)
        self.act_export_svg.triggered.connect(self._export_svg)
        self.act_export_png.triggered.connect(self._export_png)
        self.act_about.triggered.connect(self._show_about)

        # Menus
        mb = self.menuBar()
        m_file = mb.addMenu("&File")
        m_file.addAction(self.act_new)
        m_file.addAction(self.act_open)
        m_file.addAction(self.act_save)
        m_file.addSeparator()
        m_file.addAction(self.act_export)
        m_file.addAction(self.act_export_svg)
        m_file.addAction(self.act_export_png)
        m_file.addSeparator()
        m_file.addAction(self.act_quit)

        m_edit = mb.addMenu("&Edit")
        m_edit.addAction(self.act_settings)

        m_view = mb.addMenu("&View")
        m_view.addAction(self.act_toggle_spec)
        m_view.addAction(self.act_toggle_prop)
        m_view.addAction(self.act_toggle_out)

        m_run = mb.addMenu("&Run")
        m_run.addAction(self.act_generate)
        m_run.addAction(self.act_drc)
        m_run.addAction(self.act_autofix)
        m_run.addSeparator()
        m_run.addAction(self.act_stop_ai)

        # Plugins menu — populated from PluginManager actions.
        plugin_actions = self._plugins.actions
        if plugin_actions:
            m_plugins = mb.addMenu("&Plugins")
            for pa in plugin_actions:
                a = QAction(pa.title, self)
                if pa.shortcut:
                    a.setShortcut(pa.shortcut)
                if pa.tooltip:
                    a.setToolTip(pa.tooltip)
                a.triggered.connect(
                    lambda _checked=False, cb=pa.callback: self._invoke_plugin_action(cb)
                )
                m_plugins.addAction(a)

        # Plugin exporters appended under File menu.
        plugin_exporters = self._plugins.exporters
        if plugin_exporters:
            m_file.addSeparator()
            for exporter in plugin_exporters:
                a = QAction(f"Export — {exporter.name}…", self)
                a.triggered.connect(
                    lambda _checked=False, e=exporter: self._run_plugin_exporter(e)
                )
                m_file.addAction(a)

        m_help = mb.addMenu("&Help")
        m_help.addAction(self.act_about)

        # Toolbar
        tb = QToolBar("Main")
        tb.setObjectName("MainToolBar")
        tb.setIconSize(QSize(20, 20))
        tb.setMovable(False)
        self.addToolBar(tb)
        for act in (self.act_new, self.act_open, self.act_save):
            tb.addAction(act)
        tb.addSeparator()
        for act in (self.act_generate, self.act_drc, self.act_autofix):
            tb.addAction(act)
        tb.addAction(self.act_stop_ai)
        tb.addSeparator()
        for act in (self.act_export_svg, self.act_export):
            tb.addAction(act)
        tb.addSeparator()
        tb.addAction(self.act_toggle_theme)
        tb.addAction(self.act_settings)

    def _wire_signals(self) -> None:
        self._spec_panel.spec_ready.connect(self._on_spec_submit)
        self._spec_panel.chat_message.connect(self._on_chat_message)
        self._canvas.component_selected.connect(self._on_component_selected)
        self._canvas.design_changed.connect(self._on_canvas_edited)
        self._design_engine.progress.connect(self._progress.update_text)
        self._design_engine.error.connect(self._on_pipeline_error)
        self._output_panel.autofix_requested.connect(self._auto_fix)
        # Toolbox double-click drops a centered component as a convenience.
        self._toolbox.component_activated.connect(self._on_toolbox_activated)

    def _wire_theme(self) -> None:
        if self._theme_manager is None:
            return
        self._theme_manager.theme_changed.connect(self._on_theme_changed)
        # Repaint canvas so grid / background colours update immediately.
        self._theme_manager.theme_changed.connect(lambda _name: self._canvas.viewport().update())

    # -- Theme -----------------------------------------------------------
    def _toggle_theme(self) -> None:
        if self._theme_manager is None:
            return
        self._theme_manager.toggle()
        self._config["theme"] = self._theme_manager.current
        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            self._config_path.write_text(json.dumps(self._config, indent=2))
        except Exception as e:  # noqa: BLE001
            log.warning("Could not persist theme: %s", e)

    def _on_theme_changed(self, name: str) -> None:
        self._status.showMessage(f"Theme switched to {name}.", 3000)
        # Propagate to code editors inside the output panel so their
        # hardcoded inline stylesheet is refreshed to the current theme.
        from .widgets.code_editor import CodeEditor

        for editor in self._output_panel.findChildren(CodeEditor):
            editor.apply_theme(name)

    # -- helpers ---------------------------------------------------------
    def _set_busy(self, busy: bool, label: str = "Working…") -> None:
        self._busy = busy
        for act in (
            self.act_generate,
            self.act_drc,
            self.act_autofix,
            self.act_save,
            self.act_export,
        ):
            if act is self.act_generate:
                act.setEnabled(not busy and self._ai_online)
            else:
                act.setEnabled(not busy and self._current_design is not None)
        self._spec_panel.set_busy(busy)
        # Stop button is the inverse of Generate — only enabled while busy.
        self.act_stop_ai.setEnabled(busy)
        # Generate is enabled when the configured provider is usable.
        # For local providers (Ollama/LM Studio) no api_key is required, so
        # gate on the most recent health probe rather than on a key string.
        if not busy:
            self.act_generate.setEnabled(self._ai_online)
        if busy:
            self._progress.start(label)
        else:
            self._progress.stop("Ready.")

    def _check_api_key(self) -> bool:
        if self._ai.is_ready():
            return True
        QMessageBox.warning(
            self,
            "AutoPCB",
            "AI provider is not configured. Open Settings to choose a provider,"
            " or use the Components panel to build a schematic offline.",
        )
        return False

    # -- AI status indicator --------------------------------------------
    def _refresh_ai_status(self) -> None:
        """Probe the configured provider in the background."""
        provider_label = PROVIDER_LABELS.get(
            self._provider_config.provider, self._provider_config.provider
        )
        self._mode_indicator.set_status(
            online=False,
            provider=provider_label,
            model=self._provider_config.model,
            state="connecting",
        )
        if not self._ai.is_ready():
            self._mode_indicator.set_status(
                online=False,
                provider=provider_label,
                model=self._provider_config.model,
                state="offline",
            )
            self._ai_online = False
            return
        worker = _AIDetectWorker(self._provider_config)
        worker.detected.connect(self._on_ai_status)
        worker.finished.connect(lambda: setattr(self, "_detect_worker", None))
        self._detect_worker = worker
        worker.start()

    def _on_ai_status(self, online: bool) -> None:
        self._ai_online = bool(online)
        provider_label = PROVIDER_LABELS.get(
            self._provider_config.provider, self._provider_config.provider
        )
        self._mode_indicator.set_status(
            online=online,
            provider=provider_label,
            model=self._provider_config.model,
            state="online" if online else "offline",
        )

    # -- Canvas / toolbox --------------------------------------------------
    def _on_canvas_edited(self) -> None:
        design = self._canvas.get_current_design()
        if design is not None:
            self._current_design = design
            self._property_panel.set_design(design)
            for act in (self.act_save, self.act_drc, self.act_export):
                act.setEnabled(True)

    def _on_toolbox_activated(self, comp_id: str) -> None:
        """Drop the activated component near the centre of the visible area."""
        from PyQt6.QtCore import QPoint

        view_centre = self._canvas.viewport().rect().center()
        scene_pos = self._canvas.mapToScene(QPoint(view_centre.x(), view_centre.y()))
        self._canvas.add_component_at(comp_id, scene_pos)

    # -- pipeline --------------------------------------------------------
    def _on_spec_submit(self, name: str, ic_type: str, description: str) -> None:
        if not self._check_api_key():
            return
        self._on_generate_pipeline(name=name, ic_type=ic_type, description=description)

    def _on_generate_pipeline(
        self,
        *,
        name: str | None = None,
        ic_type: str | None = None,
        description: str | None = None,
    ) -> None:
        if not self._check_api_key():
            return
        if name is None:
            name, ic_type, description = self._spec_panel.current_values()
        if not name or not description:
            QMessageBox.information(
                self, "AutoPCB", "Please enter an IC name and description first."
            )
            return

        # Ensure project exists
        if self._current_project_id is None:
            self._current_project_id = self._store.create_project(name, ic_type or "digital")

        self._set_busy(True, "Generating IC spec…")
        nl = f"IC name: {name}\n" f"IC type: {ic_type}\n" f"Description: {description}\n"
        spec_worker = self._ai.generate_ic_spec(nl)
        spec_worker.progress.connect(self._progress.update_text)
        spec_worker.error.connect(self._on_pipeline_error)
        spec_worker.response_ready.connect(self._after_spec)

    def _after_spec(self, payload: object) -> None:
        try:
            if not isinstance(payload, dict):
                raise ValueError("Spec payload was not a JSON object")
            # Inject user-typed name/type if Claude omitted them.
            name, ic_type, desc = self._spec_panel.current_values()
            payload.setdefault("name", name)
            payload.setdefault("ic_type", ic_type or "digital")
            payload.setdefault("functional_description", desc)
            spec = SpecParser().parse(payload)
        except Exception as e:  # noqa: BLE001
            self._on_pipeline_error(f"Spec parse failed: {e}")
            return
        self._progress.update_text("Designing topology…")
        self._design_engine.design(spec, self._after_design, self._on_pipeline_error)

    def _after_design(self, design: ICDesign) -> None:
        self._current_design = design
        self._canvas.render_design(design)
        self._property_panel.set_design(design)
        self._property_panel.clear()
        self._spec_panel.chat().add_message(
            ROLE_SYSTEM,
            f"Design ready — {len(design.components)} components, {len(design.nets)} nets.",
        )

        self._progress.update_text("Generating Verilog…")
        v_worker = self._ai.generate_verilog(design.to_dict())
        v_worker.progress.connect(self._progress.update_text)
        v_worker.error.connect(self._on_pipeline_error)
        v_worker.response_ready.connect(self._after_verilog)

    def _after_verilog(self, raw: object) -> None:
        if not isinstance(raw, str):
            raw = ""
        try:
            self._current_verilog = self._verilog_gen.finalize(self._current_design, raw)
        except Exception as e:  # noqa: BLE001
            log.warning("Verilog finalize failed (%s) — using offline generator", e)
            self._current_verilog = self._verilog_gen.generate_offline(self._current_design)
        self._output_panel.load_verilog(self._current_verilog)

        self._progress.update_text("Generating SPICE netlist…")
        s_worker = self._ai.generate_spice(self._current_design.to_dict())
        s_worker.progress.connect(self._progress.update_text)
        s_worker.error.connect(self._on_pipeline_error)
        s_worker.response_ready.connect(self._after_spice)

    def _after_spice(self, raw: object) -> None:
        if not isinstance(raw, str):
            raw = ""
        try:
            self._current_spice = self._netlist_gen.finalize(self._current_design, raw)
        except Exception as e:  # noqa: BLE001
            log.warning("SPICE finalize failed (%s) — using offline generator", e)
            self._current_spice = self._netlist_gen.generate_offline(self._current_design)
        self._output_panel.load_spice(self._current_spice)

        self._progress.update_text("Building BOM…")
        self._current_bom = self._bom_gen.generate(self._current_design)
        self._output_panel.load_bom(self._current_bom)

        # Run DRC (deterministic + AI)
        self._progress.update_text("Running deterministic DRC…")
        det = self._drc_engine.run_deterministic(self._current_design)
        ai_worker = self._ai.run_drc(self._current_design.to_dict(), self._current_spice)
        ai_worker.progress.connect(self._progress.update_text)

        def _fold_ai(ai_payload: object) -> None:
            ai_report = DRCReport()
            if isinstance(ai_payload, dict):
                ai_report = DRCEngine.from_ai(ai_payload)
            merged = DRCEngine.merge(det, ai_report)
            self._after_drc(merged)

        ai_worker.error.connect(lambda _m: self._after_drc(det))
        ai_worker.response_ready.connect(_fold_ai)

    def _after_drc(self, report: DRCReport) -> None:
        self._current_drc = report
        self._output_panel.load_drc(report)
        self._save_current_version()
        self._set_busy(False)
        self._status.showMessage(
            f"Generation complete — {report.summary}",
            7000,
        )
        self._spec_panel.chat().add_message(
            ROLE_ASSISTANT,
            f"Pipeline finished. {report.summary}. Click components to inspect.",
        )

    # -- DRC re-run / autofix -------------------------------------------
    def _run_drc(self) -> None:
        if not self._current_design:
            return
        if not self._check_api_key():
            return
        self._set_busy(True, "Running DRC…")
        det = self._drc_engine.run_deterministic(self._current_design)
        worker = self._ai.run_drc(self._current_design.to_dict(), self._current_spice)
        worker.progress.connect(self._progress.update_text)

        def _done(payload: object) -> None:
            ai_report = DRCEngine.from_ai(payload) if isinstance(payload, dict) else DRCReport()
            merged = DRCEngine.merge(det, ai_report)
            self._current_drc = merged
            self._output_panel.load_drc(merged)
            self._output_panel.show_drc()
            self._set_busy(False)

        worker.response_ready.connect(_done)
        worker.error.connect(lambda m: (self._on_pipeline_error(m), self._set_busy(False)))

    def _auto_fix(self) -> None:
        if not self._current_design or not self._current_drc:
            return
        if not self._check_api_key():
            return
        self._set_busy(True, "AI auto-fixing DRC violations…")
        worker = self._ai.auto_fix(
            self._current_design.to_dict(),
            [v.to_dict() for v in self._current_drc.violations],
        )
        worker.progress.connect(self._progress.update_text)

        def _done(payload: object) -> None:
            try:
                if not isinstance(payload, dict):
                    raise ValueError("autofix payload not a dict")
                fixed = ICDesign.from_dict(payload)
                # Preserve the original ICSpec if fixed lost it.
                if fixed.spec is None or not fixed.spec.name:
                    fixed.spec = self._current_design.spec
                from core.design_engine import auto_place

                auto_place(fixed.components)
                self._current_design = fixed
                self._canvas.render_design(fixed)
                self._property_panel.set_design(fixed)
                # Regenerate downstream artifacts deterministically.
                self._current_verilog = self._verilog_gen.generate_offline(fixed)
                self._current_spice = self._netlist_gen.generate_offline(fixed)
                self._current_bom = self._bom_gen.generate(fixed)
                self._output_panel.load_verilog(self._current_verilog)
                self._output_panel.load_spice(self._current_spice)
                self._output_panel.load_bom(self._current_bom)
                self._current_drc = self._drc_engine.run_deterministic(fixed)
                self._output_panel.load_drc(self._current_drc)
                self._save_current_version()
                self._status.showMessage("Auto-fix applied — new version saved.", 6000)
            except Exception as e:  # noqa: BLE001
                self._on_pipeline_error(f"Auto-fix failed: {e}")
            finally:
                self._set_busy(False)

        worker.response_ready.connect(_done)
        worker.error.connect(lambda m: (self._on_pipeline_error(m), self._set_busy(False)))

    # -- chat ------------------------------------------------------------
    def _on_chat_message(self, text: str) -> None:
        if not self._check_api_key():
            return
        if self._current_project_id is not None:
            self._store.append_chat(self._current_project_id, "user", text)
        bubble = self._spec_panel.chat().add_message(ROLE_ASSISTANT, "…")
        worker = self._ai.chat_modify(
            self._current_design.to_dict() if self._current_design else None,
            text,
        )
        worker.progress.connect(self._progress.update_text)

        def _done(payload: object) -> None:
            msg = ""
            patch = None
            if isinstance(payload, dict):
                msg = str(payload.get("message", ""))
                patch = payload.get("design_patch")
            if not msg:
                msg = "(no message)"
            self._spec_panel.chat().stream_into(bubble, msg)
            if self._current_project_id is not None:
                self._store.append_chat(self._current_project_id, "assistant", msg)
            if isinstance(patch, dict):
                try:
                    fixed = ICDesign.from_dict(patch)
                    if not fixed.spec.name and self._current_design:
                        fixed.spec = self._current_design.spec
                    from core.design_engine import auto_place

                    auto_place(fixed.components)
                    self._current_design = fixed
                    self._canvas.render_design(fixed)
                    self._property_panel.set_design(fixed)
                except Exception as e:  # noqa: BLE001
                    log.warning("chat patch failed: %s", e)

        worker.response_ready.connect(_done)
        worker.error.connect(lambda m: bubble.setText(f"Error: {m}"))

    # -- selection -------------------------------------------------------
    def _on_component_selected(self, component: Optional[Component]) -> None:
        if component is None:
            self._property_panel.clear()
            return
        self._property_panel.update_component(component, component.rationale)

    # -- error handling --------------------------------------------------
    def _on_pipeline_error(self, message: str) -> None:
        log.error("Pipeline error: %s", message)
        self._status.showMessage(f"Error: {message}", 9000)
        self._spec_panel.chat().add_message(ROLE_SYSTEM, f"❌ {message}")
        self._set_busy(False)

    # -- AI cancellation -------------------------------------------------
    def _stop_ai(self) -> None:
        """Forcefully cancel any in-flight AI request."""
        if not self._busy:
            return
        n = self._ai.cancel_all()
        log.info("Stop AI: cancelled %d worker(s)", n)
        self._status.showMessage(f"AI request cancelled by user ({n} worker(s) stopped).", 5000)
        self._spec_panel.chat().add_message(ROLE_SYSTEM, "⏹ AI request cancelled by user.")
        self._set_busy(False)

    # -- persistence -----------------------------------------------------
    def _save_current_version(self) -> None:
        if not self._current_design:
            return
        if self._current_project_id is None:
            self._current_project_id = self._store.create_project(
                self._current_design.spec.name or "untitled",
                self._current_design.spec.ic_type or "digital",
            )
        self._store.save_version(
            self._current_project_id,
            self._current_design,
            verilog=self._current_verilog,
            spice=self._current_spice,
            bom=[e.to_dict() for e in self._current_bom],
            drc=self._current_drc.to_dict() if self._current_drc else None,
        )

    # -- dialogs ---------------------------------------------------------
    def _open_settings(self) -> None:
        dlg = SettingsDialog(
            self._config, self._config_path, theme_manager=self._theme_manager, parent=self
        )
        if dlg.exec():
            self._config = dlg.result_config()
            self._provider_config = dlg.active_provider_config()
            try:
                self._ai.set_provider(self._provider_config)
            except AIProviderError as e:
                QMessageBox.warning(self, "AutoPCB", f"Provider could not be initialised: {e}")
            self.act_generate.setEnabled(self._ai.is_ready())
            self._refresh_ai_status()
            if self._ai.is_ready():
                self._status.showMessage(
                    f"AI provider: {PROVIDER_LABELS.get(self._provider_config.provider)}.", 5000
                )

    def _open_project_dialog(self) -> None:
        dlg = ProjectDialog(self._store, self)
        dlg.project_created.connect(self._on_project_created)
        dlg.project_opened.connect(self._on_project_opened)
        dlg._versions.load_requested.connect(self._on_version_load)
        dlg.exec()

    def _on_project_created(self, pid: int, name: str, ic_type: str, desc: str) -> None:
        self._current_project_id = pid
        self._spec_panel.set_values(name, ic_type, desc)
        self._status.showMessage(f"Project '{name}' created.", 5000)

    def _on_project_opened(self, pid: int) -> None:
        self._current_project_id = pid
        loaded = self._store.load_latest(pid)
        if loaded:
            self._apply_loaded(loaded)
            self._status.showMessage(
                f"Loaded latest version of project #{pid}.",
                5000,
            )

    def _on_version_load(self, version_id: int) -> None:
        loaded = self._store.load_version(version_id)
        if loaded:
            self._apply_loaded(loaded)
            self._status.showMessage(f"Loaded version #{version_id}.", 5000)

    def _apply_loaded(self, payload: dict) -> None:
        design: ICDesign = payload["design"]
        from core.design_engine import auto_place

        auto_place(design.components)
        self._current_design = design
        self._current_verilog = payload.get("verilog", "") or ""
        self._current_spice = payload.get("spice", "") or ""
        self._current_bom = [BOMEntry(**e) for e in payload.get("bom", []) if isinstance(e, dict)]
        drc_raw = payload.get("drc") or {}
        self._current_drc = DRCReport.from_dict(drc_raw) if drc_raw else None

        self._spec_panel.set_values(
            design.spec.name, design.spec.ic_type, design.spec.functional_description
        )
        self._canvas.render_design(design)
        self._property_panel.set_design(design)
        self._output_panel.load_verilog(self._current_verilog)
        self._output_panel.load_spice(self._current_spice)
        self._output_panel.load_bom(self._current_bom)
        if self._current_drc:
            self._output_panel.load_drc(self._current_drc)
        for act in (self.act_save, self.act_drc, self.act_autofix, self.act_export):
            act.setEnabled(True)

    # -- exports ---------------------------------------------------------
    def _default_export_dir(self) -> str:
        return self._config.get("output_dir") or os.getcwd()

    def _export_zip(self) -> None:
        if not self._current_design:
            return
        default = str(
            Path(self._default_export_dir()) / f"{self._current_design.spec.name or 'design'}.zip"
        )
        path, _ = QFileDialog.getSaveFileName(self, "Export ZIP", default, "ZIP archive (*.zip)")
        if not path:
            return
        # Prepare schematic SVG (in-memory: write to temp and add).
        tmp_dir = Path(self._default_export_dir())
        tmp_dir.mkdir(parents=True, exist_ok=True)
        svg_path = tmp_dir / f"{self._current_design.spec.name or 'design'}.svg"
        self._canvas.export_svg(str(svg_path))
        try:
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("design.v", self._current_verilog or "")
                zf.writestr("design.sp", self._current_spice or "")
                zf.writestr("bom.csv", BOMGenerator.to_csv(self._current_bom))
                zf.writestr("bom.json", BOMGenerator.to_json(self._current_bom))
                zf.writestr(
                    "drc.json",
                    json.dumps(self._current_drc.to_dict() if self._current_drc else {}, indent=2),
                )
                zf.writestr("spec.json", json.dumps(self._current_design.spec.to_dict(), indent=2))
                zf.writestr("design.json", json.dumps(self._current_design.to_dict(), indent=2))
                zf.write(svg_path, arcname="schematic.svg")
            self._status.showMessage(f"Exported to {path}", 7000)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "AutoPCB", f"Export failed: {e}")

    def _export_svg(self) -> None:
        if not self._current_design:
            return
        default = str(
            Path(self._default_export_dir())
            / f"{self._current_design.spec.name or 'schematic'}.svg"
        )
        path, _ = QFileDialog.getSaveFileName(self, "Export SVG", default, "SVG (*.svg)")
        if path:
            self._canvas.export_svg(path)
            self._status.showMessage(f"SVG saved to {path}", 5000)

    def _export_png(self) -> None:
        if not self._current_design:
            return
        default = str(
            Path(self._default_export_dir())
            / f"{self._current_design.spec.name or 'schematic'}.png"
        )
        path, _ = QFileDialog.getSaveFileName(self, "Export PNG", default, "PNG (*.png)")
        if path:
            self._canvas.export_png(path)
            self._status.showMessage(f"PNG saved to {path}", 5000)

    # -- plugin invocations ---------------------------------------------
    def _invoke_plugin_action(self, callback) -> None:
        try:
            callback(self)
        except Exception as e:  # noqa: BLE001
            log.exception("Plugin action raised")
            QMessageBox.warning(self, "AutoPCB", f"Plugin action failed: {e}")

    def _run_plugin_exporter(self, exporter) -> None:
        if not self._current_design:
            QMessageBox.information(self, "AutoPCB", "No active design to export.")
            return
        ext_filter = " ".join(f"*.{e.lstrip('.')}" for e in exporter.extensions)
        default_ext = exporter.extensions[0].lstrip(".") if exporter.extensions else "txt"
        default = str(
            Path(self._default_export_dir())
            / f"{self._current_design.spec.name or 'design'}.{default_ext}"
        )
        path, _ = QFileDialog.getSaveFileName(
            self, f"Export — {exporter.name}", default, f"{exporter.name} ({ext_filter})"
        )
        if not path:
            return
        try:
            exporter.callback(self._current_design, Path(path))
            self._status.showMessage(f"Exported: {path}", 6000)
        except Exception as e:  # noqa: BLE001
            log.exception("Plugin exporter raised")
            QMessageBox.warning(self, "AutoPCB", f"Export failed: {e}")

    # -- about -----------------------------------------------------------
    def _show_about(self) -> None:
        plugins = (
            "<br>".join(f"• {p.name} v{p.version}" for p in self._plugins.plugins)
            or "<i>(none loaded)</i>"
        )
        QMessageBox.about(
            self,
            "About AutoPCB",
            "<h3>AutoPCB</h3>"
            "<p>AI-Powered IC Design Desktop App</p>"
            "<p>Stack: Python · PyQt6 · Multi-provider AI (Anthropic / Ollama / "
            "LM Studio / NVIDIA / OpenAI router) · SQLite · Pygments</p>"
            f"<p><b>Plugins:</b><br>{plugins}</p>"
            "<p>© AutoPCB — internal project.</p>",
        )
