"""Unit tests for setup assembly (SETUP-01/02) — the decision-bar-close entry,
the ``serialize_evidence`` round-trip + ``p_win``/``score_source`` provenance,
the AI-07 labeled fallback, and the point-in-time prefix-stability discipline.

Builds deterministic candidate worlds from ``_ml_fixtures`` and uses a fake
scorer + ``FakeLLMProvider`` from ``_llm_fixtures`` (no MT5, no live LLM).
"""

from __future__ import annotations

import json

import pandas as pd
import pytest
from _detector_fixtures import flat_bars
from _llm_fixtures import FakeLLMProvider
from _ml_fixtures import _h1_world, _h4_world, _m15_world
from _setup_fixtures import setup_cfg

import ai_trading.setup as setup_init
from ai_trading.backtest.candidates import candidate_at_bar, compute_rr
from ai_trading.backtest.chain import run_chain
from ai_trading.ml.features import features_at_decision
from ai_trading.setup.assembly import _asof_state, assemble_setup, build_setup_record

SYMBOL = "EURUSD"
# Determined from the sculpted world: candidate fires at decision bar 33
# (matches the Phase-3 world's single expected label at decision bar 33).
DECISION_IDX = 33


class FakeScorer:
    """Deterministic scorer double with the ``Scorer`` surface Phase 6 uses."""

    def __init__(self, p_win=0.72, artifact_version=1):
        self.p_win = p_win
        self.artifact_version = artifact_version

    def score(self, features: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "p_win": [self.p_win],
                "score_source": ["ml"],
                "artifact_version": [self.artifact_version],
            }
        )

    def contributors(self, features: pd.DataFrame) -> pd.DataFrame:
        row = {col: 0.05 for col in features.columns}
        row["bias"] = 0.0
        return pd.DataFrame([row])


def _world():
    return _m15_world(), _h1_world(), _h4_world()


def _disprove_future_leak_at(full, decision_idx, h1, h4, cfg, scorer):
    """Reproduce the assembly decision at ``decision_idx`` over a CHAIN computed
    from the FUTURE-containing frame (bars beyond the decision bar present),
    proving the as-of slices null out future bars (prefix-stability / repaint).
    Returns ``(entry, p_win)`` for the decision."""
    chain = run_chain(full, h1, h4)  # contains bars beyond the decision bar
    bar_t = pd.Timestamp(full["time_utc"].iloc[decision_idx])
    state = _asof_state(chain, bar_t, full.iloc[: decision_idx + 1].reset_index(drop=True))
    cand = candidate_at_bar(state, cfg)
    assert cand is not None, "decision world must produce a candidate"
    entry = float(full["close"].iloc[decision_idx])
    label_row = {
        "symbol": cand.symbol,
        "timeframe": cand.timeframe,
        "direction": cand.direction,
        "sl_price": cand.sl_price,
        "tp_price": cand.tp_price,
        "zone_id": cand.zone_id,
        "event_id": cand.event_id,
    }
    feats = features_at_decision(state, pd.Series(label_row), cfg)
    score_row = scorer.score(pd.DataFrame([feats])).iloc[0]
    return entry, float(score_row["p_win"])


def _verified_narrative(verdict="confirm", confidence=0.7, citations=("symbol", "direction")):
    """A citation-check-verifiable narrative response JSON (fields that exist on
    the evidence object)."""
    return json.dumps(
        {
            "verdict": verdict,
            "confidence": confidence,
            "reasoning": "structure agrees with the setup direction",
            "citations": list(citations),
        }
    )


@pytest.mark.unit
def test_package_exports_setup_surface():
    assert hasattr(setup_init, "assemble_setup")
    assert hasattr(setup_init, "build_setup_record")


@pytest.mark.unit
def test_candidate_fires_with_pinned_entry_and_rr():
    m15, h1, h4 = _world()
    cfg = setup_cfg()
    scorer = FakeScorer(p_win=0.72)
    llm = FakeLLMProvider()
    decision = m15.iloc[: DECISION_IDX + 1]
    rec = assemble_setup(cfg, SYMBOL, decision, h1, h4, scorer, llm)

    assert rec is not None
    # Pinned A3: entry == decision-bar close (last row of the m15 prefix).
    assert rec["entry"] == pytest.approx(float(decision["close"].iloc[-1]))
    sl = rec["sl_price"]
    tp = rec["tp_price"]
    risk = rec["entry"] - sl
    assert risk > 0
    assert rec["rr_at_decision"] == pytest.approx(
        compute_rr(rec["direction"], rec["entry"], sl, tp)
    )
    assert rec["status"] == "pending"
    assert rec["direction"] == "long"
    assert rec["symbol"] == SYMBOL


@pytest.mark.unit
def test_no_candidate_world_returns_none():
    cfg = setup_cfg()
    scorer = FakeScorer()
    llm = FakeLLMProvider()
    flat = flat_bars(SYMBOL, "M15", pd.Timestamp("2026-08-20T00:00:00").to_pydatetime(), 200)
    m15 = flat
    # Build flat HTF feeds (no sweeps/zones -> no candidate).
    flat_h1 = flat_bars(SYMBOL, "H1", pd.Timestamp("2026-08-20T00:00:00").to_pydatetime(), 40)
    flat_h4 = flat_bars(SYMBOL, "H4", pd.Timestamp("2026-08-20T00:00:00").to_pydatetime(), 40)
    rec = assemble_setup(cfg, SYMBOL, m15, flat_h1, flat_h4, scorer, llm)
    assert rec is None


@pytest.mark.unit
def test_evidence_roundtrip_and_provenance():
    m15, h1, h4 = _world()
    cfg = setup_cfg()
    scorer = FakeScorer(p_win=0.72)
    llm = FakeLLMProvider()
    rec = assemble_setup(cfg, SYMBOL, m15.iloc[: DECISION_IDX + 1], h1, h4, scorer, llm)

    assert rec is not None
    evidence = json.loads(rec["evidence_json"])
    assert evidence["symbol"] == SYMBOL
    assert evidence["p_win"] == pytest.approx(0.72)
    assert evidence["score_source"] == "ml"
    # delete-account: evidence objects carry the reference-only levels too.
    assert evidence["entry"] == pytest.approx(rec["entry"])
    assert evidence["sl"] == pytest.approx(rec["sl_price"])
    # Record provenance matches the scorer.
    assert rec["artifact_version"] == 1


@pytest.mark.unit
def test_ai07_fallback_labeled_when_llm_disabled():
    m15, h1, h4 = _world()
    cfg = setup_cfg(llm_enabled=False)
    scorer = FakeScorer()
    llm = FakeLLMProvider()
    rec = assemble_setup(cfg, SYMBOL, m15.iloc[: DECISION_IDX + 1], h1, h4, scorer, llm)

    assert rec is not None
    assert rec["narrative_status"] == "llm_unavailable"
    assert rec["narrative_reason"] == "llm_disabled"
    assert rec["score_source"] == "ml"  # honesty rule: no verified narrative -> ml


@pytest.mark.unit
def test_ai07_fallback_labeled_on_timeout():
    m15, h1, h4 = _world()
    cfg = setup_cfg(llm_enabled=True)
    scorer = FakeScorer()
    llm = FakeLLMProvider(
        errors=[TimeoutError("boom"), TimeoutError("boom")]  # 2 attempts (llm_max_retries=1)
    )
    rec = assemble_setup(cfg, SYMBOL, m15.iloc[: DECISION_IDX + 1], h1, h4, scorer, llm)

    assert rec is not None
    assert rec["narrative_status"] == "llm_unavailable"
    assert rec["narrative_reason"] == "timeout"
    assert rec["score_source"] == "ml"


@pytest.mark.unit
def test_score_source_promoted_to_ml_llm_on_verified_narrative():
    m15, h1, h4 = _world()
    cfg = setup_cfg(llm_enabled=True)
    scorer = FakeScorer()
    llm = FakeLLMProvider(responses=[_verified_narrative()])
    rec = assemble_setup(cfg, SYMBOL, m15.iloc[: DECISION_IDX + 1], h1, h4, scorer, llm)

    assert rec is not None
    assert rec["narrative_status"] == "ok"
    assert rec["narrative_verdict"] == "confirm"
    assert rec["agreement"] in ("agree", "disagree", "unclear")
    assert rec["score_source"] == "ml_llm"  # verified narrative attaches


@pytest.mark.unit
def test_prefix_stability_future_bars_do_not_repaint():
    """Appending future bars after the decision bar does not change the
    assembled entry/p_win/evidence for an already-assembled record. Proven by
    comparing the exact-prefix assembly against a re-derivation over a
    FUTURE-containing chain at the SAME decision bar."""
    m15, h1, h4 = _world()
    cfg = setup_cfg()
    scorer = FakeScorer(p_win=0.72)
    llm = FakeLLMProvider()

    rec = assemble_setup(cfg, SYMBOL, m15.iloc[: DECISION_IDX + 1], h1, h4, scorer, llm)
    assert rec is not None
    rebased_entry, rebased_p_win = _disprove_future_leak_at(
        m15, DECISION_IDX, h1, h4, cfg, scorer
    )

    assert rec["entry"] == pytest.approx(rebased_entry)
    assert rec["p_win"] == pytest.approx(rebased_p_win)
    # The persisted evidence object round-trips and carries the ML provenance.
    evidence = json.loads(rec["evidence_json"])
    assert evidence["entry"] == pytest.approx(rec["entry"])
    assert evidence["p_win"] == pytest.approx(rec["p_win"])


@pytest.mark.unit
def test_build_setup_record_names_all_fields():
    rec = build_setup_record(
        setup_id="s-test",
        symbol="EURUSD",
        timeframe="M15",
        direction="long",
        entry=1.10,
        sl_price=1.095,
        tp_price=1.12,
        rr_at_decision=4.0,
        entry_bar_idx=36,
        created_at=pd.Timestamp("2026-08-20T09:00:00"),
        zone_id="z-001",
        event_id="ev-001",
        pool_id="p-001",
        zone_range_high=1.105,
        zone_range_low=1.098,
        zone_state="mitigated",
        bias_h1="bullish",
        bias_h4="bullish",
        p_win=0.6,
        score_source="ml",
        artifact_version=1,
        evidence_json="{}",
        narrative_status="llm_unavailable",
        narrative_reason="llm_disabled",
        narrative_verdict=pd.NA,
        narrative_confidence=float("nan"),
        narrative_reasoning=pd.NA,
        narrative_citations=pd.NA,
        agreement=pd.NA,
        agreement_confidence=float("nan"),
    )
    from ai_trading.setup.store import SETUP_COLUMNS

    assert list(rec.keys()) == list(SETUP_COLUMNS)
    assert rec["status"] == "pending"
    assert rec["outcome"] is pd.NA
