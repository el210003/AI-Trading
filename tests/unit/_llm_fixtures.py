"""Phase-5 LLM test fixtures — local helper built over the existing
``_backtest_fixtures`` / ``_ml_fixtures`` config-constructor chain (direct
import, never extended).

Helpers:
- ``FakeLLMProvider``: duck-typed ``LLMProvider`` double (mirrors ``conftest.py``
  ``FakeMT5Client``) — FIFO-scripts raw JSON responses and exceptions (e.g.
  ``TimeoutError`` to force the AI-07 fallback), records every call.
- ``llm_cfg``: frozen Config carrying the Phase-5 ``llm_*`` defaults so LLM
  tests never depend on ``load_config`` or files on disk.
- ``make_evidence``: deterministic sample evidence object dict (keys matching
  ``ALLOWED_CITATION_KEYS`` plus the reference-only level fields, for the
  citation/schema and prompt tests).

All helpers return new structures / never mutate inputs.
"""

from __future__ import annotations

from typing import Any

from _ml_fixtures import ml_cfg

__all__ = ["FakeLLMProvider", "llm_cfg", "make_evidence"]


def llm_cfg(**overrides) -> Any:
    """Frozen Config carrying the Phase-5 ``llm_*`` defaults (and all Phase-4
    ``ml_*`` / Phase-3 backtest defaults) via ``_ml_fixtures.ml_cfg``; pass
    keyword overrides per test (never touches ``load_config``)."""
    defaults = {
        "llm_enabled": False,
        "llm_base_url": "http://192.168.5.178:8000/v1",
        "llm_model": "deepseek-v4-flash-vision-exp",
        "llm_api_key": "",
        "llm_timeout_ms": 8000,
        "llm_max_tokens": 2048,
        "llm_top_n_contributors": 5,
        "llm_structured_mode": "json_schema",
        "llm_agree_min_confidence": 0.6,
        "llm_max_retries": 1,
    }
    return ml_cfg(**{**defaults, **overrides})


class FakeLLMProvider:
    """Test double for ``LLMProvider`` — scripted responses / scripted errors.

    Constructor takes ``responses`` (FIFO of raw JSON strings) and ``errors``
    (FIFO of exceptions, e.g. ``TimeoutError``). ``calls`` records every
    ``(evidence, response_schema)``. ``build_narrative`` pops an error first
    (raising it), else a response; ``AssertionError`` when no scripted response
    remains.
    """

    def __init__(self, responses=None, errors=None):
        self.responses = list(responses or [])
        self.errors = list(errors or [])
        self.calls: list[tuple[dict, dict]] = []

    def build_narrative(self, evidence, response_schema, *, cfg):
        self.calls.append((evidence, response_schema))
        if self.errors:
            raise self.errors.pop(0)
        if not self.responses:
            raise AssertionError("no scripted response for FakeLLMProvider")
        return self.responses.pop(0)


def make_evidence(**overrides) -> dict:
    """Deterministic sample evidence object: keys matching
    ``ALLOWED_CITATION_KEYS`` plus the reference-only level fields (D-01) used
    by the citation/schema and prompt tests. Values are scalars."""
    evidence: dict = {
        "symbol": "EURUSD",
        "timeframe": "M15",
        "direction": "long",
        "zone_id": "z-001",
        "zone_state": "mitigated",
        "event_id": "ev-001",
        "pool_id": "p-001",
        "sweep_side": "low",
        "bias_h1": "bullish",
        "bias_h4": "bullish",
        "p_win": 0.72,
        "score_source": "ml",
        "artifact_version": 1,
        "rr_at_decision": 2.1,
        # Reference-only level fields (D-01) — NOT legal citation targets.
        "entry": 1.10500,
        "sl": 1.09850,
        "tp": 1.12340,
        "sl_price": 1.09850,
        "tp_price": 1.12340,
    }
    evidence.update(overrides)
    return evidence
