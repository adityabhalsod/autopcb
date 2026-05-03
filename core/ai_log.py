"""Centralised AI activity log.

Every AI request, response, retry, error and cancellation is forwarded to a
single :class:`AILogBus` so the UI can display a live stream in the
``AI Log`` tab. The bus is also installed as a Python ``logging.Handler``
that captures the ``autoic.ai`` and ``autoic.provider`` log channels, so
existing ``log.info(...)`` calls automatically appear too.

Persistence
-----------
When :func:`enable_file_persistence` is called (at app startup) the bus also
writes:

* ``<user_dir>/ai_logs/session-<YYYYmmdd-HHMMSS>.jsonl`` — every record
  appended as a single JSON line (compact). One file per app session.
* ``<user_dir>/ai_logs/transcripts/<seq>_<source>.json`` — a separate file
  per request / response / error containing the full system prompt, user
  prompt, response text and metadata. These are intentionally
  human-readable for debugging.

Thread safety
-------------
Bus methods are called from worker threads. We append to a deque under a
lock and emit a Qt signal — Qt marshals the signal to the GUI thread
automatically (queued connection across threads).
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal

log = logging.getLogger("autoic.ai_log")


# ---------------------------------------------------------------------------
# Record
# ---------------------------------------------------------------------------
@dataclass
class AILogRecord:
    ts: float                       # epoch seconds
    level: str                      # "INFO" | "WARN" | "ERROR" | "DEBUG"
    source: str                     # "request" | "response" | "retry" | "cancel" | "logger:<name>"
    message: str
    extra: dict = field(default_factory=dict)

    def formatted(self) -> str:
        t = time.strftime("%H:%M:%S", time.localtime(self.ts))
        ms = int((self.ts - int(self.ts)) * 1000)
        return f"[{t}.{ms:03d}] {self.level:<5} {self.source:<14} {self.message}"

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Bus
# ---------------------------------------------------------------------------
class AILogBus(QObject):
    """Singleton hub for AI log records.

    Use :meth:`instance` to get the global instance. Subscribe to
    :attr:`record_added` from the UI; call :meth:`emit_record` (or any
    convenience helper) from anywhere to push a new entry.
    """

    record_added = pyqtSignal(object)   # AILogRecord

    _instance: Optional["AILogBus"] = None
    _lock = threading.Lock()

    MAX_RECORDS = 2000

    def __init__(self) -> None:
        super().__init__()
        self._records: deque[AILogRecord] = deque(maxlen=self.MAX_RECORDS)
        self._file_lock = threading.Lock()
        self._jsonl_path: Optional[Path] = None
        self._transcript_dir: Optional[Path] = None
        self._seq: int = 0

    @classmethod
    def instance(cls) -> "AILogBus":
        with cls._lock:
            if cls._instance is None:
                cls._instance = AILogBus()
            return cls._instance

    # -- persistence ------------------------------------------------------
    def enable_file_persistence(self, base_dir: Path) -> Path:
        """Start writing records and transcripts under ``base_dir``.

        Returns the resolved log directory.
        """
        base_dir = Path(base_dir)
        base_dir.mkdir(parents=True, exist_ok=True)
        (base_dir / "transcripts").mkdir(exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self._jsonl_path = base_dir / f"session-{stamp}.jsonl"
        self._transcript_dir = base_dir / "transcripts"
        # Header line so the file is easy to identify.
        try:
            with self._jsonl_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "_session_started": stamp,
                    "_pid": int(time.time()),
                }) + "\n")
        except OSError as e:
            log.warning("Could not open AI log file %s: %s", self._jsonl_path, e)
            self._jsonl_path = None
        return base_dir

    @property
    def jsonl_path(self) -> Optional[Path]:
        return self._jsonl_path

    @property
    def transcript_dir(self) -> Optional[Path]:
        return self._transcript_dir

    def _next_seq(self) -> int:
        with self._file_lock:
            self._seq += 1
            return self._seq

    def _persist_record(self, record: AILogRecord) -> None:
        if self._jsonl_path is None:
            return
        try:
            with self._file_lock, self._jsonl_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
        except OSError as e:  # pragma: no cover
            log.debug("Could not append to AI log: %s", e)

    def write_transcript(self, kind: str, payload: dict) -> Optional[Path]:
        """Persist a full request / response payload to a standalone file.

        ``kind`` is one of ``"request"`` / ``"response"`` / ``"error"``.
        Returns the file path written (or ``None`` if persistence is disabled).
        """
        if self._transcript_dir is None:
            return None
        seq = self._next_seq()
        ts = time.strftime("%H%M%S")
        path = self._transcript_dir / f"{seq:05d}_{ts}_{kind}.json"
        try:
            with path.open("w", encoding="utf-8") as f:
                json.dump({
                    "seq": seq,
                    "kind": kind,
                    "timestamp": time.time(),
                    "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    **payload,
                }, f, indent=2, ensure_ascii=False)
            return path
        except OSError as e:
            log.debug("Could not write transcript %s: %s", path, e)
            return None

    # -- public API -------------------------------------------------------
    def records(self) -> list[AILogRecord]:
        return list(self._records)

    def clear(self) -> None:
        self._records.clear()

    def emit_record(self, record: AILogRecord) -> None:
        self._records.append(record)
        self._persist_record(record)
        self.record_added.emit(record)

    # -- convenience helpers ---------------------------------------------
    def log(self, level: str, source: str, message: str, **extra) -> None:
        self.emit_record(AILogRecord(
            ts=time.time(), level=level.upper(), source=source,
            message=message, extra=dict(extra),
        ))

    def info(self, source: str, message: str, **extra) -> None:
        self.log("INFO", source, message, **extra)

    def warn(self, source: str, message: str, **extra) -> None:
        self.log("WARN", source, message, **extra)

    def error(self, source: str, message: str, **extra) -> None:
        self.log("ERROR", source, message, **extra)


# ---------------------------------------------------------------------------
# logging.Handler bridge
# ---------------------------------------------------------------------------
class _BusHandler(logging.Handler):
    def __init__(self, bus: AILogBus) -> None:
        super().__init__(level=logging.DEBUG)
        self._bus = bus

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D401
        try:
            level = record.levelname
            if level == "WARNING":
                level = "WARN"
            if level == "CRITICAL":
                level = "ERROR"
            msg = record.getMessage()
            self._bus.emit_record(AILogRecord(
                ts=record.created, level=level,
                source=f"logger:{record.name.split('.')[-1]}",
                message=msg,
            ))
        except Exception:  # pragma: no cover
            pass


_INSTALLED = False


def install_log_bridge() -> AILogBus:
    """Attach a handler that mirrors `autoic.ai` / `autoic.provider` to the bus.

    Idempotent — safe to call multiple times.
    """
    global _INSTALLED
    bus = AILogBus.instance()
    if _INSTALLED:
        return bus
    handler = _BusHandler(bus)
    handler.setLevel(logging.INFO)
    for name in ("autoic.ai", "autoic.provider"):
        lg = logging.getLogger(name)
        lg.addHandler(handler)
        # Make sure these loggers actually emit at INFO without forcing
        # the root logger config.
        if lg.level == logging.NOTSET or lg.level > logging.INFO:
            lg.setLevel(logging.INFO)
    _INSTALLED = True
    return bus


def enable_file_persistence(base_dir) -> AILogBus:
    """Convenience wrapper — configures persistence on the singleton bus."""
    bus = AILogBus.instance()
    bus.enable_file_persistence(base_dir)
    return bus


__all__ = ["AILogBus", "AILogRecord",
           "install_log_bridge", "enable_file_persistence"]
