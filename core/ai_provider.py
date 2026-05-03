"""Multi-provider AI abstraction.

Every AI call in AutoIC routes through one of these providers. Adding a new
backend means subclassing :class:`AIProvider` and registering it in
:class:`AIProviderFactory`.

Supported out of the box:
    * ``anthropic``      — Anthropic Claude (requires API key)
    * ``ollama``         — Local Ollama server (no key)
    * ``lmstudio``       — Local LM Studio server (no key)
    * ``nvidia``         — NVIDIA AI catalog (requires API key)
    * ``openai_router``  — Any OpenAI-compatible REST endpoint

All providers expose two methods only: ``complete(system, user)`` and
``health_check()``. They MUST be safe to call from a worker thread.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from .ai_log import AILogBus

log = logging.getLogger("autoic.provider")


# ---------------------------------------------------------------------------
# WSL helpers — when AutoIC runs inside WSL but the local LLM server
# (Ollama / LM Studio) lives on the Windows host, ``localhost`` does NOT
# bridge across. We auto-detect the Windows host IP and try it as a
# fallback whenever a ``localhost`` base URL fails.
# ---------------------------------------------------------------------------
_WSL_HOST_CACHE: Optional[str] = None


def _is_wsl() -> bool:
    if os.name != "posix":
        return False
    if "microsoft" in os.uname().release.lower():
        return True
    try:
        with open("/proc/version", "r", encoding="utf-8") as f:
            return "microsoft" in f.read().lower()
    except OSError:
        return False


def _windows_host_ip() -> Optional[str]:
    """Return the Windows host IP reachable from WSL2, or ``None``."""
    global _WSL_HOST_CACHE
    if _WSL_HOST_CACHE is not None:
        return _WSL_HOST_CACHE or None
    if not _is_wsl():
        _WSL_HOST_CACHE = ""
        return None
    # 1) /etc/resolv.conf nameserver is the Windows host on WSL2 (default).
    try:
        with open("/etc/resolv.conf", "r", encoding="utf-8") as f:
            for line in f:
                m = re.match(r"\s*nameserver\s+([0-9.]+)", line)
                if m:
                    _WSL_HOST_CACHE = m.group(1)
                    return _WSL_HOST_CACHE
    except OSError:
        pass
    # 2) default route gateway.
    try:
        out = subprocess.check_output(
            ["ip", "route", "show", "default"], text=True, timeout=2.0)
        m = re.search(r"default via ([0-9.]+)", out)
        if m:
            _WSL_HOST_CACHE = m.group(1)
            return _WSL_HOST_CACHE
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        pass
    _WSL_HOST_CACHE = ""
    return None


def _candidate_bases(base_url: str) -> list[str]:
    """Expand a configured base URL into fallback candidates.

    For WSL: ``http://localhost:11434`` →
        [original, ``http://<windows-host-ip>:11434``,
         ``http://host.docker.internal:11434``].
    """
    base = (base_url or "").rstrip("/")
    if not base:
        return []
    out = [base]
    host = _windows_host_ip()
    # Only rewrite local-loopback URLs.
    if re.search(r"//(localhost|127\.0\.0\.1)([:/])", base):
        if host:
            out.append(re.sub(r"//(localhost|127\.0\.0\.1)",
                              f"//{host}", base, count=1))
        out.append(re.sub(r"//(localhost|127\.0\.0\.1)",
                          "//host.docker.internal", base, count=1))
    # Deduplicate while preserving order.
    seen: set[str] = set()
    return [u for u in out if not (u in seen or seen.add(u))]


# ---------------------------------------------------------------------------
# Optional deps
# ---------------------------------------------------------------------------
try:
    import httpx
except Exception:  # pragma: no cover
    httpx = None  # type: ignore[assignment]

try:
    import anthropic
    from anthropic import APIError as _AnthropicAPIError
except Exception:  # pragma: no cover
    anthropic = None
    _AnthropicAPIError = Exception


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------
class AIProviderError(Exception):
    """Raised by any provider when a request cannot be completed."""


class AIProviderUnavailable(AIProviderError):
    """Raised by health checks when a backend is unreachable."""


# ---------------------------------------------------------------------------
# Config dataclass
# ---------------------------------------------------------------------------
PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_OLLAMA = "ollama"
PROVIDER_LMSTUDIO = "lmstudio"
PROVIDER_NVIDIA = "nvidia"
PROVIDER_OPENAI_ROUTER = "openai_router"

ALL_PROVIDERS = (
    PROVIDER_ANTHROPIC, PROVIDER_OLLAMA, PROVIDER_LMSTUDIO,
    PROVIDER_NVIDIA, PROVIDER_OPENAI_ROUTER,
)

PROVIDER_LABELS = {
    PROVIDER_ANTHROPIC: "Anthropic Claude",
    PROVIDER_OLLAMA: "Ollama (Local)",
    PROVIDER_LMSTUDIO: "LM Studio (Local)",
    PROVIDER_NVIDIA: "NVIDIA AI",
    PROVIDER_OPENAI_ROUTER: "OpenAI-Compatible Router",
}

DEFAULT_BASE_URLS = {
    PROVIDER_ANTHROPIC: "",
    PROVIDER_OLLAMA: "http://localhost:11434",
    PROVIDER_LMSTUDIO: "http://localhost:1234",
    PROVIDER_NVIDIA: "https://integrate.api.nvidia.com/v1",
    PROVIDER_OPENAI_ROUTER: "http://localhost:8000/v1",
}

DEFAULT_MODELS = {
    PROVIDER_ANTHROPIC: "claude-sonnet-4-20250514",
    PROVIDER_OLLAMA: "llama3.2",
    PROVIDER_LMSTUDIO: "local-model",
    PROVIDER_NVIDIA: "meta/llama-3.1-70b-instruct",
    PROVIDER_OPENAI_ROUTER: "gpt-4o-mini",
}


@dataclass
class AIProviderConfig:
    provider: str = PROVIDER_ANTHROPIC
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    timeout_seconds: int = 90
    max_retries: int = 3
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: dict | None) -> "AIProviderConfig":
        raw = dict(raw or {})
        provider = str(raw.get("provider") or PROVIDER_ANTHROPIC)
        if provider not in ALL_PROVIDERS:
            provider = PROVIDER_ANTHROPIC
        return cls(
            provider=provider,
            base_url=str(raw.get("base_url") or DEFAULT_BASE_URLS.get(provider, "")),
            api_key=str(raw.get("api_key") or ""),
            model=str(raw.get("model") or DEFAULT_MODELS.get(provider, "")),
            timeout_seconds=int(raw.get("timeout_seconds") or 90),
            max_retries=int(raw.get("max_retries") or 3),
            extra=dict(raw.get("extra") or {}),
        )

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------
class AIProvider:
    """Abstract base class. Subclasses implement ``complete`` and ``health_check``."""

    label: str = "AIProvider"

    def __init__(self, config: AIProviderConfig) -> None:
        self.config = config
        # Cancellation primitives shared by all subclasses.
        self._cancelled: bool = False

    @property
    def name(self) -> str:
        return PROVIDER_LABELS.get(self.config.provider, self.config.provider)

    @property
    def model(self) -> str:
        return self.config.model

    def complete(self, system: str, user: str, *,
                 max_tokens: int = 8000, temperature: float = 0.2) -> str:
        raise NotImplementedError

    def health_check(self) -> bool:
        raise NotImplementedError

    # -- cancellation ----------------------------------------------------
    def cancel(self) -> None:
        """Best-effort abort of any in-flight request.

        Subclasses override to also close their HTTP client. The base
        implementation just sets a flag so retry loops can short-circuit.
        """
        self._cancelled = True
        AILogBus.instance().warn(
            "cancel", f"{self.name}: cancel requested by user")

    def reset_cancel(self) -> None:
        self._cancelled = False

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    # -- helpers ----------------------------------------------------------
    def _require_httpx(self) -> Any:
        if httpx is None:
            raise AIProviderError("httpx not installed (required for HTTP providers)")
        return httpx


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------
class AnthropicProvider(AIProvider):
    label = PROVIDER_LABELS[PROVIDER_ANTHROPIC]

    def __init__(self, config: AIProviderConfig) -> None:
        super().__init__(config)
        self._client: Any = None

    def _client_inst(self):
        if anthropic is None:
            raise AIProviderError("anthropic SDK not installed")
        if not self.config.api_key:
            raise AIProviderError("Anthropic API key not configured")
        if self._client is None:
            self._client = anthropic.Anthropic(api_key=self.config.api_key)
        return self._client

    def complete(self, system: str, user: str, *,
                 max_tokens: int = 8000, temperature: float = 0.2) -> str:
        bus = AILogBus.instance()
        if self._cancelled:
            raise AIProviderError("Cancelled before request")
        client = self._client_inst()
        model = self.config.model or DEFAULT_MODELS[PROVIDER_ANTHROPIC]
        bus.info("request",
                 f"→ Anthropic {model}  user={len(user)}B  system={len(system)}B  "
                 f"max_tokens={max_tokens}  temp={temperature:.2f}")
        bus.write_transcript("request", {
            "provider": "anthropic", "model": model,
            "max_tokens": max_tokens, "temperature": temperature,
            "system": system, "user": user,
        })
        t0 = time.monotonic()
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system,
                messages=[{"role": "user", "content": user}],
                timeout=self.config.timeout_seconds,
            )
        except _AnthropicAPIError as e:  # type: ignore[misc]
            bus.error("response", f"✕ Anthropic API error: {e}")
            raise AIProviderError(f"Anthropic API error: {e}") from e
        except Exception as e:  # noqa: BLE001
            if self._cancelled:
                bus.warn("cancel", "Anthropic request aborted")
                raise AIProviderError("Cancelled by user") from e
            bus.error("response", f"✕ Anthropic call failed: {e}")
            raise AIProviderError(f"Anthropic call failed: {e}") from e

        parts: list[str] = []
        for block in getattr(resp, "content", []) or []:
            t = getattr(block, "text", None)
            if t:
                parts.append(t)
        text = "\n".join(parts).strip()
        if not text:
            bus.error("response", "✕ Anthropic returned empty response")
            raise AIProviderError("Empty response from Anthropic")
        elapsed = time.monotonic() - t0
        bus.info("response",
                 f"← Anthropic {model}  bytes={len(text)}  "
                 f"elapsed={elapsed:.2f}s")
        bus.write_transcript("response", {
            "provider": "anthropic", "model": model,
            "elapsed_seconds": round(elapsed, 3),
            "response": text,
        })
        return text

    def cancel(self) -> None:
        super().cancel()
        # Best-effort close of the SDK's underlying httpx client.
        try:
            client = self._client
            if client is not None:
                inner = getattr(client, "_client", None)
                if inner is not None and hasattr(inner, "close"):
                    inner.close()
        except Exception:  # noqa: BLE001
            pass
        self._client = None

    def health_check(self) -> bool:
        return anthropic is not None and bool(self.config.api_key)


# ---------------------------------------------------------------------------
# OpenAI-compatible base (Ollama / LM Studio / NVIDIA / Router)
# ---------------------------------------------------------------------------
class _OpenAICompatibleProvider(AIProvider):
    """Shared logic for OpenAI-style ``/chat/completions`` endpoints."""

    requires_key: bool = False
    health_path: str = "/v1/models"
    chat_path: str = "/v1/chat/completions"

    def __init__(self, config: AIProviderConfig) -> None:
        super().__init__(config)
        self._active_client: Any = None

    def cancel(self) -> None:
        super().cancel()
        c = self._active_client
        if c is not None:
            try:
                c.close()
            except Exception:  # noqa: BLE001
                pass

    def _base(self) -> str:
        base = (self.config.base_url or "").rstrip("/")
        if not base:
            raise AIProviderError(f"{self.label}: base_url not configured")
        return base

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.config.api_key:
            h["Authorization"] = f"Bearer {self.config.api_key}"
        elif self.requires_key:
            raise AIProviderError(f"{self.label}: API key required")
        return h

    def complete(self, system: str, user: str, *,
                 max_tokens: int = 8000, temperature: float = 0.2) -> str:
        bus = AILogBus.instance()
        if self._cancelled:
            raise AIProviderError("Cancelled before request")
        h = self._require_httpx()
        url = self._base() + self.chat_path
        model = self.config.model or DEFAULT_MODELS.get(self.config.provider, "")
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        bus.info("request",
                 f"→ {self.name} POST {url}  model={model}  "
                 f"user={len(user)}B  system={len(system)}B  "
                 f"max_tokens={max_tokens}  temp={temperature:.2f}")
        bus.write_transcript("request", {
            "provider": self.config.provider, "model": model, "url": url,
            "max_tokens": max_tokens, "temperature": temperature,
            "system": system, "user": user,
        })
        t0 = time.monotonic()
        try:
            with h.Client(timeout=self.config.timeout_seconds) as client:
                self._active_client = client
                try:
                    resp = client.post(url, headers=self._headers(), json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                finally:
                    self._active_client = None
        except h.HTTPStatusError as e:
            bus.error("response",
                      f"✕ {self.name} HTTP {e.response.status_code}: "
                      f"{e.response.text[:160]}")
            raise AIProviderError(
                f"{self.label} HTTP {e.response.status_code}: {e.response.text[:200]}"
            ) from e
        except h.RequestError as e:
            if self._cancelled:
                bus.warn("cancel", f"{self.name} request aborted")
                raise AIProviderError("Cancelled by user") from e
            bus.error("response", f"✕ {self.name} request error: {e}")
            raise AIProviderError(f"{self.label}: {e}") from e
        except json.JSONDecodeError as e:
            bus.error("response", f"✕ {self.name} invalid JSON: {e}")
            raise AIProviderError(f"{self.label}: invalid JSON response: {e}") from e

        try:
            choices = data.get("choices") or []
            if not choices:
                raise KeyError("no choices")
            msg = choices[0].get("message") or {}
            text = (msg.get("content") or "").strip()
            if not text:
                raise KeyError("empty content")
            elapsed = time.monotonic() - t0
            bus.info("response",
                     f"← {self.name} {model}  bytes={len(text)}  "
                     f"elapsed={elapsed:.2f}s")
            bus.write_transcript("response", {
                "provider": self.config.provider, "model": model,
                "url": url, "elapsed_seconds": round(elapsed, 3),
                "response": text,
            })
            return text
        except (KeyError, TypeError) as e:
            bus.error("response",
                      f"✕ {self.name} malformed response shape ({e})")
            raise AIProviderError(f"{self.label}: malformed response shape ({e})") from e

    def health_check(self) -> bool:
        if httpx is None:
            return False
        for base in _candidate_bases(self.config.base_url):
            try:
                with httpx.Client(timeout=4.0) as client:
                    resp = client.get(base + self.health_path,
                                      headers=self._headers())
                if resp.status_code < 500:
                    return True
            except Exception:
                continue
        return False

    def list_models(self) -> list[str]:
        """Best-effort model discovery for UI auto-complete. Returns []."""
        if httpx is None:
            return []
        last_err: Optional[Exception] = None
        for base in _candidate_bases(self.config.base_url):
            url = base + self.health_path
            try:
                with httpx.Client(timeout=4.0) as client:
                    resp = client.get(url, headers=self._headers())
                    resp.raise_for_status()
                    data = resp.json()
                # OpenAI shape: {"data": [{"id": "..."}, ...]}
                if isinstance(data, dict) and "data" in data:
                    models = [str(m.get("id", "")).strip()
                              for m in data["data"] if m.get("id")]
                # Ollama shape: {"models":[{"name":"..."}]}
                elif isinstance(data, dict) and "models" in data:
                    models = [str(m.get("name", "")).strip()
                              for m in data["models"] if m.get("name")]
                else:
                    models = []
                if models:
                    # Cache the working base URL so future calls skip probing.
                    if base != self.config.base_url.rstrip("/"):
                        log.info("%s reachable via fallback %s", self.label, base)
                        self.config.base_url = base
                    return models
            except Exception as e:  # noqa: BLE001
                last_err = e
                log.debug("list_models %s failed: %s", url, e)
        if last_err is not None:
            log.debug("list_models exhausted candidates: %s", last_err)
        return []


class OllamaProvider(_OpenAICompatibleProvider):
    label = PROVIDER_LABELS[PROVIDER_OLLAMA]
    requires_key = False
    health_path = "/api/tags"


class LMStudioProvider(_OpenAICompatibleProvider):
    label = PROVIDER_LABELS[PROVIDER_LMSTUDIO]
    requires_key = False
    health_path = "/v1/models"


class NvidiaAIProvider(_OpenAICompatibleProvider):
    label = PROVIDER_LABELS[PROVIDER_NVIDIA]
    requires_key = True
    health_path = "/models"
    chat_path = "/chat/completions"


class OpenAIRouterProvider(_OpenAICompatibleProvider):
    label = PROVIDER_LABELS[PROVIDER_OPENAI_ROUTER]
    requires_key = False
    health_path = "/models"
    chat_path = "/chat/completions"


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
class AIProviderFactory:
    """Construct the right provider instance from a config object."""

    _registry: dict[str, type[AIProvider]] = {
        PROVIDER_ANTHROPIC: AnthropicProvider,
        PROVIDER_OLLAMA: OllamaProvider,
        PROVIDER_LMSTUDIO: LMStudioProvider,
        PROVIDER_NVIDIA: NvidiaAIProvider,
        PROVIDER_OPENAI_ROUTER: OpenAIRouterProvider,
    }

    @classmethod
    def register(cls, name: str, provider_cls: type[AIProvider]) -> None:
        """Register a custom provider (used by plugins)."""
        cls._registry[name] = provider_cls
        if name not in PROVIDER_LABELS:
            PROVIDER_LABELS[name] = getattr(provider_cls, "label", name)

    @classmethod
    def create(cls, config: AIProviderConfig) -> AIProvider:
        if config.provider not in cls._registry:
            raise AIProviderError(f"Unknown provider: {config.provider}")
        return cls._registry[config.provider](config)

    @classmethod
    def detect_available(cls, anthropic_key: str = "") -> list[str]:
        """Probe every provider; return those that look usable."""
        found: list[str] = []
        # Anthropic — heuristic only (don't burn API call)
        if anthropic is not None and anthropic_key:
            found.append(PROVIDER_ANTHROPIC)
        # Local
        for name in (PROVIDER_OLLAMA, PROVIDER_LMSTUDIO):
            try:
                cfg = AIProviderConfig(
                    provider=name,
                    base_url=DEFAULT_BASE_URLS[name],
                    model=DEFAULT_MODELS[name],
                )
                if cls.create(cfg).health_check():
                    found.append(name)
            except Exception:  # noqa: BLE001
                continue
        return found


__all__ = [
    "AIProvider", "AIProviderConfig", "AIProviderError", "AIProviderFactory",
    "AIProviderUnavailable",
    "AnthropicProvider", "OllamaProvider", "LMStudioProvider",
    "NvidiaAIProvider", "OpenAIRouterProvider",
    "PROVIDER_ANTHROPIC", "PROVIDER_OLLAMA", "PROVIDER_LMSTUDIO",
    "PROVIDER_NVIDIA", "PROVIDER_OPENAI_ROUTER",
    "ALL_PROVIDERS", "PROVIDER_LABELS", "DEFAULT_BASE_URLS", "DEFAULT_MODELS",
    "is_wsl", "windows_host_ip",
]


# Public aliases so the UI can show "Resolved Windows host: 172.x.x.x".
is_wsl = _is_wsl
windows_host_ip = _windows_host_ip
