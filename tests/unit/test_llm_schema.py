"""Unit tests for the structured-output contract (D-02/D-04).

Verifies ``LLMNarrative``'s verdict-enum / confidence-bound / non-empty-reasoning
validation, the ``FORBIDDEN_LEVEL_KEYS`` schema guard, and the strict
``json_schema`` response_format builder (single source of truth = the pydantic
model). No network / no MT5 anywhere.
"""

from __future__ import annotations

import pytest

from ai_trading.llm.schema import (
    ALLOWED_CITATION_KEYS,
    FORBIDDEN_LEVEL_KEYS,
    LLMNarrative,
    narrative_response_format,
)


@pytest.mark.unit
def test_verdict_accepts_both_values():
    for verdict in ("confirm", "refute"):
        narrative = LLMNarrative(
            verdict=verdict,
            confidence=0.7,
            reasoning="sweep + mitigated zone",
            citations=["zone_id"],
        )
        assert narrative.verdict == verdict


@pytest.mark.unit
def test_verdict_rejects_outside_enum_naming_field():
    with pytest.raises(ValueError) as exc:
        LLMNarrative(verdict="maybe", confidence=0.7, reasoning="r", citations=[])
    assert "verdict" in str(exc.value)


@pytest.mark.unit
@pytest.mark.parametrize("confidence", [-0.1, 1.5])
def test_confidence_rejects_outside_bounds_naming_field(confidence):
    with pytest.raises(ValueError) as exc:
        LLMNarrative(verdict="confirm", confidence=confidence, reasoning="r", citations=[])
    assert "confidence" in str(exc.value)


@pytest.mark.unit
def test_reasoning_requires_non_empty():
    with pytest.raises(ValueError) as exc:
        LLMNarrative(verdict="confirm", confidence=0.7, reasoning="", citations=[])
    assert "reasoning" in str(exc.value)


@pytest.mark.unit
def test_forbidden_level_keys_guard():
    assert {"entry", "sl", "tp", "sl_price", "tp_price", "entry_price"} <= FORBIDDEN_LEVEL_KEYS
    # A level field can never be a legal citation target (D-02 / SC1).
    assert not (ALLOWED_CITATION_KEYS & FORBIDDEN_LEVEL_KEYS)


@pytest.mark.unit
def test_response_format_is_strict_json_schema_matching_model():
    rf = narrative_response_format()
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["strict"] is True
    assert rf["json_schema"]["name"] == "LLMNarrative"
    schema = rf["json_schema"]["schema"]
    assert set(schema["properties"]) == {"verdict", "confidence", "reasoning", "citations"}
    assert schema["properties"]["verdict"]["enum"] == ["confirm", "refute"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"verdict", "confidence", "reasoning", "citations"}
