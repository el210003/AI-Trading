"""Evidence serializer — assemble the D-01 structured evidence object the LLM
receives (point-in-time, MT5-free, pure).

Consumes three inputs and never reaches outside them:

- ``scorer_result``: the Phase 4 ``Scorer.score()`` output carrying the
  calibrated ``p_win``, ``score_source`` and ``artifact_version`` provenance.
- ``candidate_state``: the SMC candidate/setup fields (symbol, timeframe,
  direction, zone_id, zone_state, event_id, pool_id, sweep_side, bias_h1,
  bias_h4) plus the reference-only structural levels (entry / sl / tp) and the
  decision-time R:R (``rr_at_decision``).
- ``contributor_frame``: the ``Scorer.contributors()`` per-row attribution frame
  (feature columns plus a trailing ``bias`` column).

Point-in-time discipline (RESEARCH Pitfall 3 / Discretion A5): the serializer
consumes the frozen ``CandidateState`` / ``Scorer`` outputs AS-IS. It NEVER
recomputes an R:R, NEVER re-derives an SL/TP, NEVER reaches into any
post-decision column (fill-based ``entry_price`` / ``exit_*`` / ``r_*`` /
``outcome`` / fill-based ``rr``) and NEVER emits a raw OHLC/candle series
(D-03). The build is a whitelist over known keys, so a fill-derived field
cannot leak structurally.

Top-5 contributors: the ``contributor_frame`` is ranked by absolute raw
``pred_contrib`` EXCLUDING the trailing ``bias`` column, capped at
``cfg.llm_top_n_contributors`` (default 5), null/NaN contributor values are
dropped (never zero-filled — warmup rows are missing, not zero), and each is
exposed as ``{feature, contribution, effect}`` where ``effect`` is the sign of
the raw contribution relative to the ML direction (positive pushes toward a
higher P(WIN), negative away).

Pure: no I/O, no mutation of inputs, no MetaTrader5 import.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

#: Required fields on the Phase 4 scorer output (``Scorer.score()`` row).
_REQUIRED_SCORER_FIELDS = ("p_win", "score_source", "artifact_version")

#: Required SMC candidate-state fields that map into the evidence object.
#: Naming them here makes the fail-fast guard (Pitfall 3) exact instead of a
#: blind attribute typo surfacing later.
_REQUIRED_CANDIDATE_FIELDS = (
    "symbol",
    "timeframe",
    "direction",
    "zone_id",
    "zone_state",
    "event_id",
    "pool_id",
    "sweep_side",
    "bias_h1",
    "bias_h4",
    "entry",
    "sl",
    "tp",
    "rr_at_decision",
)

#: Reference-only level fields carried in the object but NEVER legal citation
#: targets (D-01 / D-02). ``sl_price`` / ``tp_price`` are the raw detector
#: outputs (frozen, not fill-derived); they are kept alongside ``sl``/``tp``
#: so the D-02 level-field citation-drop test can cite either spelling.
_REFERENCE_ONLY_LEVEL_FIELDS = ("sl_price", "tp_price")

#: Post-decision / fill-derived column set that must NEVER appear in the
#: evidence object (Pitfall 3 / D-03). Whitelist build makes absence
#: structural, but the guard makes it explicit and testable.
_FORBIDDEN_DERIVED_FIELDS = frozenset(
    {"entry_price", "exit_time", "exit_price", "exit_idx", "outcome", "rr"}
)

#: The trailing ``bias`` column name in the ``contributors`` frame.
_BIAS_COLUMN = "bias"


def _scalar(source: Any, field: str) -> Any:
    """Return ``source[field]`` as a scalar from a dict / Series / single-row
    DataFrame (Phase 4 scorer output shapes). Raises ``ValueError`` naming the
    field when absent."""
    if isinstance(source, pd.DataFrame):
        if field not in source.columns:
            raise ValueError(
                f"serialize_evidence invariant violated: required scorer field "
                f"{field!r} is missing"
            )
        return source.iloc[0][field]
    if isinstance(source, pd.Series):
        if field not in source.index:
            raise ValueError(
                f"serialize_evidence invariant violated: required scorer field "
                f"{field!r} is missing"
            )
        return source[field]
    if isinstance(source, dict):
        if field not in source:
            raise ValueError(
                f"serialize_evidence invariant violated: required scorer field "
                f"{field!r} is missing"
            )
        return source[field]
    raise TypeError(
        f"serialize_evidence invariant violated: scorer_result must be a dict, "
        f"Series or single-row DataFrame, got {type(source).__name__}"
    )


def _candidate_field(candidate_state: dict, field: str) -> Any:
    """Return a required candidate-state field, raising a named-field
    ``ValueError`` when absent (fail-fast guard, mirror of ``_validate_bars``)."""
    if field not in candidate_state:
        raise ValueError(
            f"serialize_evidence invariant violated: candidate_state is missing "
            f"required field {field!r}"
        )
    return candidate_state[field]


def _validate_evidence_inputs(
    scorer_result: Any, candidate_state: Any, contributor_frame: Any
) -> None:
    """Fail-fast guard naming any missing required field before blind assembly
    (RESEARCH Pitfall 3 / features.py ``_validate_bars`` discipline)."""
    if not isinstance(candidate_state, dict):
        raise TypeError(
            "serialize_evidence invariant violated: candidate_state must be a dict "
            f"of SMC fields, got {type(candidate_state).__name__}"
        )
    scorer_columns = set(_scorer_columns_any(scorer_result))
    missing_scorer = [f for f in _REQUIRED_SCORER_FIELDS if f not in scorer_columns]
    if missing_scorer:
        raise ValueError(
            f"serialize_evidence invariant violated: scorer_result is missing "
            f"required field(s) {missing_scorer}"
        )
    missing_candidate = [f for f in _REQUIRED_CANDIDATE_FIELDS if f not in candidate_state]
    if missing_candidate:
        raise ValueError(
            f"serialize_evidence invariant violated: candidate_state is missing "
            f"required field(s) {missing_candidate}"
        )
    if contributor_frame is None:
        raise ValueError(
            "serialize_evidence invariant violated: contributor_frame is required"
        )
    if not isinstance(contributor_frame, pd.DataFrame):
        raise TypeError(
            "serialize_evidence invariant violated: contributor_frame must be a "
            f"DataFrame, got {type(contributor_frame).__name__}"
        )


def _scorer_columns_any(source: Any) -> list[str]:
    """Return the field names available on the scorer result (for the guard)."""
    if isinstance(source, pd.DataFrame):
        return list(source.columns)
    if isinstance(source, pd.Series):
        return list(source.index)
    if isinstance(source, dict):
        return list(source.keys())
    return []


def _rank_contributors(contributor_frame: pd.DataFrame, cfg) -> list[dict]:
    """Rank the contribution row by absolute raw ``pred_contrib`` excluding the
    trailing ``bias`` column, drop null/NaN contributor values (never
    zero-fill), cap at ``cfg.llm_top_n_contributors``, and expose each as
    ``{feature, contribution, effect}``.

    ``effect`` is the sign of the raw contribution relative to the ML
    direction: ``positive`` pushes the probability toward the WIN class (higher
    P(WIN)), ``negative`` pushes away.
    """
    if contributor_frame.empty:
        return []
    top_n = getattr(cfg, "llm_top_n_contributors", 5)
    row = contributor_frame.iloc[0] if len(contributor_frame) else pd.Series(dtype=float)
    ranked: list[dict] = []
    for feature, value in row.items():
        if feature == _BIAS_COLUMN:
            continue
        if value is None or pd.isna(value):
            continue  # warmup/null contributor rows dropped, never zero-filled
        try:
            contrib = float(value)
        except (TypeError, ValueError):
            continue
        ranked.append({"feature": feature, "contribution": contrib})
    ranked.sort(key=lambda entry: abs(entry["contribution"]), reverse=True)
    ranked = ranked[:top_n]
    for entry in ranked:
        entry["effect"] = "positive" if entry["contribution"] >= 0 else "negative"
    return ranked


def serialize_evidence(
    scorer_result: Any, candidate_state: dict, contributor_frame: pd.DataFrame, cfg
) -> dict:
    """Assemble the D-01 evidence object dict (pure, point-in-time).

    Returns a NEW dict whose scalar keys are exactly ``ALLOWED_CITATION_KEYS``
    plus the reference-only level fields and the ``top_contributors`` list.
    The ``p_win`` / ``score_source`` / ``artifact_version`` provenance comes
    from ``scorer_result``; the SMC context from ``candidate_state``. Inputs
    are never mutated and no fill-derived / OHLC data is emitted.
    """
    _validate_evidence_inputs(scorer_result, candidate_state, contributor_frame)

    evidence: dict[str, Any] = {
        "symbol": str(_candidate_field(candidate_state, "symbol")),
        "timeframe": str(_candidate_field(candidate_state, "timeframe")),
        "direction": str(_candidate_field(candidate_state, "direction")),
        "zone_id": str(_candidate_field(candidate_state, "zone_id")),
        "zone_state": str(_candidate_field(candidate_state, "zone_state")),
        "event_id": str(_candidate_field(candidate_state, "event_id")),
        "pool_id": str(_candidate_field(candidate_state, "pool_id")),
        "sweep_side": str(_candidate_field(candidate_state, "sweep_side")),
        "bias_h1": _candidate_field(candidate_state, "bias_h1"),
        "bias_h4": _candidate_field(candidate_state, "bias_h4"),
        # Reference-only structural levels (D-01) — never legal citation targets.
        "entry": float(_candidate_field(candidate_state, "entry")),
        "sl": float(_candidate_field(candidate_state, "sl")),
        "tp": float(_candidate_field(candidate_state, "tp")),
        "rr_at_decision": float(_candidate_field(candidate_state, "rr_at_decision")),
    }
    for field in _REFERENCE_ONLY_LEVEL_FIELDS:
        if field in candidate_state:
            evidence[field] = float(candidate_state[field])

    evidence["p_win"] = float(_scalar(scorer_result, "p_win"))
    evidence["score_source"] = str(_scalar(scorer_result, "score_source"))
    evidence["artifact_version"] = int(_scalar(scorer_result, "artifact_version"))

    evidence["top_contributors"] = _rank_contributors(contributor_frame, cfg)

    # Structural guard (Pitfall 3 / D-03): the whitelist build above cannot
    # emit a post-decision/fill-derived field, but assert it so a future edit
    # that appends a derived key fails fast instead of leaking.
    leaked = _FORBIDDEN_DERIVED_FIELDS.intersection(evidence.keys())
    if leaked:
        raise ValueError(
            f"serialize_evidence invariant violated: evidence must not contain "
            f"post-decision/fill-derived field(s) {sorted(leaked)}"
        )
    return evidence
