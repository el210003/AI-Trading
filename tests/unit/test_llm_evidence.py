"""Unit tests for ``serialize_evidence`` — the D-01 evidence object builder.

Pinned tests: the evidence dict carries every ``ALLOWED_CITATION_KEYS`` field
plus the reference-only level fields; the top-5 contributors are ranked by
absolute ``pred_contrib`` excluding ``bias``, capped at
``cfg.llm_top_n_contributors``, null/NaN dropped not zero-filled; the object
contains no post-decision/fill-derived field and no raw OHLC series (D-03 /
RESEARCH Pitfall 3); a missing required scorer/candidate field fails fast
naming the field.
"""

from __future__ import annotations

import pandas as pd
import pytest
from _llm_fixtures import llm_cfg

from ai_trading.llm.evidence import serialize_evidence
from ai_trading.llm.schema import ALLOWED_CITATION_KEYS

#: Post-decision / fill-derived keys that must never appear in the evidence
#: object (mirrors ml/features FORBIDDEN-input discipline, Pitfall 3).
_FORBIDDEN_DERIVED = {
    "entry_price",
    "exit_time",
    "exit_price",
    "exit_idx",
    "outcome",
    "rr",
    "r_gross",
    "r_net",
    "r_raw",
}
_OHLC = {"open", "high", "low", "close", "volume"}


def _scorer_result(p_win: float = 0.72, **overrides) -> dict:
    return {
        "p_win": p_win,
        "score_source": "ml",
        "artifact_version": 1,
        **overrides,
    }


def _candidate_state(**overrides) -> dict:
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
        "sl_price": 1.09850,
        "tp_price": 1.12340,
        "rr_at_decision": 2.1,
        **overrides,
    }


def _contributor_frame(**columns) -> pd.DataFrame:
    data = {
        "atr14": 0.005,
        "rr_at_decision": 0.4,
        "htf_bias_agreement": 0.3,
        "zone_position": -0.25,
        "bars_since_sweep": 0.0,
        "bias": 0.1,  # trailing bias column — excluded from ranking
    }
    data.update(columns)
    return pd.DataFrame([data])


@pytest.mark.unit
def test_evidence_keys_match_allowed_and_level_fields():
    cfg = llm_cfg()
    evidence = serialize_evidence(
        _scorer_result(), _candidate_state(), _contributor_frame(), cfg
    )
    for key in ALLOWED_CITATION_KEYS:
        assert key in evidence, f"evidence missing allowed key {key!r}"
    # Reference-only level fields present in the object.
    for key in ("entry", "sl", "tp", "sl_price", "tp_price", "rr_at_decision"):
        assert key in evidence
    # ML provenance from the scorer result.
    assert evidence["p_win"] == pytest.approx(0.72)
    assert evidence["score_source"] == "ml"
    assert evidence["artifact_version"] == 1
    assert "top_contributors" in evidence


@pytest.mark.unit
def test_top_contributors_ranked_excluding_bias_dropping_null():
    cfg = llm_cfg(llm_top_n_contributors=5)
    frame = _contributor_frame(
        alpha=2.0, beta=1.0, gamma=-3.0, delta=0.5, epsilon=float("nan"), zeta=None
    )
    evidence = serialize_evidence(_scorer_result(), _candidate_state(), frame, cfg)
    top = evidence["top_contributors"]
    # Bias excluded, null/NaN dropped (not zero-filled).
    features = [entry["feature"] for entry in top]
    assert "bias" not in features
    assert "epsilon" not in features
    assert "zeta" not in features
    # Ranked by absolute value, descending.
    abs_contribs = [abs(entry["contribution"]) for entry in top]
    assert abs_contribs == sorted(abs_contribs, reverse=True)
    # gamma (-3.0) is largest |contrib|, so first.
    assert top[0]["feature"] == "gamma"
    assert top[0]["contribution"] == pytest.approx(-3.0)
    assert top[0]["effect"] == "negative"
    # alpha (+2.0) second, effect positive.
    assert top[1]["feature"] == "alpha"
    assert top[1]["effect"] == "positive"


@pytest.mark.unit
def test_top_contributors_capped_at_cfg_top_n():
    cfg = llm_cfg(llm_top_n_contributors=2)
    frame = _contributor_frame(a=1.0, b=2.0, c=3.0, d=4.0)
    evidence = serialize_evidence(_scorer_result(), _candidate_state(), frame, cfg)
    assert len(evidence["top_contributors"]) == 2


@pytest.mark.unit
def test_evidence_no_ohlc_no_recompute():
    cfg = llm_cfg()
    evidence = serialize_evidence(
        _scorer_result(), _candidate_state(), _contributor_frame(), cfg
    )
    keys = set(evidence.keys())
    assert not keys.intersection(_FORBIDDEN_DERIVED), (
        f"evidence carries post-decision/fill-derived keys: "
        f"{sorted(keys.intersection(_FORBIDDEN_DERIVED))}"
    )
    assert not keys.intersection(_OHLC), (
        f"evidence carries raw OHLC series keys: {sorted(keys.intersection(_OHLC))}"
    )


@pytest.mark.unit
def test_missing_scorer_field_raises_named_value_error():
    cfg = llm_cfg()
    scorer = _scorer_result()
    del scorer["p_win"]
    with pytest.raises(ValueError) as exc:
        serialize_evidence(scorer, _candidate_state(), _contributor_frame(), cfg)
    assert "p_win" in str(exc.value)


@pytest.mark.unit
def test_missing_candidate_field_raises_named_value_error():
    cfg = llm_cfg()
    state = _candidate_state()
    del state["zone_state"]
    with pytest.raises(ValueError) as exc:
        serialize_evidence(_scorer_result(), state, _contributor_frame(), cfg)
    assert "zone_state" in str(exc.value)


@pytest.mark.unit
def test_missing_contributor_frame_raises():
    cfg = llm_cfg()
    with pytest.raises(ValueError) as exc:
        serialize_evidence(_scorer_result(), _candidate_state(), None, cfg)
    assert "contributor_frame" in str(exc.value)
