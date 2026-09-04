"""Setup assembly (SETUP-01/02) — turn one M15 decision close into a fully
evidenced live setup record, reusing the Phase 3/4/5 pure functions verbatim
(D-03 / BT-01). MT5-free, side-effect-free (the only I/O lives in the injected
``scorer`` / ``llm_provider``).

Pipeline (pinned in 06-CONTEXT / RESEARCH Pattern 1): ``run_chain`` ->
as-of ``CandidateState`` at the decision bar -> ``candidate_at_bar`` ->
decision-bar-close ``entry`` (A3) -> ``compute_rr`` ->
``features_at_decision`` (18 features) -> ``scorer.score``/
``scorer.contributors`` -> ``serialize_evidence`` -> eager
``run_narrative_pipeline`` (OQ2) -> ``build_setup_record``.

Honesty rule (UI-SPEC): the record's ``score_source`` is ``ml_llm`` ONLY when
a verified narrative attaches (``narrative_status == "ok"``); otherwise it
stays the scorer's ``"ml"``. Never present an ML+LLM-tagged score without an
attached verified narrative.

Point-in-time discipline (Pitfall 2): every detector tier is sliced through
``visible_mask`` at the decision bar with the exact per-tier anchors, and the
``payload_row`` is consumed as-is (never re-anchored). Prefix-stability is
proven by test — appending future bars after the decision bar does not change
an already-assembled record's ``entry``/``p_win``/``evidence``.
"""

from __future__ import annotations

import json
import math
from uuid import uuid4

import pandas as pd

from ai_trading.backtest.asof import STAMP_BAR, STAMP_CLOSE, close_time_of, visible_mask
from ai_trading.backtest.candidates import CandidateState, candidate_at_bar, compute_rr
from ai_trading.backtest.chain import run_chain
from ai_trading.llm.evidence import serialize_evidence
from ai_trading.llm.narrative import run_narrative_pipeline
from ai_trading.ml.features import features_at_decision

M15 = "M15"


def _json_default(obj):
    """JSON-safe renderer for the evidence object: pandas null scalars (NA /
    NaT / NaN) become ``null``; numpy/pandas scalars collapse to their Python
    value; anything else falls through to ``str`` (never raises)."""
    if obj is pd.NA or obj is pd.NaT:
        return None
    if isinstance(obj, float) and math.isnan(obj):
        return None
    if hasattr(obj, "item"):
        try:
            return obj.item()
        except Exception:
            pass
    return str(obj)


def _tapped_zone(chain_zones: pd.DataFrame, zone_id: str) -> pd.Series | None:
    """Locate the tapped zone row by ``zone_id`` (zone_id is unique)."""
    if chain_zones is None or chain_zones.empty:
        return None
    matches = chain_zones[chain_zones["zone_id"] == zone_id]
    return matches.iloc[0] if len(matches) else None


def _sweep_side(chain_events: pd.DataFrame, event_id: str) -> str | None:
    """The side of the sweep event fired at this decision (``low``/``high``)."""
    if chain_events is None or chain_events.empty:
        return None
    matches = chain_events[chain_events["event_id"] == event_id]
    return str(matches.iloc[0]["side"]) if len(matches) else None


def _asof_state(chain: dict, bar_t: pd.Timestamp, m15: pd.DataFrame) -> CandidateState:
    """Build the as-of ``CandidateState`` at the decision bar (Pitfall 2)."""
    close_t = close_time_of(bar_t, M15)
    events = chain["events15"]
    zones = chain["zones15"]
    pools = chain["pools15"]
    swings = chain["swings15"]
    payload = chain["payload"]

    payload_rows = (
        payload[payload["time_utc"] == bar_t]
        if payload is not None and not payload.empty
        else payload
    )
    return CandidateState(
        m15_bars=m15,
        events15=(
            events[visible_mask(events, "resolved_at", STAMP_BAR, bar_t, close_t)]
            if events is not None and not events.empty
            else events
        ),
        zones15=(
            zones[visible_mask(zones, "mitigated_at", STAMP_BAR, bar_t, close_t)]
            if zones is not None and not zones.empty
            else zones
        ),
        pools15=(
            pools[visible_mask(pools, "activated_at", STAMP_CLOSE, bar_t, close_t)]
            if pools is not None and not pools.empty
            else pools
        ),
        swings15=(
            swings[visible_mask(swings, "confirmed_at", STAMP_CLOSE, bar_t, close_t)]
            if swings is not None and not swings.empty
            else swings
        ),
        payload_row=payload_rows.iloc[0] if len(payload_rows) else None,
    )


def build_setup_record(
    *,
    setup_id: str,
    symbol: str,
    timeframe: str,
    direction: str,
    entry: float,
    sl_price: float,
    tp_price: float,
    rr_at_decision: float,
    entry_bar_idx: int,
    created_at: pd.Timestamp,
    zone_id: str,
    event_id: str,
    pool_id: str,
    zone_range_high: float,
    zone_range_low: float,
    zone_state: str,
    bias_h1,
    bias_h4,
    p_win: float,
    score_source: str,
    artifact_version,
    evidence_json: str,
    narrative_status: str,
    narrative_reason,
    narrative_verdict,
    narrative_confidence,
    narrative_reasoning,
    narrative_citations,
    agreement,
    agreement_confidence,
) -> dict:
    """Build a pending setup record matching ``store.SETUP_COLUMNS`` exactly.

    Every field is named explicitly (no positional dict-injection) so a missing
    field fails loudly at the call site. Resolution-only fields (trigger/exit /
    outcome / r_*) are null for a fresh pending setup.
    """
    return {
        "setup_id": setup_id,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry": float(entry),
        "sl_price": float(sl_price),
        "tp_price": float(tp_price),
        "rr_at_decision": float(rr_at_decision),
        "entry_bar_idx": int(entry_bar_idx),
        "created_at": pd.Timestamp(created_at),
        "zone_id": zone_id,
        "event_id": event_id,
        "pool_id": pool_id,
        "zone_range_high": float(zone_range_high),
        "zone_range_low": float(zone_range_low),
        "zone_state": zone_state,
        "bias_h1": bias_h1,
        "bias_h4": bias_h4,
        "p_win": float(p_win),
        "score_source": score_source,
        "artifact_version": artifact_version,
        "evidence_json": evidence_json,
        "narrative_status": narrative_status,
        "narrative_reason": narrative_reason,
        "narrative_verdict": narrative_verdict,
        "narrative_confidence": narrative_confidence,
        "narrative_reasoning": narrative_reasoning,
        "narrative_citations": narrative_citations,
        "agreement": agreement,
        "agreement_confidence": agreement_confidence,
        "status": "pending",
        "outcome": pd.NA,
        "trigger_time": pd.NaT,
        "trigger_bar_idx": pd.NA,
        "closed_at": pd.NaT,
        "exit_price": pd.NA,
        "exit_time": pd.NaT,
        "exit_idx": pd.NA,
        "r_gross": pd.NA,
        "r_raw": pd.NA,
        "r_net": pd.NA,
    }


def _narrative_record(narrative) -> dict:
    """Carry the ``NarrativeResult`` observable state onto the record (AI-07
    labeled fallback never leaves a blank)."""
    obj = narrative.narrative
    return {
        "narrative_status": narrative.narrative_status,
        "narrative_reason": narrative.reason,
        "narrative_verdict": obj.verdict if obj is not None else pd.NA,
        "narrative_confidence": float(obj.confidence) if obj is not None else float("nan"),
        "narrative_reasoning": obj.reasoning if obj is not None else pd.NA,
        "narrative_citations": (
            json.dumps(obj.citations) if obj is not None and obj.citations else pd.NA
        ),
        "agreement": narrative.agreement,
        "agreement_confidence": narrative.agreement_confidence,
    }


def assemble_setup(cfg, symbol: str, m15: pd.DataFrame, h1: pd.DataFrame, h4: pd.DataFrame,
                   scorer, llm_provider) -> dict | None:
    """Assemble one fully-evidenced pending setup at the last closed M15 bar.

    Returns a record dict matching ``store.SETUP_COLUMNS`` (status ``pending``)
    when a D-01/D-02 candidate fires, or ``None`` when no candidate exists.
    ``m15`` is the M15 frame whose LAST bar is the decision bar (the prefix up
    to and including the decision close); ``h1``/``h4`` are the HTF feeds.
    """
    if m15 is None or m15.empty:
        return None

    chain = run_chain(m15, h1, h4)
    bar_t = pd.Timestamp(m15["time_utc"].iloc[-1])
    close_t = close_time_of(bar_t, M15)

    state = _asof_state(chain, bar_t, m15)
    cand = candidate_at_bar(state, cfg)
    if cand is None:
        return None

    entry = float(m15["close"].iloc[-1])  # A3: decision-bar close
    rr = compute_rr(cand.direction, entry, cand.sl_price, cand.tp_price)

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
    feat_frame = pd.DataFrame([feats])
    score_row = scorer.score(feat_frame).iloc[0]
    contrib_frame = scorer.contributors(feat_frame)

    zone = _tapped_zone(chain["zones15"], cand.zone_id)
    sweep_side = _sweep_side(chain["events15"], cand.event_id)

    candidate_fields = {
        "symbol": cand.symbol,
        "timeframe": cand.timeframe,
        "direction": cand.direction,
        "zone_id": cand.zone_id,
        "zone_state": str(zone["state"]) if zone is not None else "mitigated",
        "event_id": cand.event_id,
        "pool_id": cand.pool_id,
        "sweep_side": sweep_side if sweep_side is not None else cand.direction,
        "bias_h1": cand.bias_h1,
        "bias_h4": cand.bias_h4,
        "entry": entry,
        "sl": cand.sl_price,
        "tp": cand.tp_price,
        "rr_at_decision": rr,
        "sl_price": cand.sl_price,
        "tp_price": cand.tp_price,
    }
    evidence = serialize_evidence(score_row, candidate_fields, contrib_frame, cfg)

    narrative = run_narrative_pipeline(llm_provider, evidence, cfg)
    narr = _narrative_record(narrative)

    # Honesty rule: ml_llm only when a verified narrative attaches, else ml.
    score_source = "ml_llm" if narrative.narrative_status == "ok" else "ml"
    p_win = float(narrative.p_win if narrative.p_win is not None else score_row["p_win"])

    return build_setup_record(
        setup_id=uuid4().hex,
        symbol=cand.symbol,
        timeframe=cand.timeframe,
        direction=cand.direction,
        entry=entry,
        sl_price=cand.sl_price,
        tp_price=cand.tp_price,
        rr_at_decision=rr,
        entry_bar_idx=cand.entry_bar_idx,
        created_at=close_t,  # decision-bar close time
        zone_id=cand.zone_id,
        event_id=cand.event_id,
        pool_id=cand.pool_id,
        zone_range_high=float(zone["range_high"]) if zone is not None else float("nan"),
        zone_range_low=float(zone["range_low"]) if zone is not None else float("nan"),
        zone_state=str(zone["state"]) if zone is not None else "mitigated",
        bias_h1=cand.bias_h1,
        bias_h4=cand.bias_h4,
        p_win=p_win,
        score_source=score_source,
        artifact_version=narrative.artifact_version if narrative.artifact_version is not None
        else score_row["artifact_version"],
        evidence_json=json.dumps(evidence, default=_json_default),
        **narr,
    )
