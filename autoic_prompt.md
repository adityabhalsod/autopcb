# AutoIC — AI-Powered IC Design Desktop App
## Master Build Prompt v2 (Python + PyQt6)
### Includes: Theme Fix + Multi-AI Provider + Full Offline Mode + Component Toolbox

---

```
<context>
You are a senior Python desktop application engineer and EDA (Electronic Design Automation) specialist.
You are building "AutoIC" — a fully native Python + PyQt6 desktop application that works in TWO modes:

  MODE A — AI-ASSISTED MODE: Uses any configured AI provider (Claude, Ollama, LM Studio,
            NVIDIA AI, OpenAI-compatible routers) to autonomously design ICs from natural language.

  MODE B — OFFLINE MANUAL MODE: Works with zero AI/internet. Engineer manually drags and drops
            real EDA components from a full left-panel toolbox onto the canvas to design ICs
            by hand — exactly like a real EDA workbench (KiCad/Eagle style).

Both modes share the same canvas, schematic engine, netlist generator, BOM, DRC, and export system.
The app detects AI availability at startup and shows which mode is active in the status bar.

This tool is generic — it handles any IC type: digital, analog, mixed-signal, and power management.
</context>

<constraints>
HARD CONSTRAINTS — NEVER violate any of these:
- NEVER use Flask, FastAPI, Django, or any web framework
- NEVER use HTML, CSS, JavaScript, React, Electron, Tauri, or any web technology
- ALL UI MUST be built exclusively with PyQt6 — widgets, QPainter, QGraphicsScene
- NEVER truncate code — every function, every file MUST be complete and runnable
- NEVER write pseudocode, stubs, or "# TODO" placeholders — only real working Python
- NEVER block the Qt main thread — ALL AI calls run inside QThread workers
- ALL generated Verilog MUST be synthesizable and parseable by Yosys
- ALL generated SPICE MUST be ngspice-compatible (.sp format)
- Database: Python stdlib sqlite3 only — no ORM, no SQLAlchemy
- PyQt6 version 6.7.x — use only stable non-deprecated APIs
- Target OS: Linux (Ubuntu 24.04 primary), Windows 10+ secondary
- NEVER use QWebEngineView or any browser/web widget inside the app
- Theme switching MUST work correctly — ALL widgets MUST respond to theme change instantly
  without restart, by reloading QSS at runtime via QApplication.setStyleSheet()
</constraints>

<task>
Build the complete AutoIC application sequentially, module by module.
After each module: ✅ MODULE [N] COMPLETE — [files created] — [one-line description].

---

## PROJECT FILE STRUCTURE

Create exactly this layout:

autoic/
├── main.py
├── requirements.txt
├── README.md
├── assets/
│   ├── icons/                         # SVG icon files for all toolbar + toolbox actions
│   │   ├── resistor.svg
│   │   ├── capacitor.svg
│   │   ├── inductor.svg
│   │   ├── diode.svg
│   │   ├── nmos.svg
│   │   ├── pmos.svg
│   │   ├── npn.svg
│   │   ├── pnp.svg
│   │   ├── opamp.svg
│   │   ├── gate_and.svg
│   │   ├── gate_or.svg
│   │   ├── gate_not.svg
│   │   ├── gate_xor.svg
│   │   ├── gate_nand.svg
│   │   ├── gate_nor.svg
│   │   ├── flipflop_d.svg
│   │   ├── flipflop_jk.svg
│   │   ├── mux.svg
│   │   ├── vdd.svg
│   │   ├── gnd.svg
│   │   ├── net_label.svg
│   │   ├── wire.svg
│   │   └── ...                        # all other component icons
│   └── themes/
│       ├── dark_theme.qss             # Complete dark EDA-style stylesheet
│       └── light_theme.qss            # Complete light EDA-style stylesheet
├── core/
│   ├── __init__.py
│   ├── ai_provider.py                 # Multi-provider AI abstraction layer
│   ├── ai_engine.py                   # IC design AI logic (provider-agnostic)
│   ├── spec_parser.py                 # NL input → structured IC spec JSON
│   ├── design_engine.py               # IC design decision orchestrator
│   ├── netlist_generator.py           # SPICE netlist builder
│   ├── verilog_generator.py           # RTL Verilog builder
│   ├── drc_engine.py                  # Design Rule Check engine
│   ├── bom_generator.py               # Bill of Materials generator
│   ├── component_library.py           # Full offline component definitions + library
│   └── project_store.py              # SQLite project save/load/history
├── ui/
│   ├── __init__.py
│   ├── main_window.py                 # QMainWindow — root layout + docking
│   ├── component_toolbox.py           # Left panel: full offline EDA component toolbox
│   ├── ai_panel.py                    # Left panel (AI mode): spec input + chat
│   ├── schematic_canvas.py            # Center: interactive QGraphicsScene canvas
│   ├── property_panel.py              # Right panel: component properties + rationale
│   ├── output_panel.py                # Bottom tabbed: Verilog, SPICE, BOM, DRC
│   ├── project_dialog.py              # New/Open/Save project dialogs
│   ├── settings_dialog.py             # AI provider config, theme, preferences
│   └── widgets/
│       ├── chat_widget.py             # AI chat interface widget
│       ├── progress_widget.py         # AI generation progress indicator
│       ├── code_editor.py             # Syntax-highlighted read-only code viewer
│       └── mode_indicator.py          # Status bar widget: AI ONLINE / OFFLINE mode
└── output/                            # All generated files saved here per project


---

## MODULE 1 — Project Scaffold + Dual Theme + Entry Point

Files: main.py, requirements.txt, README.md,
       assets/themes/dark_theme.qss, assets/themes/light_theme.qss

### main.py
- QApplication entry point
- Loads theme from ~/.autoic/config.json (default: dark)
- Applies theme via QApplication.instance().setStyleSheet(qss_content)
- Launches MainWindow
- Exposes global function apply_theme(theme_name: str) that reloads QSS at runtime
  and calls QApplication.instance().setStyleSheet() — NO restart required

### Theme System — CRITICAL FIX
- Theme switching MUST work instantly without app restart
- Implementation: ThemeManager(QObject) singleton
  - Method load(theme_name: str): reads .qss file, calls QApplication.instance().setStyleSheet()
  - Signal theme_changed(str): emitted after switch so all widgets can react if needed
  - ThemeManager is imported and used everywhere — NEVER call setStyleSheet directly
- dark_theme.qss color palette:
  - Background: #1e1e2e, Panel: #252535, Canvas: #12121f
  - Accent: #7c3aed (purple), Accent hover: #6d28d9
  - Text primary: #cdd6f4, Text secondary: #a6adc8
  - Success: #a6e3a1, Warning: #f9e2af, Error: #f38ba8
  - Net colors on canvas: signal=#00d4aa, power=#ff6b6b, clock=#ffd700, ground=#888888
- light_theme.qss color palette:
  - Background: #f5f5f5, Panel: #ffffff, Canvas: #e8e8f0
  - Accent: #6d28d9, Text: #1e1e2e
  - Net colors on canvas: signal=#007a5e, power=#cc0000, clock=#b8860b, ground=#555555
- BOTH .qss files MUST style: QMainWindow, QDockWidget, QTabWidget, QToolBar,
  QMenuBar, QTreeWidget, QListWidget, QSplitter, QPushButton, QLineEdit, QTextEdit,
  QComboBox, QScrollBar, QGroupBox, QLabel, QStatusBar, QGraphicsView, QDialog,
  QTreeView, QTableWidget, QHeaderView — ALL widgets, nothing left at Qt default

### requirements.txt
- PyQt6==6.7.*
- anthropic>=0.25.0
- httpx>=0.27.0         # for Ollama, LM Studio, NVIDIA AI REST calls
- pygments>=2.18.0      # syntax highlighting
- pyqtgraph>=0.13.0     # waveform display

### README.md
- pip install -r requirements.txt
- API key setup for each provider
- How to run: python main.py
- How to use offline mode (no API key needed)


---

## MODULE 2 — Multi-Provider AI Abstraction Layer

File: core/ai_provider.py

This is the most critical new module. ALL AI calls go through this layer.
The rest of the app NEVER calls any provider SDK directly — only this module does.

### Supported Providers (ALL must work):

  1. ANTHROPIC CLAUDE
     - SDK: anthropic Python SDK
     - Config: api_key, model (claude-sonnet-4-20250514 default)
     - Auth: Bearer token in header

  2. OLLAMA (local)
     - Protocol: OpenAI-compatible REST at http://localhost:11434/v1
     - Config: base_url (default http://localhost:11434), model name (e.g. llama3, qwen2.5-coder)
     - No API key required
     - Health check: GET http://localhost:11434/api/tags

  3. LM STUDIO (local)
     - Protocol: OpenAI-compatible REST at http://localhost:1234/v1
     - Config: base_url (default http://localhost:1234), model name
     - No API key required
     - Health check: GET http://localhost:1234/v1/models

  4. NVIDIA AI API
     - Protocol: OpenAI-compatible REST at https://integrate.api.nvidia.com/v1
     - Config: api_key (NVIDIA API key), model (e.g. meta/llama-3.1-70b-instruct)
     - Auth: Bearer token

  5. OPENAI-COMPATIBLE ROUTER (catch-all)
     - Protocol: OpenAI /v1/chat/completions endpoint
     - Config: base_url (user-defined), api_key (optional), model (user-defined)
     - Covers: LiteLLM, LocalAI, Groq, Together AI, Mistral, any OpenAI-proxy

### Classes:

AIProviderConfig (dataclass):
  - provider: str  # "anthropic" | "ollama" | "lmstudio" | "nvidia" | "openai_router"
  - base_url: str
  - api_key: str   # empty string if not required
  - model: str
  - timeout_seconds: int = 60
  - max_retries: int = 3

AIProvider (abstract base class):
  - Abstract method: complete(system: str, user: str) -> str
  - Abstract method: health_check() -> bool
  - All implementations MUST handle: connection errors, timeouts, invalid JSON,
    rate limits — raising AIProviderError with human-readable message

AnthropicProvider(AIProvider):
  - Uses anthropic SDK
  - Runs in QThread via AIWorker wrapper

OllamaProvider(AIProvider):
  - Uses httpx to call OpenAI-compatible endpoint
  - health_check(): GET /api/tags, returns True if reachable

LMStudioProvider(AIProvider):
  - Uses httpx to call OpenAI-compatible endpoint
  - health_check(): GET /v1/models

NvidiaAIProvider(AIProvider):
  - Uses httpx to call https://integrate.api.nvidia.com/v1/chat/completions

OpenAIRouterProvider(AIProvider):
  - Generic OpenAI-compatible, base_url fully user-configurable

AIProviderFactory:
  - Static method create(config: AIProviderConfig) -> AIProvider
  - Static method detect_available() -> list[str]:
    - Tries health_check() on Ollama (localhost:11434) and LM Studio (localhost:1234)
    - Returns list of provider names that responded successfully
    - Used at startup to auto-populate available providers in Settings

AIWorker(QThread):
  - Takes: provider: AIProvider, system: str, user: str
  - Signals: response_ready(str), error(str), progress(str)
  - Runs provider.complete() in thread, emits result
  - NEVER called on main thread


---

## MODULE 3 — AI Engine (Provider-Agnostic IC Design Logic)

File: core/ai_engine.py

- Class AIEngine(QObject): uses whichever AIProvider is currently configured
- Property current_provider: AIProvider — set from settings, hot-swappable at runtime
- Property is_available: bool — True if current_provider.health_check() passes
- Method generate_ic_spec(nl_input: str) -> dict
- Method generate_design(spec: dict) -> dict
- Method generate_verilog(design: dict) -> str
- Method generate_spice(design: dict) -> str
- Method run_drc_ai(design: dict) -> dict
- Method chat_modify(current_design: dict, user_message: str) -> dict
- ALL methods run via AIWorker(QThread) — never block main thread
- System prompt sent to every provider: "You are an expert IC design engineer.
  Output ONLY valid JSON when asked for structured data. Output ONLY valid Verilog
  or SPICE when asked for HDL/netlist. Never add prose explanations inside
  structured outputs. Always complete your response — never truncate."


---

## MODULE 4 — Component Library (Full Offline Catalog)

File: core/component_library.py

This module defines the complete library of EDA components available in offline mode.
Each component has: symbol drawing instructions, pin definitions, default values,
SPICE model string, Verilog behavioral model string, color coding by category.

### Component Categories and Members (ALL must be defined):

PASSIVE:
  - Resistor (R): value in Ω, tolerance, power rating
  - Capacitor (C): value in F, voltage rating, type (ceramic/electrolytic/film)
  - Inductor (L): value in H, current rating, DCR
  - Transformer: primary/secondary turns ratio, coupling factor
  - Crystal/Resonator: frequency, load capacitance
  - Ferrite Bead: impedance @ 100MHz

DIODES:
  - Signal Diode (1N4148 default)
  - Zener Diode: breakdown voltage
  - Schottky Diode: forward voltage
  - LED: color (red/green/blue/white/yellow), forward voltage
  - TVS Diode: clamping voltage

TRANSISTORS:
  - NMOS: Vth, W/L ratio, Rds_on
  - PMOS: Vth, W/L ratio, Rds_on
  - NPN BJT: hFE, Vce_sat, Ic_max
  - PNP BJT: hFE, Vce_sat, Ic_max
  - JFET N-channel
  - JFET P-channel

ANALOG:
  - Op-Amp (generic, LM741 default): GBW, slew rate, supply range
  - Comparator: propagation delay, input offset
  - Voltage Reference: output voltage, accuracy
  - Instrumentation Amplifier: gain resistor
  - Differential Amplifier

POWER:
  - LDO Regulator: Vin, Vout, Iout, dropout voltage
  - Buck Converter: Vin, Vout, switching freq, efficiency
  - Boost Converter: Vin, Vout, switching freq
  - Buck-Boost Converter
  - Charge Pump

DIGITAL GATES:
  - AND (2,3,4 input)
  - OR (2,3,4 input)
  - NOT / Inverter
  - NAND (2,3,4 input)
  - NOR (2,3,4 input)
  - XOR (2 input)
  - XNOR (2 input)
  - Buffer / Tri-state Buffer

SEQUENTIAL:
  - D Flip-Flop (with reset, enable)
  - JK Flip-Flop
  - SR Latch
  - T Flip-Flop
  - D Latch
  - Shift Register (4-bit, 8-bit)
  - Counter (4-bit binary, decade)

COMBINATIONAL:
  - Multiplexer (2:1, 4:1, 8:1)
  - Demultiplexer (1:2, 1:4)
  - Encoder (4:2, 8:3 priority)
  - Decoder (2:4, 3:8)
  - Half Adder
  - Full Adder
  - 4-bit ALU
  - Comparator (magnitude)

MEMORY:
  - SRAM cell (6T)
  - ROM (lookup table)
  - Register File (4x8 bit)
  - FIFO (16 deep, 8-bit wide)

INTERFACE:
  - UART TX/RX
  - SPI Master/Slave
  - I2C Master/Slave
  - PWM Generator

POWER SYMBOLS:
  - VDD (with configurable voltage label: 3.3V, 5V, 12V, custom)
  - GND
  - AGND (analog ground)
  - VREF
  - Net Label (named wire connection)

CONNECTORS / IO:
  - Input Port (named)
  - Output Port (named)
  - Bidirectional Port
  - Bus (configurable width)

### ComponentDef (dataclass):
  - id: str
  - name: str
  - category: str
  - subcategory: str
  - symbol_type: str              # used by canvas to know which draw routine to call
  - pins: list[PinDef]
  - default_params: dict          # e.g. {"value": "10k", "tolerance": "1%"}
  - param_schema: dict            # which params are editable and their types
  - spice_template: str           # SPICE line template with {param} placeholders
  - verilog_template: str         # behavioral Verilog template
  - color: str                    # canvas accent color for this component category
  - icon_path: str                # path to SVG icon in assets/icons/

### ComponentLibrary (singleton):
  - Method get_all() -> list[ComponentDef]
  - Method get_by_category(cat: str) -> list[ComponentDef]
  - Method get_by_id(id: str) -> ComponentDef
  - Method search(query: str) -> list[ComponentDef]  # fuzzy search by name/category


---

## MODULE 5 — IC Spec Parser

File: core/spec_parser.py

- Class SpecParser: converts AI JSON spec response into typed Python dataclasses
- Dataclass ICSpec: name, ic_type (digital/analog/mixed/power), technology_node,
  supply_voltage, input_pins: list[PinDef], output_pins: list[PinDef],
  functional_description, performance_targets: dict, constraints: list[str]
- Dataclass PinDef: name, direction, voltage_level, pin_type (power/signal/clock/ground)
- Method parse(raw_json: dict) -> ICSpec: validates, raises SpecValidationError on bad data
- Method to_clarification_questions(partial_spec: ICSpec) -> list[str]


---

## MODULE 6 — Design Engine

File: core/design_engine.py

- Class DesignEngine: orchestrates full IC design flow (AI-assisted mode)
- Method design(spec: ICSpec) -> ICDesign: spec → topology → components → nets → rationale
- Dataclass ICDesign: spec, components: list[Component], nets: list[Net],
  rationale: dict, timing_estimates: dict, power_estimate_mw: float, area_estimate_um2: float
- Dataclass Component: id, component_def: ComponentDef, params: dict,
  position: QPointF, rotation: int, rationale: str
- Dataclass Net: id, name, connected_pins: list[tuple[str,str]],
  net_type (power/signal/clock/ground), color: str
- For DIGITAL: components selected from ComponentLibrary digital/sequential categories
- For ANALOG: components selected from passive/diode/transistor/analog categories with real values
- For POWER: power management components with calculated switching parameters


---

## MODULE 7 — Verilog Generator

File: core/verilog_generator.py

- Class VerilogGenerator
- Method generate(design: ICDesign) -> str: complete synthesizable Verilog
- Uses component verilog_template from ComponentDef for offline-placed components
- For AI-generated designs: full module from AI output
- MUST include: module declaration, all ports, wire/reg declarations,
  always blocks, assign statements, submodule instantiations, endmodule
- Header comment: IC name, AutoIC v2, date, spec summary, provider used


---

## MODULE 8 — SPICE Netlist Generator

File: core/netlist_generator.py

- Class NetlistGenerator
- Method generate(design: ICDesign) -> str: complete ngspice-compatible SPICE
- Uses component spice_template from ComponentDef for offline-placed components
- Format: .title, component lines, .model, .subckt, .op/.ac/.tran, .end
- MUST validate: no floating nets, all nodes referenced, supply rails present


---

## MODULE 9 — BOM Generator

File: core/bom_generator.py

- Class BOMGenerator
- Method generate(design: ICDesign) -> list[BOMEntry]
- Dataclass BOMEntry: reference, component_type, value, model, description, quantity
- Method to_csv(entries) -> str
- Method to_json(entries) -> str


---

## MODULE 10 — DRC Engine

File: core/drc_engine.py

- Class DRCEngine
- Method run(design: ICDesign, netlist: str) -> DRCReport
- Static rules (work fully offline without AI):
  - DIGITAL: fan-out > 8 = WARN, undriven inputs = FAIL, missing power = FAIL,
    clock without flip-flop = WARN, bus width mismatch = FAIL
  - ANALOG: floating net = FAIL, no bypass cap on supply = WARN,
    no DC path to ground = FAIL, reverse-biased supply = FAIL
  - ALL: duplicate reference designators = FAIL, overlapping components = WARN
- AI-enhanced rules (only when AI available):
  - Biasing validity check, stability margin, timing closure estimate
- Dataclass DRCReport: violations: list[DRCViolation], pass_count, warn_count, fail_count
- Dataclass DRCViolation: rule_id, severity (PASS/WARN/FAIL), component_ref, message, fix
- Method auto_fix(design, violations) -> ICDesign: AI applies fixes (AI mode only)


---

## MODULE 11 — Project Store (SQLite)

File: core/project_store.py

- Class ProjectStore: all sqlite3 operations
- Tables: projects, design_versions, chat_history
- Schema adds: mode column ("ai" | "offline") per design_version
- Method create_project(name, ic_type) -> int
- Method save_version(project_id, design, verilog, spice, mode) -> int
- Method load_latest(project_id) -> tuple[ICDesign, str, str]
- Method list_projects() -> list[dict]
- Method get_chat_history(project_id) -> list[dict]
- Method append_chat(project_id, role, message)


---

## MODULE 12 — Schematic Canvas (QGraphicsScene)

File: ui/schematic_canvas.py

- Class SchematicCanvas(QGraphicsView) with QGraphicsScene
- TWO sub-modes:
  - READ mode: renders AI-generated design (called by DesignEngine)
  - EDIT mode: full drag-and-drop manual placement (offline mode)

### Component Symbol Drawing (QPainter — IEEE standard):
  - Resistor: zigzag line with lead wires
  - Capacitor: two parallel plates (polarized: curved bottom)
  - Inductor: series of semicircles
  - Diode: triangle + bar, cathode/anode leads
  - LED: diode symbol + two outgoing arrows
  - Zener: diode with bent cathode bar
  - NMOS: vertical channel line, gate bar, arrow pointing in, D/G/S labels
  - PMOS: same with arrow pointing out
  - NPN/PNP BJT: circle with base, emitter (arrow), collector
  - Op-Amp: triangle, +/- inputs left, output right, power rails top/bottom
  - AND/OR/NAND/NOR/XOR gates: proper curved IEEE logic symbols
  - NOT/Buffer: triangle with/without bubble
  - D/JK/T Flip-Flop: rectangle with pin labels D,Q,Qn,CLK,R,S
  - Mux/Demux: trapezoid with select lines
  - VDD: upward arrow with voltage label
  - GND: three horizontal lines (descending width)
  - Net Label: small flag with name text
  - Input/Output Port: directional arrow shape with name

### Net Coloring (from theme — net_type → color):
  - signal: #00d4aa (dark) / #007a5e (light)
  - power: #ff6b6b (dark) / #cc0000 (light)
  - clock: #ffd700 (dark) / #b8860b (light)
  - ground: #888888 both themes

### EDIT Mode — Drag and Drop:
  - Accept QDrag events from ComponentToolbox
  - On drop: place ghost component at cursor, snap to 50px grid
  - Click placed component: select it (blue highlight border)
  - Selected component: show resize handles, rotation handle
  - Press R: rotate component 90° clockwise
  - Press Delete: remove selected component
  - Wire drawing mode: click a pin → drag → click another pin → draws orthogonal wire
  - Wire routing: auto L-shape (horizontal then vertical), with junction dots at T-joins
  - Double-click component: open property editor dialog
  - Middle-click drag: pan canvas
  - Mouse wheel: zoom in/out (Ctrl+scroll = fine zoom)
  - Right-click: context menu (Edit Properties, Rotate, Mirror, Delete, Add Label)

### Both Modes:
  - Grid: 50px dot grid, toggleable via View menu
  - Rulers: top and left rulers with unit labels (um, mm, grid units) — toggleable
  - Method render_design(design: ICDesign): full render from ICDesign object
  - Method get_current_design() -> ICDesign: serializes current manual canvas state
  - Method export_svg(filepath)
  - Method export_png(filepath, dpi=300)
  - Signal component_selected(Component): emitted on click


---

## MODULE 13 — Component Toolbox (Left Panel — Offline Mode)

File: ui/component_toolbox.py

This is the primary left panel when in OFFLINE mode (or always visible as a side panel).
It is a full professional EDA component palette — every component in ComponentLibrary
must appear here, organized by category.

- Class ComponentToolbox(QWidget)
- Layout: QVBoxLayout
  - Top: QLineEdit search bar (filters components in real time as user types)
  - Middle: QTreeWidget showing all components grouped by category
    - Category nodes: PASSIVE, DIODES, TRANSISTORS, ANALOG, POWER, DIGITAL GATES,
      SEQUENTIAL, COMBINATIONAL, MEMORY, INTERFACE, POWER SYMBOLS, CONNECTORS/IO
    - Each category has a colored left border stripe matching component color
    - Each component row: SVG icon (24x24) + component name + hotkey hint
    - Expand/collapse categories
  - Bottom: preview panel (120x120px QGraphicsView) showing IEEE symbol of hovered component

### Drag and Drop:
  - User clicks and drags any component from the tree → QDrag initiated with component id
  - SchematicCanvas accepts the drop and places the component

### Quick-Access Toolbar (above tree):
  - Icon buttons for most-used components: Resistor, Capacitor, Inductor, NMOS, PMOS,
    GND, VDD, Wire, Net Label — single click activates placement mode on canvas

### Component color coding in tree (left border color by category):
  - PASSIVE: #a0c4ff (blue)
  - DIODES: #ffadad (red)
  - TRANSISTORS: #ffd6a5 (orange)
  - ANALOG: #caffbf (green)
  - POWER: #fdffb6 (yellow)
  - DIGITAL GATES: #c77dff (purple)
  - SEQUENTIAL: #9d4edd (deep purple)
  - COMBINATIONAL: #7b2d8b (violet)
  - MEMORY: #ff9e00 (amber)
  - INTERFACE: #48cae4 (cyan)
  - POWER SYMBOLS: #ff6b6b (crimson)
  - CONNECTORS: #b7e4c7 (mint)


---

## MODULE 14 — AI Panel (Left Panel — AI Mode)

File: ui/ai_panel.py

This panel replaces (or tabs with) ComponentToolbox when AI mode is active.

- Class AIPanel(QWidget)
- Layout: QVBoxLayout
  - AI Mode indicator badge: green dot "AI ONLINE — [provider name] — [model]"
    or red dot "AI OFFLINE — Manual Mode"
  - IC Name: QLineEdit
  - IC Type: QComboBox (Digital / Analog / Mixed-Signal / Power)
  - Description: QTextEdit (multiline NL input)
    placeholder: "Describe your IC in plain English.
    Example: Design a 5V to 3.3V LDO voltage regulator with 500mA output,
    thermal shutdown at 150°C, and soft-start capability."
  - QPushButton "Generate IC Design" (disabled when AI offline)
  - Separator
  - ChatWidget for ongoing AI conversation about the design
- Signal: spec_ready(str, str, str) → (name, ic_type, nl_description)
- When AI is OFFLINE: show message "AI unavailable — use Component Toolbox to design manually"
  and disable Generate button


---

## MODULE 15 — Main Window

File: ui/main_window.py

- Class MainWindow(QMainWindow): 1440x900 minimum size
- Startup sequence:
  1. Load theme from config
  2. Run AIProviderFactory.detect_available() in background thread
  3. Show mode indicator in status bar
  4. If AI available: show AIPanel in left dock (ComponentToolbox still accessible via tab)
  5. If AI offline: show ComponentToolbox in left dock, show AI tab as disabled

### Panel Layout (QDockWidgets — all dockable and resizable):
  - Left dock (320px default): QTabWidget with two tabs:
    - Tab 1 "Components" → ComponentToolbox (always available)
    - Tab 2 "AI Design" → AIPanel (enabled/disabled based on AI availability)
  - Center: SchematicCanvas
  - Right dock (280px default): PropertyPanel
  - Bottom dock (280px default): OutputPanel

### Menu Bar:
  - File: New, Open, Save, Save As, Export SVG, Export PNG, Export ZIP, Separator, Quit
  - Edit: Undo, Redo, Select All, Delete Selected, Separator, Settings
  - View: Toggle Left Panel, Toggle Right Panel, Toggle Bottom Panel,
    Separator, Toggle Grid, Toggle Rulers, Separator, Zoom In, Zoom Out, Fit to Window
  - AI: Generate IC Design, Run DRC, Auto-Fix Violations, Separator,
    Switch AI Provider, Test Connection
  - Theme: Dark Mode, Light Mode (MUST switch instantly without restart)
  - Help: About AutoIC, Documentation, Report Bug

### Toolbar (icon + tooltip for each):
  New | Open | Save || Generate IC | Run DRC | Auto-Fix || 
  Export SVG | Export ZIP || Undo | Redo || Grid | Rulers ||
  Dark/Light theme toggle button (moon/sun icon)

### Theme Toggle — CRITICAL:
  - Toolbar has a QPushButton with moon icon (dark) or sun icon (light)
  - On click: calls ThemeManager.load(new_theme)
  - ThemeManager calls QApplication.instance().setStyleSheet(new_qss)
  - ALL widgets update instantly — verified by checking QDockWidget, QTabWidget,
    canvas background, toolbox colors ALL change without restart

### Status Bar:
  - Left: current project name
  - Center: ModeIndicator widget (AI ONLINE / OFFLINE + provider name)
  - Right: zoom level % + canvas coordinates

### Key Methods:
  - on_generate_clicked(): spec → DesignEngine → SchematicCanvas.render_design() + OutputPanel
  - on_export_zip(): Verilog + SPICE + BOM CSV + DRC report + SVG → ZIP
  - on_drc_clicked(): DRCEngine.run(canvas.get_current_design()) → OutputPanel DRC tab
  - on_theme_toggle(): ThemeManager.load() → instant switch


---

## MODULE 16 — Property Panel

File: ui/property_panel.py

- Class PropertyPanel(QWidget)
- Sections:
  - Component Info (QFormLayout): reference, type, value, model
  - Parameters: editable QLineEdit fields for each param in component_def.param_schema
    (e.g. resistance, tolerance for Resistor — live-update canvas on change)
  - AI Rationale (QTextEdit read-only): shown only in AI mode
  - Pin Table (QTableWidget): pin name | direction | net connected | voltage level
  - Timing/Power (QLabel): delay estimate, power dissipation
- Method update_component(component: Component, rationale: str)
- Method clear()
- Parameter edits: emit component_params_changed(component_id, new_params) → canvas re-renders symbol


---

## MODULE 17 — Output Panel

Files: ui/output_panel.py, ui/widgets/code_editor.py

OutputPanel(QWidget):
- QTabWidget: Verilog | SPICE | BOM | DRC Report
- Verilog tab: CodeEditor (verilog highlight) + Copy + Save + "Open in Yosys" button
- SPICE tab: CodeEditor (spice highlight) + Copy + Save + "Open in ngspice" button
- BOM tab: QTableWidget (Ref, Type, Value, Model, Description, Qty) + Export CSV
- DRC tab: QTreeWidget (PASS green / WARN yellow / FAIL red categories)
  + "Auto-Fix All" button (AI mode only, grayed out offline)
- Method load_verilog(code), load_spice(code), load_bom(entries), load_drc(report)

CodeEditor(QWidget):
- QTextEdit read-only, monospace font (JetBrains Mono → Courier fallback)
- Pygments QSyntaxHighlighter subclass — verilog and spice modes
- Line number gutter (painted QWidget)
- Copy to clipboard, Save to file buttons


---

## MODULE 18 — Settings Dialog (Multi-Provider Config)

File: ui/settings_dialog.py

- Class SettingsDialog(QDialog) — full provider configuration UI
- Layout: QTabWidget with tabs: AI Provider | Appearance | Paths | About

### AI Provider Tab:
  - QComboBox "Active Provider": Anthropic Claude | Ollama (Local) | LM Studio (Local) |
    NVIDIA AI | OpenAI-Compatible Router
  - Provider-specific fields shown dynamically based on selection:
    - Anthropic: API Key (password field + show/hide), Model selector
    - Ollama: Base URL (default http://localhost:11434), Model name input,
      "Detect Models" button (calls /api/tags, populates model dropdown)
    - LM Studio: Base URL (default http://localhost:1234), Model name input,
      "Detect Models" button
    - NVIDIA AI: API Key, Model selector (preset list of NVIDIA-hosted models)
    - OpenAI Router: Base URL (text input), API Key (optional), Model name (text input)
  - "Test Connection" button: runs health_check() in QThread, shows green/red result
  - "Auto-Detect Local" button: scans Ollama + LM Studio, shows what's found
  - Connection status indicator (colored dot + text)

### Appearance Tab:
  - Theme: Dark / Light radio buttons — on change calls ThemeManager.load() INSTANTLY
  - Canvas grid size: QSpinBox (10–100px)
  - Font size: QSpinBox

### Paths Tab:
  - Output directory: QLineEdit + Browse button
  - ngspice path: QLineEdit + Browse (for "Open in ngspice" button)
  - Yosys path: QLineEdit + Browse

### Settings persistence:
  - Save to ~/.autoic/config.json on OK
  - Load on startup


---

## MODULE 19 — Chat Widget + Mode Indicator

Files: ui/widgets/chat_widget.py, ui/widgets/mode_indicator.py

ChatWidget(QWidget):
- QScrollArea containing QWidget with QVBoxLayout for message bubbles
- User bubbles: right-aligned, rounded rect, accent blue background
- AI bubbles: left-aligned, rounded rect, dark purple background, provider name label
- QLineEdit + QPushButton "Send" at bottom (disabled when AI offline)
- AI responses: stream token-by-token using QTimer updating last bubble text
- Emits: user_message_sent(str)

ModeIndicator(QWidget):
- Small status widget for status bar
- Shows: colored circle (green=online, red=offline, yellow=connecting) + text
- Text format: "AI ONLINE · Ollama · llama3.2" or "OFFLINE · Manual Mode"
- Method set_status(provider_name: str, model: str, online: bool)


---

## MODULE 20 — Project Dialog

File: ui/project_dialog.py

- Class ProjectDialog(QDialog)
- Tab 1 "New Project": name, IC type, description, mode radio (AI / Manual)
- Tab 2 "Open Project": QTableWidget (name, type, mode, date, versions) + Open + Delete
- Tab 3 "Version History": versions for selected project + Load Version button


---

## OUTPUT FORMAT

For each module:
1. Output ALL files — complete code, zero truncation, every function implemented
2. After each module: ✅ MODULE [N] COMPLETE — [files] — [one-line description]
3. After all 20 modules: complete file tree + pip install command + python main.py
4. End with sample walkthrough A (AI mode): "Design a 555 timer equivalent IC" → full output
5. End with sample walkthrough B (offline mode): engineer drags R, C, NPN onto canvas,
   draws wires, runs DRC, exports SPICE netlist — show exactly what happens step by step

Start with MODULE 1. Make all architectural decisions yourself.
Document every non-obvious decision with an inline comment.
Never ask for clarification — proceed and document assumptions.
</task>

<success_criteria>
SCENARIO A — AI ONLINE:
User runs "python main.py" with ANTHROPIC_API_KEY set. Dark theme loads. Left panel shows
AI Design tab active. User types "Design a 4-bit binary adder IC", clicks Generate.
App calls Claude, renders schematic with full adder gate symbols on canvas,
fills Verilog tab with synthesizable adder module, fills SPICE tab, shows BOM and DRC.
User clicks the sun icon in toolbar — theme switches to light instantly, no restart.
User goes to Settings → switches provider to Ollama → clicks Test Connection → sees green.

SCENARIO B — OFFLINE:
User runs "python main.py" with no API key. Status bar shows "OFFLINE · Manual Mode".
Left panel shows Component Toolbox. User drags Resistor, Capacitor, NPN transistor,
VDD symbol, GND symbol onto canvas. Draws wires connecting them.
Double-clicks Resistor → edits value to 10kΩ. Clicks Run DRC → sees 1 WARN (no bypass cap).
Clicks Export ZIP → gets SPICE netlist + BOM + DRC report in ZIP. All without any AI call.

BOTH SCENARIOS must work without terminal errors or missing imports.
</success_criteria>
```