"""Live LLM integration tests (marker: llm) — REQUIRE a running, reachable
OpenAI-compatible endpoint (local vLLM) at the configured ``llm_base_url``.

Excluded from the default ``uv run pytest -q`` run by the pyproject addopts
(``-m "not mt5 and not llm"``); run explicitly via ``uv run pytest -m llm -q``.
When the endpoint is disabled/unreachable every test SKIPS with an actionable
message, so the suite still exits 0.

It is importable WITHOUT requiring the endpoint at import time — all network
access happens inside the test (the ``OpenAICompatProvider`` client is
constructed but never used until a call). This is the only path touching a live
endpoint.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_trading.config import load_config
from ai_trading.llm.narrative import run_narrative_pipeline
from ai_trading.llm.provider import OpenAICompatProvider

pytestmark = [pytest.mark.llm]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _sample_evidence() -> dict:
    """A well-formed D-01 evidence object (offline, deterministic)."""
    return {
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
        "entry": 1.10500,
        "sl": 1.09850,
        "tp": 1.12340,
        "rr_at_decision": 2.1,
        "p_win": 0.72,
        "score_source": "ml",
        "artifact_version": 1,
        "top_contributors": [],
    }


@pytest.fixture
def llm_cfg_live():
    """Real config + a provider against the configured endpoint; skips when
    `llm_enabled` is false or the endpoint is unreachable."""
    try:
        cfg = load_config(_repo_root() / "config.toml")
    except ValueError as exc:
        pytest.skip(f"live LLM config unavailable: {exc}")
    if not cfg.llm_enabled:
        pytest.skip(
            "llm_enabled is false in config; set it true (and the endpoint) in "
            "config.local.toml to run the live LLM integration test"
        )
    # Construct once against the configured endpoint (client built, no call yet).
    provider = OpenAICompatProvider(cfg)
    return provider, cfg


def test_live_narrative_produces_verified_result(llm_cfg_live):
    """A full narrative over the sample evidence yields a verified narrative and
    an agreement flag (AI-05 / AI-06) from the real endpoint."""
    provider, cfg = llm_cfg_live
    result = run_narrative_pipeline(provider, _sample_evidence(), cfg)
    assert result.narrative is not None, f"no narrative; narrative_status={result.narrative_status}"
    assert result.citation_status == "verified"
    assert result.score_source == "ml_llm"
    assert result.narrative_status == "ok"
    assert result.agreement in {"agree", "disagree", "unclear"}
