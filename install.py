"""AutoIC v2 installer.

One-shot setup for AutoIC. Creates the local virtual environment (if missing),
installs Python requirements, prepares the user data directory
(`~/.autoic/`), seeds a default `config.json` with multi-provider AI
settings, and verifies that the optional EDA toolchain (yosys, ngspice) is
on PATH.

Usage:
    python install.py             # full setup
    python install.py --check     # only verify environment
    python install.py --reinstall # force-reinstall requirements
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_DIR = ROOT / "env"
REQUIREMENTS = ROOT / "requirements.txt"
PLUGINS_DIR = ROOT / "plugins"
THEMES_DIR = ROOT / "assets" / "themes"

USER_DIR = Path.home() / ".autoic"
USER_PLUGINS_DIR = USER_DIR / "plugins"
CONFIG_PATH = USER_DIR / "config.json"
LOG_PATH = USER_DIR / "autoic.log"

PY_MIN = (3, 11)


# ---------------------------------------------------------------------------
# Pretty printing
# ---------------------------------------------------------------------------
class C:
    R = "\033[31m"
    G = "\033[32m"
    Y = "\033[33m"
    B = "\033[34m"
    M = "\033[35m"
    C = "\033[36m"
    W = "\033[37m"
    BOLD = "\033[1m"
    END = "\033[0m"


def info(msg: str) -> None:
    print(f"{C.C}[i]{C.END} {msg}")


def ok(msg: str) -> None:
    print(f"{C.G}[✓]{C.END} {msg}")


def warn(msg: str) -> None:
    print(f"{C.Y}[!]{C.END} {msg}")


def err(msg: str) -> None:
    print(f"{C.R}[x]{C.END} {msg}")


def banner() -> None:
    print(f"{C.M}{C.BOLD}")
    print("  ╔═══════════════════════════════════════════════════════════╗")
    print("  ║              AutoIC v2 — Installer & Bootstrap           ║")
    print("  ║   AI-Powered IC Design Desktop App (PyQt6)               ║")
    print("  ║   Multi-provider AI · Offline manual mode · Plugins      ║")
    print("  ╚═══════════════════════════════════════════════════════════╝")
    print(C.END)


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------
def check_python() -> None:
    if sys.version_info < PY_MIN:
        err(f"Python {PY_MIN[0]}.{PY_MIN[1]}+ required (found {platform.python_version()})")
        sys.exit(1)
    ok(f"Python {platform.python_version()} on {platform.system()} {platform.release()}")


def venv_python() -> Path:
    if os.name == "nt":
        return ENV_DIR / "Scripts" / "python.exe"
    return ENV_DIR / "bin" / "python"


def ensure_venv() -> Path:
    py = venv_python()
    if py.exists():
        ok(f"Virtualenv exists at {ENV_DIR}")
        return py
    info(f"Creating virtualenv at {ENV_DIR} ...")
    subprocess.check_call([sys.executable, "-m", "venv", str(ENV_DIR)])
    ok("Virtualenv created")
    return py


def pip_install(py: Path, reinstall: bool) -> None:
    if not REQUIREMENTS.exists():
        err(f"Missing {REQUIREMENTS}")
        sys.exit(1)
    info("Upgrading pip ...")
    subprocess.check_call([str(py), "-m", "pip", "install", "--upgrade", "pip"])
    cmd = [str(py), "-m", "pip", "install", "-r", str(REQUIREMENTS)]
    if reinstall:
        cmd.insert(-2, "--force-reinstall")
    info(f"Installing requirements (PyQt6, anthropic, httpx, Pygments, pyqtgraph …): {' '.join(cmd)}")
    subprocess.check_call(cmd)
    ok("Python requirements installed")


def ensure_user_dir() -> None:
    USER_DIR.mkdir(parents=True, exist_ok=True)

    # Personal plugins directory — users drop .py files here
    USER_PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
    ok(f"User plugins dir: {USER_PLUGINS_DIR}")

    if not CONFIG_PATH.exists():
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        default = {
            # ── v2 multi-provider config ────────────────────────────────────
            "ai_provider": {
                "active": "anthropic" if api_key else "ollama",
                "anthropic": {
                    "api_key": api_key,
                    "model": "claude-sonnet-4-20250514",
                },
                "ollama": {
                    "base_url": "http://localhost:11434",
                    "api_key": "",
                    "model": "llama3.2",
                },
                "lmstudio": {
                    "base_url": "http://localhost:1234",
                    "api_key": "",
                    "model": "local-model",
                },
                "nvidia": {
                    "base_url": "https://integrate.api.nvidia.com/v1",
                    "api_key": "",
                    "model": "meta/llama-3.1-70b-instruct",
                },
                "openai_router": {
                    "base_url": "http://localhost:4000/v1",
                    "api_key": "",
                    "model": "gpt-4o-mini",
                },
            },
            # ── legacy keys kept for backward compatibility ─────────────────
            "api_key": api_key,
            "model": "claude-sonnet-4-20250514",
            # ── appearance / paths ──────────────────────────────────────────
            "theme": "dark",
            "grid_size": 20,
            "font_size": 13,
            "output_dir": str(ROOT / "output"),
            "ngspice_path": "",
            "yosys_path": "",
        }
        CONFIG_PATH.write_text(json.dumps(default, indent=2))
        if api_key:
            ok(f"Created config with Anthropic provider at {CONFIG_PATH}")
        else:
            ok(f"Created config with Ollama as default provider at {CONFIG_PATH}")
            info("  (no ANTHROPIC_API_KEY found — change provider in Settings after launch)")
    else:
        ok(f"Config exists at {CONFIG_PATH}")
        _maybe_migrate_config()

    LOG_PATH.touch(exist_ok=True)
    (ROOT / "output").mkdir(exist_ok=True)


def _maybe_migrate_config() -> None:
    """Silently add missing v2 keys to an existing v1 config."""
    try:
        cfg = json.loads(CONFIG_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return

    dirty = False
    if "ai_provider" not in cfg:
        api_key = cfg.get("api_key", "")
        cfg["ai_provider"] = {
            "active": "anthropic" if api_key else "ollama",
            "anthropic": {"api_key": api_key, "model": cfg.get("model", "claude-sonnet-4-20250514")},
            "ollama": {"base_url": "http://localhost:11434", "api_key": "", "model": "llama3.2"},
            "lmstudio": {"base_url": "http://localhost:1234", "api_key": "", "model": "local-model"},
            "nvidia": {"base_url": "https://integrate.api.nvidia.com/v1", "api_key": "", "model": "meta/llama-3.1-70b-instruct"},
            "openai_router": {"base_url": "http://localhost:4000/v1", "api_key": "", "model": "gpt-4o-mini"},
        }
        dirty = True
    if "grid_size" not in cfg:
        cfg["grid_size"] = 20
        dirty = True
    if "font_size" not in cfg:
        cfg["font_size"] = 13
        dirty = True
    if dirty:
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
        ok("Config migrated to v2 schema")


def check_tool(name: str, hint: str) -> None:
    path = shutil.which(name)
    if path:
        ok(f"{name} found: {path}")
    else:
        warn(f"{name} not on PATH — install with: {hint}")


def check_eda_tools() -> None:
    info("Checking optional EDA tools (used to validate generated artifacts) ...")
    is_linux = platform.system() == "Linux"
    yosys_hint = "sudo apt install yosys" if is_linux else "see https://yosyshq.net/yosys/"
    ngspice_hint = "sudo apt install ngspice" if is_linux else "see http://ngspice.sourceforge.net/"
    check_tool("yosys", yosys_hint)
    check_tool("ngspice", ngspice_hint)


def check_qt_runtime() -> None:
    info("Checking Qt runtime and core v2 modules (offscreen probe) ...")
    py = venv_python()
    code = (
        "import os, sys;"
        "os.environ.setdefault('QT_QPA_PLATFORM','offscreen');"
        "from PyQt6.QtWidgets import QApplication;"
        "app = QApplication(sys.argv);"
        "import sys as _sys; _sys.path.insert(0, os.getcwd());"
        "from ui.theme_manager import ThemeManager;"
        "from core.plugin_manager import PluginManager;"
        "from core.component_library import ComponentLibrary;"
        "from core.ai_provider import AIProviderFactory;"
        "print('qt-ok')"
    )
    try:
        out = subprocess.check_output(
            [str(py), "-c", code],
            stderr=subprocess.STDOUT,
            timeout=30,
            cwd=str(ROOT),
        )
        if b"qt-ok" in out:
            ok("PyQt6 + all v2 core modules import cleanly")
        else:
            warn(f"Unexpected probe output: {out!r}")
    except subprocess.CalledProcessError as e:
        warn(f"Module probe failed:\n{e.output.decode(errors='ignore').strip()}")
        if platform.system() == "Linux":
            warn("If Qt fails: sudo apt install libxcb-cursor0 libxkbcommon-x11-0 libegl1 libgl1")


def print_next_steps(py: Path) -> None:
    print()
    print(f"{C.BOLD}{'─' * 60}{C.END}")
    print(f"{C.BOLD}  Next steps{C.END}")
    print(f"{C.BOLD}{'─' * 60}{C.END}")
    activate = "env\\Scripts\\activate" if os.name == "nt" else "source env/bin/activate"
    print(f"{C.C}1) Activate the virtualenv:{C.END}")
    print(f"     {activate}")
    print()
    print(f"{C.C}2) Choose an AI provider:{C.END}")
    print(f"   {C.G}Option A — Anthropic Claude (cloud, best results):{C.END}")
    print(f"     export ANTHROPIC_API_KEY=sk-ant-...")
    print(f"   {C.G}Option B — Ollama (free, local, works offline):{C.END}")
    print(f"     # Install Ollama from https://ollama.com, then:")
    print(f"     ollama pull llama3.2")
    print(f"     # AutoIC will auto-detect it in Settings → AI Provider")
    print(f"   {C.G}Option C — No AI (demo / manual canvas mode):{C.END}")
    print(f"     # Use the Echo provider (bundled plugin) for zero-config demo.")
    print(f"     # Enable via Settings → AI Provider → select 'echo' (after loading plugins)")
    print()
    print(f"{C.C}3) Add personal plugins:{C.END}")
    print(f"     Drop .py plugin files into: {USER_PLUGINS_DIR}")
    print(f"     They auto-load on next launch — no restart script needed.")
    print()
    print(f"{C.C}4) Launch AutoIC:{C.END}")
    print(f"     python main.py")
    print()
    print(f"{C.Y}Tip:{C.END} Toggle dark/light theme at any time with {C.BOLD}Ctrl+T{C.END}")
    print(f"{C.Y}Tip:{C.END} Press {C.BOLD}R{C.END} on the canvas to rotate a selected component")
    print()


def check_assets() -> None:
    """Verify bundled assets directory exists."""
    if not THEMES_DIR.exists():
        warn(f"Themes directory not found: {THEMES_DIR} — UI may fall back to no stylesheet")
    else:
        ok(f"Themes: {', '.join(p.name for p in sorted(THEMES_DIR.glob('*.qss')))}")
    if not PLUGINS_DIR.exists():
        warn(f"Bundled plugins directory not found: {PLUGINS_DIR}")
    else:
        bundled = [p.name for p in PLUGINS_DIR.glob("*.py")]
        ok(f"Bundled plugins: {', '.join(bundled) if bundled else '(none)'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="AutoIC v2 installer")
    parser.add_argument("--check", action="store_true", help="Only verify environment")
    parser.add_argument("--reinstall", action="store_true", help="Force reinstall requirements")
    args = parser.parse_args()

    banner()
    check_python()

    if args.check:
        py = venv_python()
        if not py.exists():
            err("Virtualenv missing — run `python install.py` first")
            sys.exit(1)
        ok(f"Virtualenv: {py}")
        ensure_user_dir()
        check_assets()
        check_eda_tools()
        check_qt_runtime()
        print_next_steps(py)
        return

    py = ensure_venv()
    pip_install(py, args.reinstall)
    ensure_user_dir()
    check_assets()
    check_eda_tools()
    check_qt_runtime()

    print()
    ok("AutoIC v2 installation complete.")
    print_next_steps(py)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        err(f"Command failed (exit {e.returncode}): {e}")
        sys.exit(e.returncode)
    except KeyboardInterrupt:
        err("Interrupted")
        sys.exit(130)
