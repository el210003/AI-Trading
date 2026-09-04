"""Unit tests for ``run_narrative_pipeline`` graceful fallback (AI-07 / SC3).

Pinned tests: a provider ``TimeoutError`` → complete ML-only setup (narrative /
agreement None, ``score_source="ml"``, ``narrative_status="llm_unavailable"``,
``reason="timeout"``) bounded in wall-clock; a truncated (content=None /
``LLMTruncatedError``) path retries once then falls back or succeeds; an
unverified citation discards the narrative (``narrative_status="citation_rejected"``);
and ``llm_enabled=False`` short-circuits to ML-only with NO provider call. All
offline — no live endpoint.
"""

from __future__ import annotations

import json
import time

import pytest
from _llm_fixtures import FakeLLMProvider, llm_cfg, make_evidence

from ai_trading.llm.narrative import run_narrative_pipeline
from ai_trading.llm.provider import LLMTruncatedError


def _good_narrative_json() -> str:
    """A narrative that passes schema validation AND the citation check against
    ``make_evidence`` (direction=long, bias bullish)."""
    return json.dumps(
        {
            "verdict": "confirm",
            "confidence": 0.8,
            "reasoning": "The long direction with bullish bias supports a confirm",
            "citations": ["direction", "bias_h1"],
        }
    )


@pytest.mark.unit
def test_timeout_emits_ml_only_setup():
    # A PERSISTENT timeout (across the pipeline's 1-retry window) degrades to a
    # complete ML-only result with reason="timeout". (A single transient-timeout
    # provider is intentionally retried once by the pipeline — see the tolerant
    # reasoning-model retry in narrative.py.)
    provider = FakeLLMProvider(errors=[TimeoutError(), TimeoutError()])
    result = run_narrative_pipeline(provider, make_evidence(), llm_cfg(llm_enabled=True))
    assert result.narrative is None
    assert result.agreement is None
    assert result.agreement_confidence is None
    assert result.score_source == "ml"
    assert result.narrative_status == "llm_unavailable"
    assert result.reason == "timeout"
    assert result.p_win == pytest.approx(0.72)


@pytest.mark.unit
def test_fallback_bounded_time():
    provider = FakeLLMProvider(errors=[TimeoutError(), TimeoutError()])
    start = time.perf_counter()
    run_narrative_pipeline(provider, make_evidence(), llm_cfg(llm_enabled=True))
    elapsed = time.perf_counter() - start
    assert elapsed < 2.0, f"fallback not bounded in wall-clock: {elapsed:.3f}s"


@pytest.mark.unit
def test_truncated_retried_then_success():
    provider = FakeLLMProvider(
        errors=[LLMTruncatedError("truncated on first attempt")],
        responses=[_good_narrative_json()],
    )
    result = run_narrative_pipeline(provider, make_evidence(), llm_cfg(llm_enabled=True))
    assert result.narrative is not None
    assert result.score_source == "ml_llm"
    assert result.narrative_status == "ok"
    assert result.citation_status == "verified"
    assert result.agreement == "agree"
    assert len(provider.calls) == 2  # one retry happened


@pytest.mark.unit
def test_truncated_then_fallback_after_retry():
    provider = FakeLLMProvider(
        errors=[LLMTruncatedError("first"), LLMTruncatedError("retry also truncated")]
    )
    result = run_narrative_pipeline(provider, make_evidence(), llm_cfg(llm_enabled=True))
    assert result.narrative is None
    assert result.score_source == "ml"
    assert result.narrative_status == "llm_unavailable"


@pytest.mark.unit
def test_citation_unverified_discard():
    # Citing a forbidden level field => dropped => unverified => discard.
    payload = json.dumps(
        {
            "verdict": "confirm",
            "confidence": 0.8,
            "reasoning": "the price references the entry level",
            "citations": ["entry"],
        }
    )
    provider = FakeLLMProvider(responses=[payload])
    result = run_narrative_pipeline(provider, make_evidence(), llm_cfg(llm_enabled=True))
    assert result.narrative is None
    assert result.citation_status == "unverified"
    assert result.score_source == "ml"
    assert result.narrative_status == "citation_rejected"
    assert result.reason == "unverified_citation"


@pytest.mark.unit
def test_llm_disabled_short_circuits_without_provider_call():
    provider = FakeLLMProvider()  # raises AssertionError if build_narrative called
    result = run_narrative_pipeline(provider, make_evidence(), llm_cfg(llm_enabled=False))
    assert result.narrative is None
    assert result.score_source == "ml"
    assert result.narrative_status == "llm_unavailable"
    assert provider.calls == []  # provider never invoked
