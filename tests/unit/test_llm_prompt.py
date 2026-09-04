"""Unit tests for ``build_prompt`` (D-03): the prompt is built STRICTLY from the
evidence object's field projection — no raw OHLC/candle keys, no level values
(reference-only level fields are stripped via ``FORBIDDEN_LEVEL_KEYS``), and
nothing outside the passed evidence dict. No network / no MT5.
"""

from __future__ import annotations

import json

import pytest
from _llm_fixtures import make_evidence

from ai_trading.llm.prompt import build_prompt
from ai_trading.llm.schema import FORBIDDEN_LEVEL_KEYS


def _projection(evidence: dict) -> dict:
    """Extract the serialized JSON evidence projection build_prompt embeds in
    the user message (the object after the intro line)."""
    system, user = build_prompt(evidence)
    text = user[0]["content"]
    after = text.split("fields only:\n", 1)[1]
    return json.loads(after)


@pytest.mark.unit
def test_prompt_contains_evidence_fields():
    evidence = make_evidence()
    system, user = build_prompt(evidence)
    assert isinstance(system, list) and isinstance(user, list)
    text = user[0]["content"]
    for key in ("symbol", "direction", "zone_id", "p_win", "bias_h1", "score_source"):
        assert key in text
        assert str(evidence[key]) in text


@pytest.mark.unit
def test_prompt_has_no_ohlc_or_candle_keys():
    """No raw OHLC/candle field may appear as a projection key (D-03)."""
    evidence = make_evidence()
    projection = _projection(evidence)
    for key in ("open", "high", "low", "close", "candle", "ohlc"):
        assert key not in projection


@pytest.mark.unit
def test_prompt_strips_level_values():
    """The reference-only level fields in the evidence object must NOT reach
    the prompt (D-02/D-03): no level key and no level value survives."""
    evidence = make_evidence()
    system, user = build_prompt(evidence)
    projection = _projection(evidence)
    for key in FORBIDDEN_LEVEL_KEYS:
        assert key not in projection
        # the level value itself (e.g. the SL price literal) must not appear.
        value = evidence.get(key)
        if value is not None:
            assert str(value) not in user[0]["content"]


@pytest.mark.unit
def test_prompt_only_uses_passed_evidence():
    """The builder never reaches for data outside the passed evidence dict: an
    evidence object with an extra field is serialized, and a level field added
    to the evidence is stripped — never fabricated."""
    evidence = make_evidence(extra_field="something", tp=9.999)
    system, user = build_prompt(evidence)
    projection = _projection(evidence)
    assert "extra_field" in projection
    assert "tp" not in projection
    assert "9.999" not in user[0]["content"]
