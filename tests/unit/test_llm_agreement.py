"""Unit tests for ``agreement_flag`` — the 3-state ML↔LLM agreement (AI-06).

Pinned tests: ``agree`` when the verdict matches the ML direction above the
confidence floor; ``disagree`` when the verdict opposes the ML direction above
the floor; ``unclear`` when the confidence is below the floor; and an NA /
NaN ``p_win`` path that yields ``unclear`` (NA-safe).
"""

from __future__ import annotations

import pytest
from _llm_fixtures import llm_cfg

from ai_trading.llm.agreement import agreement_flag


@pytest.mark.unit
def test_agree_when_verdict_matches_ml_direction():
    cfg = llm_cfg(llm_agree_min_confidence=0.6)
    # p_win 0.72 => ML direction "confirm"; confirm + high confidence => agree.
    agreement, confidence = agreement_flag("confirm", 0.8, 0.72, cfg)
    assert agreement == "agree"
    assert confidence == pytest.approx(0.8)


@pytest.mark.unit
def test_disagree_when_verdict_opposes_ml_direction():
    cfg = llm_cfg(llm_agree_min_confidence=0.6)
    # p_win 0.72 => ML direction "confirm"; refute opposes => disagree.
    agreement, confidence = agreement_flag("refute", 0.8, 0.72, cfg)
    assert agreement == "disagree"
    assert confidence == pytest.approx(0.8)


@pytest.mark.unit
def test_unclear_below_confidence_floor():
    cfg = llm_cfg(llm_agree_min_confidence=0.6)
    agreement, confidence = agreement_flag("confirm", 0.4, 0.72, cfg)
    assert agreement == "unclear"
    assert confidence == pytest.approx(0.4)


@pytest.mark.unit
def test_na_pwin_unclear():
    cfg = llm_cfg(llm_agree_min_confidence=0.6)
    agreement, _ = agreement_flag("confirm", 0.9, float("nan"), cfg)
    assert agreement == "unclear"
    # pandas-missing NA also yields unclear.
    agreement_na, _ = agreement_flag("confirm", 0.9, None, cfg)
    assert agreement_na == "unclear"
