"""Unit tests for ``citation_check`` — the strict D-02/D-05/SC1 guard.

Pinned tests: a citation of a FORBIDDEN_LEVEL_KEYS field (entry/sl/tp) is in
``dropped`` and drives ``unverified``; a key not in the evidence object is
``unknown`` and drives ``unverified``; a cited scalar enum value that
contradicts the evidence is a ``mismatch`` and drives ``unverified``; and a
narrative whose citations are all real, non-level and value-consistent is
``verified``.
"""

from __future__ import annotations

import pytest
from _llm_fixtures import make_evidence

from ai_trading.llm.citations import citation_check
from ai_trading.llm.schema import LLMNarrative


def _narrative(citations, reasoning: str = "evidence-grounded reasoning") -> LLMNarrative:
    return LLMNarrative(
        verdict="confirm", confidence=0.8, reasoning=reasoning, citations=citations
    )


@pytest.mark.unit
def test_level_field_dropped():
    evidence = make_evidence()
    narrative = _narrative(["entry", "sl", "tp"], "structurally referenced levels")
    result = citation_check(narrative, evidence)
    assert set(result["dropped"]) == {"entry", "sl", "tp"}
    assert result["status"] == "unverified"


@pytest.mark.unit
def test_unknown_citation_unverified():
    evidence = make_evidence()
    narrative = _narrative(["invented_field"], "a field the model never saw")
    result = citation_check(narrative, evidence)
    assert result["unknown"] == ["invented_field"]
    assert result["status"] == "unverified"


@pytest.mark.unit
def test_value_mismatch_unverified():
    evidence = make_evidence(direction="long")
    # Reasoning asserts a DIFFERENT direction value than the evidence.
    narrative = _narrative(["direction"], "The short direction favours a refute")
    result = citation_check(narrative, evidence)
    assert result["mismatch"] == ["direction"]
    assert result["status"] == "unverified"


@pytest.mark.unit
def test_valid_citations_verified():
    evidence = make_evidence(direction="long", bias_h1="bullish", bias_h4="bullish")
    narrative = _narrative(
        ["direction", "bias_h1", "p_win"],
        "The long direction with bullish H1 bias supports a confirm; p_win is high",
    )
    result = citation_check(narrative, evidence)
    assert result["status"] == "verified"
    assert result["dropped"] == []
    assert result["unknown"] == []
    assert result["mismatch"] == []


# ---------------------------------------------------------------------------
# Dotted nested paths (reasoning models cite zone.state / sweep.side —
# observed MiniMax-M3 2026-09-05; the evidence object nests those structures)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_dotted_nested_path_resolves_verified():
    evidence = make_evidence()
    evidence["zone"] = {"state": "mitigated", "range_high": 1.105, "range_low": 1.098}
    evidence["sweep"] = {"side": "low", "event_id": "ev-001"}
    narrative = _narrative(
        ["zone", "zone.state", "sweep.side"],
        "The mitigated zone state and low sweep side support a confirm",
    )
    result = citation_check(narrative, evidence)
    assert result["unknown"] == []
    assert result["status"] == "verified"


@pytest.mark.unit
def test_dotted_path_with_invented_leaf_unknown():
    evidence = make_evidence()
    evidence["zone"] = {"state": "mitigated"}
    narrative = _narrative(["zone.nope"], "citing a sub-field that does not exist")
    result = citation_check(narrative, evidence)
    assert result["unknown"] == ["zone.nope"]
    assert result["status"] == "unverified"


@pytest.mark.unit
def test_dotted_path_through_scalar_is_unknown():
    evidence = make_evidence()
    narrative = _narrative(["p_win.length"], "a dotted path through a scalar")
    result = citation_check(narrative, evidence)
    assert result["unknown"] == ["p_win.length"]
    assert result["status"] == "unverified"


@pytest.mark.unit
def test_nested_level_path_still_unverified():
    """A dotted path to a level-ish sub-field can't smuggle a citation through:
    it either resolves as unknown or stays unverified (D-05 holds)."""
    evidence = make_evidence()
    evidence["zone"] = {"state": "mitigated"}
    narrative = _narrative(["zone.entry"], "citing a level through a nested path")
    result = citation_check(narrative, evidence)
    assert result["status"] == "unverified"
    assert result["unknown"] == ["zone.entry"]
