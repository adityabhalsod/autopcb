"""AutoPCB core engine package.

Pure-Python AI + EDA logic. No Qt widgets. Safe to import in worker threads.
"""

from __future__ import annotations

__all__ = [
    "ai_engine",
    "spec_parser",
    "design_engine",
    "verilog_generator",
    "netlist_generator",
    "bom_generator",
    "drc_engine",
    "project_store",
]
