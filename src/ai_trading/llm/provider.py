"""LLM provider adapter — the ONLY module in the codebase that imports the
openai SDK (exactly once, at module top), mirroring ``mt5_client.py``'s
"only module that imports the SDK" discipline. Every other module goes through
the ``LLMProvider`` interface; tests inject a ``FakeLLMProvider`` exposing the
same surface (tests/unit/_llm_fixtures.py).

Importing this module does NOT connect to any endpoint — the client is built
ONCE in ``__init__`` from config (no per-call construction; RESEARCH line 105)
and the first network access happens lazily on a call.

Error taxonomy mirrors ``mt5_client.py`` (distinct ``RuntimeError`` subclasses):

- ``LLMProviderError`` — any provider/endpoint failure (connection, HTTP,
  timeout, malformed response).
- ``LLMTruncatedError`` — the reasoning model returned ``content is None``
  (token budget consumed by chain-of-thought, ``finish_reason="length"``;
  RESEARCH Pitfall 1). Read as a retry/fallback trigger, never a parse crash.

The ``response_format`` is gated behind ``cfg.llm_structured_mode`` (RESEARCH
Pitfall 4 — some serving stacks reject ``json_schema``); pydantic re-validation
remains the authority regardless.
"""

from __future__ import annotations

import json
import re
import time as _time
from typing import Protocol

from openai import OpenAI

from ai_trading.llm.prompt import build_prompt


class LLMProviderError(RuntimeError):
    """Provider/endpoint failure (connection, HTTP, timeout, malformed response)."""


class LLMTruncatedError(LLMProviderError):
    """The reasoning model returned ``content=None`` (token budget exhausted by
    chain-of-thought; ``finish_reason="length"``). Retry/fallback, never a parse
    crash (RESEARCH Pitfall 1)."""


_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.DOTALL)


def _extract_json_payload(content: str) -> str:
    """Return the JSON payload from model content, tolerating reasoning-model
    wrappers. Guided-decoding stacks (vLLM ``json_schema``) return pure JSON;
    cloud reasoning models (MiniMax-M3, observed 2026-09-05) may emit
    chain-of-thought prose around a markdown-fenced JSON block. Pure-JSON
    content passes through untouched; otherwise the fenced block — failing
    that the outermost brace span — is extracted and must parse as JSON,
    else the response is malformed (``LLMProviderError``)."""
    try:
        json.loads(content)
        return content
    except ValueError:
        pass
    match = _FENCE_RE.search(content)
    candidate = (
        match.group(1) if match else content[content.find("{"): content.rfind("}") + 1]
    )
    try:
        json.loads(candidate)
    except ValueError as exc:
        raise LLMProviderError(
            f"no JSON payload in LLM content ({exc}); raw head: {content[:120]!r}"
        ) from exc
    return candidate


class LLMProvider(Protocol):
    """Duck-typed provider interface: return the raw JSON string for the
    structured narrative given the evidence object. Both ``OpenAICompatProvider``
    and the test ``FakeLLMProvider`` implement this exact surface."""

    def build_narrative(self, evidence: dict, response_schema: dict, *, cfg) -> str:
        """Return the raw JSON string for the structured narrative."""
        ...


class OpenAICompatProvider:
    """OpenAI-compatible provider wrapping the openai SDK pointed at a local /
    custom endpoint (``base_url``). The client is constructed ONCE in
    ``__init__`` from config and reused across calls."""

    def __init__(self, cfg):
        self._client = OpenAI(
            api_key=cfg.llm_api_key,
            base_url=cfg.llm_base_url,
            timeout=cfg.llm_timeout_ms / 1000,
            max_retries=cfg.llm_max_retries,
        )

    def build_narrative(self, evidence: dict, response_schema: dict, *, cfg) -> str:
        """Call ``chat.completions.create`` with the config-mapped params and
        return the raw JSON string.

        ``response_format`` is gated behind ``cfg.llm_structured_mode``:
        ``json_schema`` passes the strict ``response_schema``; ``json_object``
        passes ``{"type": "json_object"}``; ``none`` omits it. A
        ``content=None`` result (reasoning-model truncation) raises
        ``LLMTruncatedError`` — never a parse crash.
        """
        system, user = build_prompt(evidence)
        messages = [*system, *user]
        kwargs = {
            "model": cfg.llm_model,
            "messages": messages,
            "max_tokens": cfg.llm_max_tokens,
        }
        if cfg.llm_structured_mode == "json_schema":
            kwargs["response_format"] = response_schema
        elif cfg.llm_structured_mode == "json_object":
            kwargs["response_format"] = {"type": "json_object"}
        # mode == "none": omit response_format entirely.

        resp = self._client.chat.completions.create(**kwargs)
        content = resp.choices[0].message.content
        if content is None:
            raise LLMTruncatedError(
                "LLM returned content=None (reasoning-model token budget exhausted — "
                "finish_reason likely 'length'); treat as retry/fallback"
            )
        return _extract_json_payload(content)


def probe_endpoint(base_url: str, api_key: str, model: str, timeout_s: float = 20.0) -> dict:
    """One-shot endpoint probe for the settings panel (SEED-004): list the
    served model ids and time a minimal chat call against ``model``.

    Never raises — network/HTTP failures land in ``error`` and ``ok=False``.
    Returns ``{ok, models, chat_ok, latency_ms, error}`` where ``models`` is
    the served id list (the authority for the configured ``llm_model``).
    """
    result: dict = {"ok": False, "models": [], "chat_ok": False, "latency_ms": None, "error": None}
    try:
        client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout_s, max_retries=0)
        listed = client.models.list()
        result["models"] = sorted(str(m.id) for m in listed.data)
    except Exception as exc:  # noqa: BLE001 — probe reports, never raises
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result
    try:
        t0 = _time.monotonic()
        client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Reply with the single word: ok"}],
            max_tokens=2048,
        )
        result["latency_ms"] = int((_time.monotonic() - t0) * 1000)
        result["chat_ok"] = True
    except Exception as exc:  # noqa: BLE001 — probe reports, never raises
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result
    result["ok"] = True
    return result
