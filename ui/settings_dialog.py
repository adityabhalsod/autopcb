"""Multi-tab settings dialog — provider, appearance, paths, about.

Theme switches are applied **immediately** through ``ThemeManager`` so the
user sees the change without restart.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from PyQt6 import sip
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QStackedWidget,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.ai_provider import (
    ALL_PROVIDERS,
    DEFAULT_BASE_URLS,
    DEFAULT_MODELS,
    PROVIDER_ANTHROPIC,
    PROVIDER_LABELS,
    PROVIDER_LMSTUDIO,
    PROVIDER_NVIDIA,
    PROVIDER_OLLAMA,
    PROVIDER_OPENAI_ROUTER,
    AIProviderConfig,
    AIProviderError,
    AIProviderFactory,
    is_wsl,
    windows_host_ip,
)

log = logging.getLogger("autopcb.settings")

ANTHROPIC_MODELS = [
    "claude-sonnet-4-20250514",
    "claude-opus-4-20250514",
    "claude-3-5-sonnet-20241022",
]
NVIDIA_MODELS = [
    "meta/llama-3.1-70b-instruct",
    "meta/llama-3.1-405b-instruct",
    "mistralai/mixtral-8x22b-instruct-v0.1",
    "nvidia/llama-3.1-nemotron-70b-instruct",
]


class _ProbeWorker(QThread):
    finished_ok = pyqtSignal(bool, str, list)

    def __init__(self, config: AIProviderConfig) -> None:
        super().__init__()
        self._config = config

    def run(self) -> None:
        try:
            provider = AIProviderFactory.create(self._config)
            ok = bool(provider.health_check())
            models: list[str] = []
            list_models = getattr(provider, "list_models", None)
            if callable(list_models):
                try:
                    models = list_models() or []
                except Exception:  # noqa: BLE001
                    models = []
            self.finished_ok.emit(
                ok,
                "Connection OK" if ok else "Provider unreachable",
                models,
            )
        except AIProviderError as e:
            self.finished_ok.emit(False, str(e), [])
        except Exception as e:  # noqa: BLE001
            self.finished_ok.emit(False, f"Unexpected: {e}", [])


class _ProviderTab(QWidget):
    def __init__(self, config: dict) -> None:
        super().__init__()
        self._config = config
        self._closing = False
        self._probe_generation = 0
        self._workers: list[_ProbeWorker] = []
        self._build()
        self._load()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        self._provider = QComboBox()
        for key in ALL_PROVIDERS:
            self._provider.addItem(PROVIDER_LABELS[key], key)
        self._provider.currentIndexChanged.connect(self._on_provider_changed)
        prov_row = QFormLayout()
        prov_row.addRow("Active provider:", self._provider)
        layout.addLayout(prov_row)

        self._stack = QStackedWidget()
        self._pages: dict[str, dict] = {}
        for key in ALL_PROVIDERS:
            page, fields = self._build_page(key)
            self._stack.addWidget(page)
            self._pages[key] = fields
        layout.addWidget(self._stack)

        self._status = QLabel("Idle")
        self._status.setObjectName("muted")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        btn_row = QHBoxLayout()
        self._test_btn = QPushButton("Test connection")
        self._test_btn.clicked.connect(self._test_current)
        self._models_btn = QPushButton("Detect models")
        self._models_btn.clicked.connect(self._detect_models)
        self._detect_btn = QPushButton("Auto-detect local")
        self._detect_btn.clicked.connect(self._detect_local)
        btn_row.addWidget(self._test_btn)
        btn_row.addWidget(self._models_btn)
        btn_row.addWidget(self._detect_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

    def _build_page(self, key: str) -> tuple[QWidget, dict]:
        page = QWidget()
        form = QFormLayout(page)
        fields: dict = {}
        if key == PROVIDER_ANTHROPIC:
            api = QLineEdit()
            api.setEchoMode(QLineEdit.EchoMode.Password)
            api.setPlaceholderText("sk-ant-...")
            toggle = QPushButton("👁")
            toggle.setCheckable(True)
            toggle.setFixedWidth(34)
            toggle.toggled.connect(
                lambda v: api.setEchoMode(
                    QLineEdit.EchoMode.Normal if v else QLineEdit.EchoMode.Password
                )
            )
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.addWidget(api, 1)
            row.addWidget(toggle)
            wrap = QWidget()
            wrap.setLayout(row)
            form.addRow("API key:", wrap)
            model = QComboBox()
            model.setEditable(True)
            for m in ANTHROPIC_MODELS:
                model.addItem(m)
            form.addRow("Model:", model)
            fields["api_key"] = api
            fields["model"] = model
        elif key in (PROVIDER_OLLAMA, PROVIDER_LMSTUDIO, PROVIDER_OPENAI_ROUTER):
            base = QLineEdit(DEFAULT_BASE_URLS[key])
            form.addRow("Base URL:", base)
            api = QLineEdit()
            api.setEchoMode(QLineEdit.EchoMode.Password)
            api.setPlaceholderText("(optional)")
            form.addRow("API key:", api)
            model = QComboBox()
            model.setEditable(True)
            model.addItem(DEFAULT_MODELS[key])
            form.addRow("Model:", model)
            fields["base_url"] = base
            fields["api_key"] = api
            fields["model"] = model
        elif key == PROVIDER_NVIDIA:
            base = QLineEdit(DEFAULT_BASE_URLS[PROVIDER_NVIDIA])
            form.addRow("Base URL:", base)
            api = QLineEdit()
            api.setEchoMode(QLineEdit.EchoMode.Password)
            api.setPlaceholderText("nvapi-...")
            form.addRow("API key:", api)
            model = QComboBox()
            model.setEditable(True)
            for m in NVIDIA_MODELS:
                model.addItem(m)
            form.addRow("Model:", model)
            fields["base_url"] = base
            fields["api_key"] = api
            fields["model"] = model
        return page, fields

    def _load(self) -> None:
        prov_cfg = self._config.get("ai_provider") or {}
        active = prov_cfg.get("active") or PROVIDER_ANTHROPIC
        if active not in ALL_PROVIDERS:
            active = PROVIDER_ANTHROPIC
        idx = list(ALL_PROVIDERS).index(active)
        self._provider.setCurrentIndex(idx)
        self._stack.setCurrentIndex(idx)
        legacy_key = self._config.get("api_key", "")
        legacy_model = self._config.get("model", "")
        for key, fields in self._pages.items():
            cfg = prov_cfg.get(key, {})
            if key == PROVIDER_ANTHROPIC:
                fields["api_key"].setText(cfg.get("api_key", legacy_key))
                if cfg.get("model") or legacy_model:
                    fields["model"].setEditText(cfg.get("model", legacy_model))
            else:
                fields["base_url"].setText(cfg.get("base_url", DEFAULT_BASE_URLS[key]))
                fields["api_key"].setText(cfg.get("api_key", ""))
                fields["model"].setEditText(cfg.get("model", DEFAULT_MODELS[key]))
        self._status.setText("Click Detect models to refresh the live model list.")

    def _on_provider_changed(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        if self._closing:
            return
        provider_key = self._provider.itemData(index)
        provider_label = PROVIDER_LABELS.get(provider_key, provider_key)
        self._status.setText(f"{provider_label} selected. Click Detect models to refresh.")

    def collect(self) -> dict:
        active = self._provider.currentData()
        prov_cfg = self._config.get("ai_provider") if isinstance(self._config.get("ai_provider"), dict) else {}
        result = {"active": active}
        for key, fields in self._pages.items():
            existing = prov_cfg.get(key, {}) if isinstance(prov_cfg.get(key), dict) else {}
            entry = {}
            for preserved_key in ("timeout_seconds", "max_retries", "extra"):
                if preserved_key in existing:
                    entry[preserved_key] = existing[preserved_key]
            if "api_key" in fields:
                entry["api_key"] = fields["api_key"].text().strip()
            if "model" in fields:
                entry["model"] = fields["model"].currentText().strip()
            if "base_url" in fields:
                entry["base_url"] = fields["base_url"].text().strip()
            result[key] = entry
        return result

    def active_config(self) -> AIProviderConfig:
        data = self.collect()
        active = data["active"]
        section = data.get(active, {})
        return AIProviderConfig.from_dict({**section, "provider": active})

    def _test_current(self) -> None:
        cfg = self.active_config()
        self._status.setText(f"Probing {PROVIDER_LABELS[cfg.provider]}…")
        worker = _ProbeWorker(cfg)
        worker.finished_ok.connect(self._on_test_done)
        worker.finished.connect(
            lambda: self._workers.remove(worker) if worker in self._workers else None
        )
        self._workers.append(worker)
        worker.start()

    def _on_test_done(self, ok: bool, message: str, _models: list) -> None:
        if self._closing or sip.isdeleted(self._status):
            return
        self._status.setText(("✅ " if ok else "❌ ") + message)

    def _detect_models(self) -> None:
        if self._closing:
            return
        cfg = self.active_config()
        active_key = cfg.provider
        self._probe_generation += 1
        probe_generation = self._probe_generation
        # Anthropic has no public /v1/models REST endpoint — use the
        # bundled hardcoded list to populate the dropdown.
        if active_key == PROVIDER_ANTHROPIC:
            combo: QComboBox = self._pages[active_key]["model"]
            current = combo.currentText()
            combo.clear()
            for m in ANTHROPIC_MODELS:
                combo.addItem(m)
            if current:
                combo.setEditText(current)
            self._status.setText(f"Loaded {len(ANTHROPIC_MODELS)} Claude models")
            return
        self._status.setText(f"Fetching models from {PROVIDER_LABELS[active_key]}…")
        worker = _ProbeWorker(cfg)

        def _done(_ok: bool, msg: str, models: list) -> None:
            if self._closing or probe_generation != self._probe_generation:
                return
            if sip.isdeleted(self) or sip.isdeleted(self._status):
                return
            if active_key not in self._pages:
                return
            page = self._pages[active_key]
            combo = page.get("model")
            if combo is None or sip.isdeleted(combo):
                return
            if models:
                combo: QComboBox = self._pages[active_key]["model"]
                current = combo.currentText()
                combo.clear()
                for m in models:
                    combo.addItem(m)
                if current:
                    combo.setEditText(current)
                # The provider may have rewritten its base_url to a working
                # WSL fallback. Reflect that in the UI so Save persists it.
                live_cfg = AIProviderFactory.create(cfg).config
                if (
                    active_key in (PROVIDER_OLLAMA, PROVIDER_LMSTUDIO, PROVIDER_OPENAI_ROUTER)
                    and live_cfg.base_url
                    and live_cfg.base_url != cfg.base_url
                ):
                    base_url = self._pages[active_key].get("base_url")
                    if base_url is not None and not sip.isdeleted(base_url):
                        base_url.setText(live_cfg.base_url)
                self._status.setText(
                    f"✅ Loaded {len(models)} models from " f"{PROVIDER_LABELS[active_key]}"
                )
            else:
                hint = ""
                if (
                    is_wsl()
                    and active_key in (PROVIDER_OLLAMA, PROVIDER_LMSTUDIO)
                    and "localhost" in (cfg.base_url or "")
                ):
                    host = windows_host_ip()
                    if host:
                        hint = (
                            f"  Tip: WSL detected — try "
                            f"http://{host}:11434  (Windows host).  "
                            f"Also set OLLAMA_HOST=0.0.0.0 on Windows."
                        )
                    else:
                        hint = (
                            "  Tip: WSL detected — set OLLAMA_HOST=0.0.0.0 "
                            "on Windows and use the Windows host IP "
                            "(run `ip route` in WSL to find it)."
                        )
                self._status.setText(
                    f"⚠️ No models returned ({msg}) — type the model name " f"manually.{hint}"
                )

        def _cleanup() -> None:
            if worker in self._workers:
                self._workers.remove(worker)

        worker.finished_ok.connect(_done)
        worker.finished.connect(_cleanup)
        self._workers.append(worker)
        worker.start()

    def _detect_local(self) -> None:
        if self._closing:
            return
        found = AIProviderFactory.detect_available(
            anthropic_key=self._pages[PROVIDER_ANTHROPIC]["api_key"].text()
        )
        if not found:
            self._status.setText("No local AI providers detected.")
        else:
            labels = ", ".join(PROVIDER_LABELS.get(f, f) for f in found)
            self._status.setText(f"Detected: {labels}")

    def shutdown(self) -> None:
        self._closing = True
        self._probe_generation += 1
        for worker in list(self._workers):
            try:
                worker.finished_ok.disconnect()
            except (TypeError, RuntimeError):
                pass


class _AppearanceTab(QWidget):
    def __init__(self, config: dict, theme_manager) -> None:
        super().__init__()
        self._theme_manager = theme_manager
        layout = QFormLayout(self)
        self._dark = QRadioButton("Dark")
        self._pcb = QRadioButton("PCB (real board look)")
        group = QButtonGroup(self)
        group.addButton(self._dark)
        group.addButton(self._pcb)
        current = config.get("theme", "dark")
        if current == "pcb":
            self._pcb.setChecked(True)
        else:
            self._dark.setChecked(True)
        self._dark.toggled.connect(self._on_theme)
        self._pcb.toggled.connect(self._on_theme)
        row = QHBoxLayout()
        row.addWidget(self._dark)
        row.addWidget(self._pcb)
        row.addStretch(1)
        wrap = QWidget()
        wrap.setLayout(row)
        layout.addRow("Theme:", wrap)
        self._grid = QSpinBox()
        self._grid.setRange(10, 100)
        self._grid.setValue(int(config.get("grid_size", 20)))
        layout.addRow("Canvas grid (px):", self._grid)
        self._font_size = QSpinBox()
        self._font_size.setRange(9, 18)
        self._font_size.setValue(int(config.get("font_size", 13)))
        layout.addRow("Font size:", self._font_size)

    def _selected_theme(self) -> str:
        if self._pcb.isChecked():
            return "pcb"
        return "dark"

    def _on_theme(self, _checked: bool) -> None:
        if self._theme_manager is None:
            return
        new = self._selected_theme()
        if getattr(self._theme_manager, "current", None) != new:
            self._theme_manager.load(new)

    def collect(self) -> dict:
        return {
            "theme": self._selected_theme(),
            "grid_size": self._grid.value(),
            "font_size": self._font_size.value(),
        }


class _PathsTab(QWidget):
    def __init__(self, config: dict) -> None:
        super().__init__()
        layout = QFormLayout(self)
        self._out = self._make_row(
            layout, "Output directory:", config.get("output_dir", ""), dir_only=True
        )
        self._ngspice = self._make_row(
            layout, "ngspice path:", config.get("ngspice_path", ""), dir_only=False
        )
        self._yosys = self._make_row(
            layout, "yosys path:", config.get("yosys_path", ""), dir_only=False
        )

    def _make_row(self, form: QFormLayout, label: str, value: str, dir_only: bool) -> QLineEdit:
        edit = QLineEdit(value)
        btn = QPushButton("Browse…")

        def _browse() -> None:
            if dir_only:
                p = QFileDialog.getExistingDirectory(self, "Select directory", edit.text())
            else:
                p, _ = QFileDialog.getOpenFileName(self, "Select executable", edit.text())
            if p:
                edit.setText(p)

        btn.clicked.connect(_browse)
        row = QHBoxLayout()
        row.addWidget(edit, 1)
        row.addWidget(btn)
        wrap = QWidget()
        wrap.setLayout(row)
        form.addRow(label, wrap)
        return edit

    def collect(self) -> dict:
        return {
            "output_dir": self._out.text().strip(),
            "ngspice_path": self._ngspice.text().strip(),
            "yosys_path": self._yosys.text().strip(),
        }


class _AboutTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        text = QTextEdit()
        text.setReadOnly(True)
        text.setHtml(
            "<h2>AutoPCB</h2>"
            "<p>AI-Powered IC Design Desktop App.</p>"
            "<p><b>Providers:</b> Anthropic Claude · Ollama · LM Studio · "
            "NVIDIA AI · OpenAI-compatible router</p>"
            "<p><b>Plugins:</b> drop <code>.py</code> files into "
            "<code>~/.autopcb/plugins/</code> or the bundled "
            "<code>plugins/</code> folder. See "
            "<code>plugins/example_ultimate_plugin.py</code> for the full "
            "plugin authoring reference.</p>"
        )
        layout.addWidget(text)


class SettingsDialog(QDialog):
    def __init__(self, config: dict, config_path: Path, theme_manager=None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("AutoPCB — Settings")
        self.resize(640, 460)
        self._config = dict(config or {})
        self._config_path = Path(config_path)
        self._original_theme = self._config.get("theme", "dark")
        self._theme_manager = theme_manager

        tabs = QTabWidget()
        self._tab_provider = _ProviderTab(self._config)
        self._tab_appearance = _AppearanceTab(self._config, theme_manager)
        self._tab_paths = _PathsTab(self._config)
        tabs.addTab(self._tab_provider, "AI Provider")
        tabs.addTab(self._tab_appearance, "Appearance")
        tabs.addTab(self._tab_paths, "Paths")
        tabs.addTab(_AboutTab(), "About")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self._cancel)

        layout = QVBoxLayout(self)
        layout.addWidget(tabs, 1)
        layout.addWidget(buttons)

    def _cancel(self) -> None:
        self._tab_provider.shutdown()
        if (
            self._theme_manager is not None
            and getattr(self._theme_manager, "current", None) != self._original_theme
        ):
            self._theme_manager.load(self._original_theme)
        self.reject()

    def _save(self) -> None:
        self._tab_provider.shutdown()
        provider_data = self._tab_provider.collect()
        appearance = self._tab_appearance.collect()
        paths = self._tab_paths.collect()
        active = provider_data["active"]
        active_section = provider_data.get(active, {})
        self._config.update(
            {
                "ai_provider": provider_data,
                "api_key": active_section.get("api_key", ""),
                "model": active_section.get("model", ""),
            }
        )
        self._config.update(appearance)
        self._config.update(paths)
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        self._config_path.write_text(json.dumps(self._config, indent=2))
        self.accept()

    def result_config(self) -> dict:
        return self._config

    def active_provider_config(self) -> AIProviderConfig:
        return self._tab_provider.active_config()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._tab_provider.shutdown()
        super().closeEvent(event)
