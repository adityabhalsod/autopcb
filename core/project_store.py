"""SQLite-backed project store. Stdlib only — no ORM."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .design_engine import ICDesign
from .spec_parser import SpecParser

log = logging.getLogger("autoic.store")


SCHEMA = [
    """CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        ic_type TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS design_versions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        version_num INTEGER NOT NULL,
        spec_json TEXT NOT NULL,
        design_json TEXT NOT NULL,
        verilog TEXT NOT NULL DEFAULT '',
        spice TEXT NOT NULL DEFAULT '',
        bom_json TEXT NOT NULL DEFAULT '[]',
        drc_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    )""",
    """CREATE TABLE IF NOT EXISTS chat_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        role TEXT NOT NULL,
        message TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    )""",
    "CREATE INDEX IF NOT EXISTS idx_versions_project ON design_versions(project_id)",
    "CREATE INDEX IF NOT EXISTS idx_chat_project ON chat_history(project_id)",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ProjectStore:
    """Thread-safe enough for our use: a dedicated lock + new connection per call."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._migrate()

    # -- low level --------------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _migrate(self) -> None:
        with self._lock, self._connect() as conn:
            for stmt in SCHEMA:
                conn.execute(stmt)
            conn.commit()

    # -- project CRUD -----------------------------------------------------
    def create_project(self, name: str, ic_type: str) -> int:
        ts = _utc_now()
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO projects (name, ic_type, created_at, updated_at) "
                "VALUES (?,?,?,?)",
                (name, ic_type, ts, ts),
            )
            conn.commit()
            return int(cur.lastrowid)

    def delete_project(self, project_id: int) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
            conn.commit()

    def list_projects(self) -> list[dict]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT p.*, "
                "(SELECT COUNT(*) FROM design_versions v WHERE v.project_id=p.id) AS versions "
                "FROM projects p ORDER BY p.updated_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]

    def get_project(self, project_id: int) -> dict | None:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
            return dict(row) if row else None

    # -- versions ---------------------------------------------------------
    def save_version(
        self,
        project_id: int,
        design: ICDesign,
        verilog: str = "",
        spice: str = "",
        bom: list | None = None,
        drc: dict | None = None,
    ) -> int:
        ts = _utc_now()
        spec_json = json.dumps(design.spec.to_dict())
        design_json = json.dumps(design.to_dict())
        bom_json = json.dumps(bom or [])
        drc_json = json.dumps(drc or {})
        with self._lock, self._connect() as conn:
            ver = conn.execute(
                "SELECT COALESCE(MAX(version_num),0)+1 FROM design_versions WHERE project_id=?",
                (project_id,),
            ).fetchone()[0]
            cur = conn.execute(
                "INSERT INTO design_versions "
                "(project_id, version_num, spec_json, design_json, verilog, spice, bom_json, drc_json, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (project_id, ver, spec_json, design_json, verilog, spice, bom_json, drc_json, ts),
            )
            conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (ts, project_id))
            conn.commit()
            return int(cur.lastrowid)

    def list_versions(self, project_id: int) -> list[dict]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT id, version_num, created_at FROM design_versions "
                "WHERE project_id=? ORDER BY version_num DESC",
                (project_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def load_version(self, version_id: int) -> dict | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM design_versions WHERE id=?", (version_id,)
            ).fetchone()
            if not row:
                return None
            return self._inflate_version(dict(row))

    def load_latest(self, project_id: int) -> dict | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM design_versions WHERE project_id=? "
                "ORDER BY version_num DESC LIMIT 1",
                (project_id,),
            ).fetchone()
            if not row:
                return None
            return self._inflate_version(dict(row))

    @staticmethod
    def _inflate_version(row: dict) -> dict:
        design_dict = json.loads(row["design_json"])
        spec_dict = json.loads(row["spec_json"])
        # Patch spec into design dict if missing.
        design_dict.setdefault("spec", spec_dict)
        design = ICDesign.from_dict(design_dict)
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "version_num": row["version_num"],
            "design": design,
            "verilog": row.get("verilog", ""),
            "spice": row.get("spice", ""),
            "bom": json.loads(row.get("bom_json") or "[]"),
            "drc": json.loads(row.get("drc_json") or "{}"),
            "created_at": row["created_at"],
        }

    # -- chat history -----------------------------------------------------
    def append_chat(self, project_id: int, role: str, message: str) -> int:
        ts = _utc_now()
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO chat_history (project_id, role, message, timestamp) "
                "VALUES (?,?,?,?)",
                (project_id, role, message, ts),
            )
            conn.commit()
            return int(cur.lastrowid)

    def get_chat_history(self, project_id: int) -> list[dict]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM chat_history WHERE project_id=? ORDER BY id ASC",
                (project_id,),
            ).fetchall()
            return [dict(r) for r in rows]
