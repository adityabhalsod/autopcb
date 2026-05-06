#!/usr/bin/env python3
"""AutoPCB — AI-Powered IC Design Desktop App.

Entry point. Bootstraps logging, user data dir, theme, and launches the
Qt main window.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import signal
import sys
import traceback
from pathlib import Path

# ---------------------------------------------------------------------------
# Suppress noisy GPU driver probes on systems without hardware acceleration
# (WSL, headless, container hosts). Must be set BEFORE Qt is imported.
# ---------------------------------------------------------------------------
os.environ.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")
os.environ.setdefault("MESA_LOG_LEVEL", "silent")
os.environ.setdefault("EGL_LOG_LEVEL", "fatal")

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------
APP_NAME = "AutoPCB"
APP_VERSION = "1.0.0"
ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
THEMES_DIR = ASSETS / "themes"
ICONS_DIR = ASSETS / "icons"
PLUGINS_DIR = ROOT / "plugins"

USER_DIR = Path.home() / ".autopcb"
USER_PLUGINS_DIR = USER_DIR / "plugins"
CONFIG_PATH = USER_DIR / "config.json"
LOG_PATH = USER_DIR / "autopcb.log"
AI_LOG_DIR = USER_DIR / "ai_logs"
DB_PATH = USER_DIR / "autopcb.db"
DEFAULT_OUTPUT_DIR = ROOT / "output"


def ensure_user_dir() -> dict:
    """Create ~/.autopcb and return loaded config."""
    USER_DIR.mkdir(parents=True, exist_ok=True)
    USER_PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
    AI_LOG_DIR.mkdir(parents=True, exist_ok=True)
    (AI_LOG_DIR / "transcripts").mkdir(parents=True, exist_ok=True)
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not CONFIG_PATH.exists():
        cfg = {
            "api_key": os.environ.get("ANTHROPIC_API_KEY", ""),
            "model": "claude-sonnet-4-20250514",
            "theme": "dark",
            "output_dir": str(DEFAULT_OUTPUT_DIR),
        }
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
        return cfg

    try:
        return json.loads(CONFIG_PATH.read_text() or "{}")
    except json.JSONDecodeError:
        return {}


def setup_logging() -> None:
    handler = logging.handlers.RotatingFileHandler(
        LOG_PATH, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    stream = logging.StreamHandler(sys.stderr)
    stream.setFormatter(logging.Formatter("[%(levelname)s] %(name)s: %(message)s"))

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    root.addHandler(stream)
    logging.getLogger("anthropic").setLevel(logging.WARNING)


def load_theme() -> str:  # legacy helper kept for compatibility
    try:
        return (THEMES_DIR / "dark_theme.qss").read_text(encoding="utf-8")
    except OSError:
        return ""


def main() -> int:
    cfg = ensure_user_dir()
    setup_logging()
    log = logging.getLogger("autopcb")
    log.info("Starting %s v%s", APP_NAME, APP_VERSION)

    # Persist every AI request/response under ~/.autopcb/ai_logs/ so users can
    # trace and debug what the model received and returned.
    from core.ai_log import enable_file_persistence, install_log_bridge

    install_log_bridge()
    enable_file_persistence(AI_LOG_DIR)
    log.info("AI transcripts \u2192 %s", AI_LOG_DIR)

    # Import Qt only after env is ready so log captures any Qt issues.
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QFont, QIcon
    from PyQt6.QtWidgets import QApplication

    # Qt6 enables high-DPI scaling automatically; the AA_EnableHighDpiScaling
    # attribute was removed. Set it defensively if present (forward-compat).
    _hidpi = getattr(Qt.ApplicationAttribute, "AA_EnableHighDpiScaling", None)
    if _hidpi is not None:
        QApplication.setAttribute(_hidpi, True)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("AutoPCB")
    app.setStyle("Fusion")

    # Font: Inter if available, otherwise system fallback.
    app.setFont(QFont("Inter", 10))

    # Theme manager — single source of truth, supports live switching.
    from ui.theme_manager import ThemeManager

    theme_manager = ThemeManager.init(THEMES_DIR)
    theme_manager.load(cfg.get("theme", "dark"))

    icon = ICONS_DIR / "generate.svg"
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))

    # Global exception hook to surface tracebacks via logger + dialog.
    def excepthook(exc_type, exc_value, exc_tb):
        # Ignore Ctrl+C — just shut down quietly.
        if issubclass(exc_type, KeyboardInterrupt):
            log.info("Interrupted by user (Ctrl+C). Exiting.")
            try:
                app.quit()
            except Exception:
                pass
            return
        msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        log.error("Unhandled exception:\n%s", msg)
        try:
            from PyQt6.QtWidgets import QMessageBox

            QMessageBox.critical(None, "AutoPCB — Unhandled Error", msg)
        except Exception:
            pass

    sys.excepthook = excepthook

    # Restore the default SIGINT handler so Ctrl+C in the launching terminal
    # cleanly terminates the Qt event loop instead of escaping into Python.
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    from ui.main_window import MainWindow

    window = MainWindow(
        config=cfg,
        config_path=CONFIG_PATH,
        db_path=DB_PATH,
        icons_dir=ICONS_DIR,
        plugin_dirs=[PLUGINS_DIR, USER_PLUGINS_DIR],
        theme_manager=theme_manager,
    )
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
