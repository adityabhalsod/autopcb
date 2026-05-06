<div align="center">

# ⚡ AutoPCB

**AI-Powered IC Design Desktop App**

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![PyQt6](https://img.shields.io/badge/PyQt6-6.7-41cd52?logo=qt&logoColor=white)](https://pypi.org/project/PyQt6/)
[![License](https://img.shields.io/badge/License-MIT-purple)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20macOS%20%7C%20Windows-lightgrey)](#installation)

> Design integrated circuits from plain English — no ASIC experience required.
> Works fully offline with local AI models (Ollama, LM Studio) or online with Anthropic Claude, NVIDIA AI, and OpenAI-compatible APIs.

<img src="assets/icons/generate.svg" width="64" alt="AutoPCB icon" />

</div>

---

## 🗺️ Table of Contents

- [For Everyone — What Is AutoPCB?](#-for-everyone--what-is-autopcb)
- [Quick Start (5 minutes)](#-quick-start-5-minutes)
- [Features at a Glance](#-features-at-a-glance)
- [Screenshots](#-screenshots)
- [For Developers — Architecture](#-for-developers--architecture)
- [Multi-Provider AI Configuration](#-multi-provider-ai-configuration)
- [Offline Manual Mode](#-offline-manual-mode)
- [Plugin System](#-plugin-system)
- [Project Structure](#-project-structure)
- [Configuration Reference](#-configuration-reference)
- [Contributing](#-contributing)

---

## 👤 For Everyone — What Is AutoPCB?

AutoPCB lets you describe an electronic chip in plain English and get back:

| Output | What it means |
|--------|---------------|
| **Schematic** | A visual diagram of all components and how they connect |
| **Verilog code** | Digital logic code a chip factory can accept |
| **SPICE netlist** | Circuit simulation file for programs like ngspice |
| **Bill of Materials** | Parts list with values (resistors, capacitors, transistors…) |
| **DRC report** | Automatic quality checks — "did you forget to add a power supply?" |

**You don't need to know what any of those mean to use AutoPCB.** Type a description, click Generate, and the AI fills in everything.

### Example prompts you can type

```
Design a 5V to 3.3V LDO voltage regulator with 500mA output current
```
```
4-bit synchronous counter with asynchronous reset
```
```
Low-noise op-amp audio preamplifier with 40dB gain
```
```
SPI-to-I2C bridge controller, 3.3V, 100MHz
```

### Two modes

| Mode | When to use |
|------|-------------|
| **AI Design** | Type a description → AI generates the complete circuit automatically |
| **Manual Canvas** | Drag components from the left panel, connect them yourself |

You can switch between modes freely — the AI can also modify your manual schematic when you ask it to in the chat window.

---

## 🚀 Quick Start (5 minutes)

### Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.11+ | [python.org](https://www.python.org/downloads/) |
| Git | any | To clone the repo |
| AI Provider | see below | At least one is needed for AI mode |

> **No AI provider yet?** Install [Ollama](https://ollama.com) (free, runs on your machine) and skip the API key step.

### Step 1 — Clone and install

```bash
git clone https://github.com/your-org/autopcb.git
cd autopcb
python install.py
```

The installer creates a Python virtual environment, installs all dependencies, and sets up `~/.autopcb/`.

### Step 2 — Configure an AI provider

**Option A — Anthropic Claude (cloud, paid)**
```bash
export ANTHROPIC_API_KEY=sk-ant-...     # Linux / macOS
set ANTHROPIC_API_KEY=sk-ant-...        # Windows CMD
```
Or enter the key in **Settings → AI Provider** after launch.

**Option B — Ollama (free, local, offline)**
```bash
# Install Ollama from https://ollama.com, then:
ollama pull llama3.2
# AutoPCB will auto-detect it — no key needed.
```

**Option C — No AI (manual drawing mode)**  
Skip this step entirely. Use the drag-and-drop canvas to build circuits by hand.

### Step 3 — Launch

```bash
source env/bin/activate   # Windows: env\Scripts\activate
python main.py
```

That's it. The window opens with a component toolbox on the left, a canvas in the centre, and outputs at the bottom.

---

## ✨ Features at a Glance

### 🧠 AI Design Pipeline
- **Multi-provider AI** — Anthropic Claude, Ollama, LM Studio, NVIDIA AI, any OpenAI-compatible router
- Spec parsing → topology generation → component selection → net routing → Verilog → SPICE → BOM → DRC
- All AI calls run on background threads — the UI never freezes
- Retries with exponential back-off on transient API errors

### 🖱️ Offline Manual Canvas
- **Drag components** from the toolbox — 50+ IEEE-standard symbols (R, C, L, MOSFET, BJT, op-amp, gates, flip-flops, SRAMs, UARTs, and more)
- **R** to rotate, **Delete** to remove, **double-click** to edit properties
- Automatic component numbering (R1, R2, C1, U1 …)
- 20 px snap grid, zoom/pan with mouse wheel and middle-button drag

### 🎨 Themes & UI
- **Dark and Light themes** — switch instantly with `Ctrl+T` or Settings → Appearance, no restart needed
- Colour-coded schematic nets (signal, power, clock, ground adapt per theme)
- Live mode indicator in the status bar: green/red/amber dot + provider name + model

### 📦 Outputs
- Synthesizable **Verilog RTL** with Pygments syntax highlighting
- **ngspice-compatible SPICE** netlist
- **CSV + JSON Bill of Materials**
- AI + deterministic **DRC** with FAIL/WARN/PASS badges, auto-fix button
- **SVG**, **PNG**, and **ZIP** export of all artifacts

### 🔌 Plugin System
- Drop a `.py` file in `~/.autopcb/plugins/` — it loads on next launch
- Plugins can register: components, AI providers, exporters, DRC rules, menu actions
- Zero friction: one `register(ctx)` function, full typed API

---

## 📸 Screenshots

> _Screenshots reflect the dark theme. Switch to light with `Ctrl+T`._

| AI Design Mode | Manual Canvas Mode |
|---|---|
| _(AI-generated circuit from a text prompt)_ | _(Drag-and-drop component placement)_ |

---

## 🏗️ For Developers — Architecture

### Tech stack

| Layer | Technology |
|-------|-----------|
| UI framework | PyQt6 6.7 — widgets, QGraphicsScene, QPainter only. **No web tech, no Flask/FastAPI.** |
| AI calls | `anthropic` SDK (Claude) · `httpx` (Ollama / LM Studio / NVIDIA / router) |
| Storage | SQLite via Python stdlib — project versions, chat history |
| Syntax highlight | Pygments 2.20 — Verilog + SPICE code editors |
| Charts | pyqtgraph 0.14 (waveform / power analysis, future) |
| Themes | QSS files in `assets/themes/` — live-reloaded via `ThemeManager` |

### Signal/slot rules
- **All AI calls** must run inside `AIWorker(QThread)` — never block the main thread
- `pyqtSignal` is the only IPC between layers — no shared mutable state
- `ThemeManager.theme_changed` signal propagates QSS reloads to every widget that paints manually

### Data flow
```
User input (SpecPanel)
  │  spec_ready(name, ic_type, description)
  ▼
AIEngine.generate_ic_spec()  ── AIWorker ──▶ SpecParser.parse()
  │                                                │
  ▼                                                ▼
AIEngine.generate_design()  ── AIWorker ──▶ DesignEngine.design()
  │                                                │
  ├──▶ VerilogGenerator     ── AIWorker ──▶ OutputPanel (Verilog tab)
  ├──▶ NetlistGenerator     ── AIWorker ──▶ OutputPanel (SPICE tab)
  ├──▶ BOMGenerator  (sync) ─────────────▶ OutputPanel (BOM tab)
  └──▶ DRCEngine (det + AI) ── AIWorker ──▶ OutputPanel (DRC tab)
                                              │
                                  ProjectStore (SQLite version)
```

---

## 🤖 Multi-Provider AI Configuration

Open **Settings → AI Provider** (or `Edit → Settings`).

### Supported providers

| Provider | Key required | Local / Cloud | Notes |
|----------|-------------|---------------|-------|
| **Anthropic Claude** | Yes (`sk-ant-…`) | Cloud | Best results. `claude-sonnet-4-20250514` default |
| **Ollama** | No | Local (free) | Must be running: `ollama serve` |
| **LM Studio** | No | Local (free) | Start the LM Studio local server first |
| **NVIDIA AI** | Yes (`nvapi-…`) | Cloud | Access via [build.nvidia.com](https://build.nvidia.com) |
| **OpenAI-compatible router** | Optional | Cloud/Local | LiteLLM, vLLM, any `/v1/chat/completions` endpoint |

### Per-provider settings

#### Anthropic
```json
{
  "ai_provider": {
    "active": "anthropic",
    "anthropic": {
      "api_key": "sk-ant-...",
      "model": "claude-sonnet-4-20250514"
    }
  }
}
```

#### Ollama (local)
```json
{
  "ai_provider": {
    "active": "ollama",
    "ollama": {
      "base_url": "http://localhost:11434",
      "model": "llama3.2"
    }
  }
}
```

#### NVIDIA AI
```json
{
  "ai_provider": {
    "active": "nvidia",
    "nvidia": {
      "api_key": "nvapi-...",
      "model": "meta/llama-3.1-70b-instruct"
    }
  }
}
```

> **Tip:** Click **"Auto-detect local"** in Settings to discover Ollama / LM Studio automatically.  
> Click **"Detect models"** to populate the model dropdown from a running server.

### Environment variable override

```bash
export ANTHROPIC_API_KEY=sk-ant-...   # picked up automatically at startup
```

---

## 🖱️ Offline Manual Mode

You can build and export a complete schematic without any AI or internet connection.

1. Switch to the **Components** tab in the left dock
2. **Search** the component library (`R`, `DFF`, `OPAMP`, `UART`…) or pick from the quick-access toolbar
3. **Drag** a component onto the canvas — it snaps to the 20 px grid
4. Press **R** to rotate, **Delete** to remove, **double-click** to edit value/model
5. Build your circuit, then use **File → Export** for SVG / PNG / ZIP
6. At any time, type in the AI chat panel to let the AI modify or extend your schematic

### Available component categories (50+ components)

| Category | Components |
|----------|-----------|
| Passive | R, C, L, Crystal |
| Diodes | Diode, Zener, LED |
| Transistors | NMOS, PMOS, NPN, PNP |
| Analog | OpAmp, Comparator, VREF, LDO, Buck |
| Logic gates | AND2/3, OR2, NOT, NAND2, NOR2, XOR2, XNOR2, BUF |
| Sequential | DFF, JKFF, TFF, 4-bit shift register, 4-bit counter |
| Combinational | MUX2/4, 2-to-4 Decoder, Half/Full Adder, 4-bit ALU |
| Memory | 6T SRAM, ROM, Register File, FIFO |
| Interface | UART, SPI, I2C, PWM |
| Power symbols | VDD, GND, AGND, VREF, Net label |
| Ports | Port In/Out/IO, Bus |

---

## 🔌 Plugin System

Plugins extend AutoPCB with new components, AI backends, exporters, DRC rules, and menu actions — without touching the core codebase.

### Search paths (in order)
1. `<repo>/plugins/` — bundled examples, version-controlled
2. `~/.autopcb/plugins/` — your personal plugins, never overwritten by updates

### Minimal plugin

```python
# ~/.autopcb/plugins/my_rf_transistor.py

def register(ctx):
    ctx.declare(name="My RF Parts", version="1.0", author="you")

    from core.component_library import ComponentDef, PinDef, CAT_TRANSISTOR
    ctx.register_component(ComponentDef(
        id="BFR740", name="BFR740 RF NPN",
        category=CAT_TRANSISTOR, subcategory="RF",
        symbol_type="NPN",
        pins=[PinDef("B","input","left"), PinDef("C","output","top"), PinDef("E","output","bottom")],
        default_params={"model": "BFR740"},
        spice_template="Q{ref} {C} {B} {E} {model}\n",
        description="RF NPN transistor, 7GHz fT",
    ))
```

### All extension points

| Method | What it registers |
|--------|------------------|
| `ctx.register_component(ComponentDef)` | New component in the toolbox |
| `ctx.register_ai_provider(key, ProviderClass)` | New AI provider selectable in Settings |
| `ctx.register_exporter(name, exts, callback)` | New entry under File → Export |
| `ctx.register_drc_rule(rule_id, callback, severity)` | Extra DRC check in the pipeline |
| `ctx.register_action(title, callback, menu, shortcut)` | New menu item (e.g. Plugins menu) |

### Bundled examples

| File | What it shows |
|------|--------------|
| [`plugins/example_capacitor_array.py`](plugins/example_capacitor_array.py) | Minimal — one new component (8-pin cap array) |
| [`plugins/example_ultimate_plugin.py`](plugins/example_ultimate_plugin.py) | **All five extension points** — NE555 timer component · Echo offline AI provider · KiCad .net exporter · decoupling-cap DRC rule · "Insert Power Tree" menu action |

---

## 🗂️ Project Structure

```
autopcb/
├── main.py                     ← entry point
├── install.py                  ← one-shot installer
├── requirements.txt
│
├── core/
│   ├── ai_provider.py          ← Anthropic / Ollama / LM Studio / NVIDIA / router
│   ├── ai_engine.py            ← AIWorker threads, system prompts, retry logic
│   ├── component_library.py    ← 50+ component catalogue + singleton registry
│   ├── design_engine.py        ← ICDesign dataclass, auto-placement
│   ├── spec_parser.py          ← ICSpec parser
│   ├── verilog_generator.py    ← offline + AI Verilog generation
│   ├── netlist_generator.py    ← offline + AI SPICE generation
│   ├── bom_generator.py        ← CSV / JSON BOM
│   ├── drc_engine.py           ← deterministic DRC + plugin rule runner
│   ├── project_store.py        ← SQLite persistence
│   └── plugin_manager.py       ← plugin discovery, context API
│
├── ui/
│   ├── main_window.py          ← MainWindow — docks, menus, plugin wiring
│   ├── schematic_canvas.py     ← QGraphicsView — AI render + EDIT mode drag-drop
│   ├── component_toolbox.py    ← left-dock component palette with drag source
│   ├── spec_panel.py           ← AI spec form + embedded chat
│   ├── settings_dialog.py      ← multi-tab: AI Provider / Appearance / Paths / About
│   ├── output_panel.py         ← tabbed Verilog / SPICE / BOM / DRC viewer
│   ├── property_panel.py       ← right-dock component property inspector
│   ├── project_dialog.py       ← project manager (create / open / version history)
│   ├── theme_manager.py        ← live QSS swap singleton
│   └── widgets/
│       ├── mode_indicator.py   ← status bar: provider + online/offline dot
│       ├── chat_widget.py      ← AI chat bubbles
│       ├── code_editor.py      ← Pygments syntax highlight + line numbers
│       └── progress_widget.py  ← status bar spinner
│
├── assets/
│   ├── themes/
│   │   ├── dark_theme.qss      ← KiCad-inspired dark palette
│   │   └── light_theme.qss     ← light sibling (instant switch via Ctrl+T)
│   └── icons/                  ← SVG toolbar icons
│
└── plugins/                    ← bundled plugin examples
    ├── example_capacitor_array.py
    └── example_ultimate_plugin.py
```

---

## ⚙️ Configuration Reference

Config file: `~/.autopcb/config.json`

```jsonc
{
  // Active AI provider and per-provider settings
  "ai_provider": {
    "active": "anthropic",         // anthropic | ollama | lmstudio | nvidia | openai_router

    "anthropic": {
      "api_key": "sk-ant-...",
      "model": "claude-sonnet-4-20250514"
    },
    "ollama": {
      "base_url": "http://localhost:11434",
      "api_key": "",               // leave blank
      "model": "llama3.2"
    },
    "lmstudio": {
      "base_url": "http://localhost:1234",
      "api_key": "",
      "model": "local-model"
    },
    "nvidia": {
      "base_url": "https://integrate.api.nvidia.com",
      "api_key": "nvapi-...",
      "model": "meta/llama-3.1-70b-instruct"
    },
    "openai_router": {
      "base_url": "http://localhost:4000",
      "api_key": "",
      "model": "gpt-4o-mini"
    }
  },

  // Appearance
  "theme": "dark",                 // dark | light  (Ctrl+T to toggle live)
  "grid_size": 20,                 // canvas snap grid in pixels
  "font_size": 13,

  // Paths
  "output_dir": "/home/user/autopcb/output",
  "ngspice_path": "",              // optional: absolute path to ngspice binary
  "yosys_path": ""                 // optional: absolute path to yosys binary
}
```

---

## 🔧 Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+T` | Toggle dark / light theme |
| `R` | Rotate selected component 90° (canvas focus) |
| `Delete` / `Backspace` | Remove selected component |
| Mouse wheel | Zoom canvas |
| Middle mouse drag | Pan canvas |

---

## 🛠️ Installation Details

### Full install
```bash
python install.py
```
- Creates `env/` virtualenv
- Installs all Python packages (`PyQt6`, `anthropic`, `httpx`, `Pygments`, `pyqtgraph`)
- Creates `~/.autopcb/` with default `config.json`
- Checks for optional `yosys` and `ngspice` on PATH
- Probes PyQt6 with an offscreen Qt application

### Verify only (no install)
```bash
python install.py --check
```

### Force-reinstall packages
```bash
python install.py --reinstall
```

### Optional EDA tools (not required for AI mode)

| Tool | Install | Purpose |
|------|---------|---------|
| `yosys` | `sudo apt install yosys` | Validate generated Verilog synthesis |
| `ngspice` | `sudo apt install ngspice` | Simulate generated SPICE netlists |

### Linux display dependencies
If the app fails to open on a Linux desktop:
```bash
sudo apt install libxcb-cursor0 libxkbcommon-x11-0 libegl1 libgl1
```

---

## 🤝 Contributing

1. Fork the repo and create a feature branch
2. All UI code must use PyQt6 — no Flask, no web views
3. All AI calls must run in `AIWorker(QThread)` — never block the main thread
4. New providers: subclass `AIProvider` in `core/ai_provider.py`, register with `AIProviderFactory`
5. New components: add to `_build_catalogue()` in `core/component_library.py` or via a plugin
6. Run the offscreen smoke test before submitting:
   ```bash
   QT_QPA_PLATFORM=offscreen timeout 5 python main.py
   ```

---

<div align="center">

Made with ⚡ and Python · AutoPCB — internal project

</div>
