"""
Multi-provider HTTP LLM client using httpx (Gemini, OpenAI-compatible, Ollama)
with safe environment discovery and deterministic offline fallback.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field


def load_local_dotenv(env_path: Path | None = None) -> bool:
    """
    Load KEY=VALUE pairs from a local `.env` file using `os.environ.setdefault`
    (skipped automatically under PyTest so unit tests stay isolated).
    """
    if "PYTEST_CURRENT_TEST" in os.environ:
        return False

    if env_path is not None:
        target = env_path
    else:
        cwd_env = Path.cwd() / ".env"
        repo_env = Path(__file__).resolve().parents[3] / ".env"
        target = cwd_env if cwd_env.is_file() else repo_env
    if not target.is_file():
        return False

    for raw_line in target.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        val = value.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
            val = val[1:-1]
        if val:
            os.environ.setdefault(key, val)
    return True


class LLMConfig(BaseModel):
    """Runtime configuration for optional multi-provider LLM inference."""

    model_config = ConfigDict(frozen=True)

    provider: Literal["auto", "groq", "gemini", "openai", "ollama", "deterministic"] = "auto"
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    timeout_seconds: float = Field(default=15.0, ge=1.0, le=60.0)


class LLMCompletionResult(BaseModel):
    """Structured output wrapper returned by MultiProviderLLMClient."""

    model_config = ConfigDict(frozen=True)

    text: str = ""
    provider: str = "deterministic"
    model: str = "deterministic-offline"
    used_live_llm: bool = False
    latency_ms: float = 0.0
    fallback_reason: str | None = None


class MultiProviderLLMClient:
    """
    Lightweight, zero-SDK HTTP LLM client powered by `httpx`.
    Auto-selects Gemini, OpenAI/compatible, or local Ollama when configured via env vars,
    and degrades gracefully to deterministic fallback when unconfigured or unreachable.
    """

    _DEFAULT_MODELS: dict[str, str] = {
        "groq": "openai/gpt-oss-20b",
        "gemini": "gemini-2.5-flash",
        "openai": "gpt-4o-mini",
        "ollama": "llama3.1",
        "deterministic": "deterministic-offline",
    }

    def __init__(
        self,
        config: LLMConfig | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.config = config or LLMConfig()
        self._injected_http = http_client

    def resolve_provider(self, provider_override: str | None = None) -> tuple[str, str, str | None, str]:
        """
        Resolve `(provider, model, api_key, base_url)` without exposing secrets.
        Precedence: `provider_override` -> `config.provider` -> `ASCI_LLM_PROVIDER` -> env auto-detect.
        """
        raw_pref = (
            provider_override
            or (self.config.provider if self.config.provider != "auto" else None)
            or os.environ.get("ASCI_LLM_PROVIDER")
            or "auto"
        ).strip().lower()

        groq_key = self.config.api_key if raw_pref == "groq" else None
        groq_key = groq_key or os.environ.get("GROQ_API_KEY")
        groq_base = (
            (self.config.base_url if raw_pref == "groq" else None)
            or os.environ.get("GROQ_BASE_URL")
            or "https://api.groq.com/openai/v1"
        ).rstrip("/")

        gemini_key = self.config.api_key if raw_pref == "gemini" else None
        gemini_key = gemini_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

        openai_key = self.config.api_key if raw_pref == "openai" else None
        openai_key = openai_key or os.environ.get("OPENAI_API_KEY")
        openai_base = (
            (self.config.base_url if raw_pref == "openai" else None)
            or os.environ.get("OPENAI_BASE_URL")
            or "https://api.openai.com/v1"
        ).rstrip("/")

        ollama_host = (
            (self.config.base_url if raw_pref == "ollama" else None)
            or os.environ.get("OLLAMA_HOST")
            or ""
        ).rstrip("/")

        if raw_pref == "auto":
            if groq_key:
                provider = "groq"
            elif gemini_key:
                provider = "gemini"
            elif openai_key:
                provider = "openai"
            elif ollama_host or os.environ.get("ASCI_OLLAMA_ENABLED", "").lower() in ("1", "true", "yes"):
                provider = "ollama"
            else:
                provider = "deterministic"
        elif raw_pref in ("groq", "gemini", "openai", "ollama", "deterministic"):
            provider = raw_pref
        else:
            provider = "deterministic"

        model_env = os.environ.get("ASCI_LLM_MODEL")
        model = self.config.model or model_env or self._DEFAULT_MODELS[provider]

        if provider == "groq":
            if not groq_key:
                return "deterministic", self._DEFAULT_MODELS["deterministic"], None, ""
            return "groq", model, groq_key, groq_base

        if provider == "gemini":
            if not gemini_key:
                return "deterministic", self._DEFAULT_MODELS["deterministic"], None, ""
            base = (self.config.base_url or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
            return "gemini", model, gemini_key, base

        if provider == "openai":
            if not openai_key and openai_base == "https://api.openai.com/v1":
                return "deterministic", self._DEFAULT_MODELS["deterministic"], None, ""
            return "openai", model, openai_key, openai_base

        if provider == "ollama":
            resolved_ollama = ollama_host or "http://localhost:11434"
            return "ollama", model, None, resolved_ollama

        return "deterministic", self._DEFAULT_MODELS["deterministic"], None, ""

    def get_status(self, provider_override: str | None = None) -> dict[str, Any]:
        """Return safe runtime capability metadata (never exposes API keys)."""
        provider, model, _, base_url = self.resolve_provider(provider_override=provider_override)
        return {
            "configured": provider != "deterministic",
            "active_provider": provider,
            "model": model,
            "mode": "live_llm" if provider != "deterministic" else "deterministic_offline",
            "endpoint": base_url if provider == "ollama" else None,
            "supported_providers": ["groq", "gemini", "openai", "ollama", "deterministic"],
        }

    def _run_http_post(self, url: str, *, json_body: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        if self._injected_http is not None:
            resp = self._injected_http.post(
                url,
                json=json_body,
                headers=headers,
                timeout=self.config.timeout_seconds,
            )
            resp.raise_for_status()
            return dict(resp.json())

        with httpx.Client(timeout=self.config.timeout_seconds) as client:
            resp = client.post(url, json=json_body, headers=headers)
            resp.raise_for_status()
            return dict(resp.json())

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        json_mode: bool = False,
        temperature: float = 0.0,
        provider_override: str | None = None,
    ) -> LLMCompletionResult:
        """
        Execute a stateless completion against the resolved provider.
        Returns `used_live_llm=False` cleanly on unconfigured or failed HTTP calls.
        """
        t0 = time.perf_counter()
        provider, model, api_key, base_url = self.resolve_provider(provider_override=provider_override)

        if provider == "deterministic":
            return LLMCompletionResult(
                text="",
                provider="deterministic",
                model=model,
                used_live_llm=False,
                latency_ms=round((time.perf_counter() - t0) * 1000.0, 2),
                fallback_reason="No external LLM API key or Ollama host configured; using deterministic engine.",
            )

        try:
            if provider == "gemini":
                url = f"{base_url}/models/{model}:generateContent?key={api_key}"
                gen_cfg: dict[str, Any] = {"temperature": temperature}
                if json_mode:
                    gen_cfg["responseMimeType"] = "application/json"
                payload: dict[str, Any] = {
                    "systemInstruction": {"parts": [{"text": system_prompt}]},
                    "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
                    "generationConfig": gen_cfg,
                }
                data = self._run_http_post(
                    url,
                    json_body=payload,
                    headers={"Content-Type": "application/json"},
                )
                candidates = data.get("candidates") or []
                parts = (candidates[0].get("content") or {}).get("parts") or [] if candidates else []
                text = "".join(str(p.get("text", "")) for p in parts).strip()

            elif provider in ("openai", "groq"):
                url = f"{base_url}/chat/completions"
                payload = {
                    "model": model,
                    "temperature": temperature,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                }
                if json_mode:
                    payload["response_format"] = {"type": "json_object"}
                headers = {"Content-Type": "application/json"}
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"
                data = self._run_http_post(url, json_body=payload, headers=headers)
                choices = data.get("choices") or []
                msg = choices[0].get("message") or {} if choices else {}
                text = str(msg.get("content", "")).strip()

            elif provider == "ollama":
                url = f"{base_url}/api/chat"
                payload = {
                    "model": model,
                    "stream": False,
                    "options": {"temperature": temperature},
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                }
                if json_mode:
                    payload["format"] = "json"
                data = self._run_http_post(
                    url,
                    json_body=payload,
                    headers={"Content-Type": "application/json"},
                )
                msg = data.get("message") or {}
                text = str(msg.get("content", "")).strip()

            else:
                text = ""

            latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            if not text:
                return LLMCompletionResult(
                    text="",
                    provider=provider,
                    model=model,
                    used_live_llm=False,
                    latency_ms=latency_ms,
                    fallback_reason=f"Provider '{provider}' returned an empty completion.",
                )

            return LLMCompletionResult(
                text=text,
                provider=provider,
                model=model,
                used_live_llm=True,
                latency_ms=latency_ms,
            )

        except Exception as exc:
            return LLMCompletionResult(
                text="",
                provider=provider,
                model=model,
                used_live_llm=False,
                latency_ms=round((time.perf_counter() - t0) * 1000.0, 2),
                fallback_reason=f"LLM request failed ({type(exc).__name__}); reverted to deterministic fallback.",
            )

