"""Walk-forward ML evaluation: per-window train-or-skip loop, decided-only
headline metrics, flagged TIMEOUT scores, reliability rows (AI-04, D-01, D-02,
Pattern 5, Pattern 6, Pitfall 12).

``run_walkforward_eval`` consumes the SAME label/feature frames and the SAME
Phase 3 ``build_windows`` windows the ML pipeline trains on — it is NOT a new
splitter (AI-04/SC3: the harness is the only splitter; no shuffled splits
anywhere). Along with ``run_walkforward_eval``'s sibling ``run_ml_pipeline`` in
``ml/runner.py``, every labeled candidate row receives a probability and every
score row records its ``score_source`` (``ml`` or ``heuristic``) — a score
without provenance is a bug (research anti-pattern).

CONVENTIONS (pinned by named tests):

- D-01 DECIDED-ONLY HEADLINE: AUC / log-loss / Brier are computed on decided
  rows (win/loss) ONLY. TIMEOUT rows never train and never enter headline
  metrics; they appear in ``ml_scores.parquet`` flagged ``excluded=True`` with
  their probabilities kept (D-02 score-and-flag) — no metric contamination, no
  information lost.
- PATTERN 5 SKIP CONTRACT: a window whose purged-decided train slice fails
  ``ml.train.preflight_reason`` is recorded as ``status="skipped"`` with the
  stable reason prefix (never raised, never fabricated) and its test span is
  covered by the heuristic scorer (Pattern 6) with ``score_source="heuristic"``
  — which is structurally barred from the ML headline/reliability aggregation.
- PATTERN 6 HEURISTIC COVERAGE: skipped windows' test rows are scored by
  ``ml.heuristic.heuristic_score`` over the same FEATURE_SPEC vector.
- RELIABILITY: per-window ``ml.train.reliability_curve`` on the decided ML
  probabilities, tagged with the window; a single pooled set over all decided
  test rows across windows is tagged ``window_id=-1`` (the pooled-scope marker
  documented in the module docstring). Empty when no window passes preflight.
- SCORES = one row per label row (label order preserved): symbol, timeframe,
  entry_time, direction, outcome, window_id, p_win, excluded (True exactly for
  TIMEOUT rows), score_source, provenance, artifact_version (NaN in eval —
  per-window models are transient; the versioned bundle is plan-02's saved
  artifact the runner records on the report summary).

ALIGNMENT: ``features`` row i must correspond to ``labels`` row i (the
``build_feature_frame`` alignment invariant) and both frames must be
non-empty; a mismatch raises ValueError naming the misalignment.

Pure pandas/lightgbm/sklearn: no file I/O, no MetaTrader5, inputs never
mutated.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

from ai_trading.backtest.barriers import OUTCOME_LOSS, OUTCOME_TIMEOUT, OUTCOME_WIN
from ai_trading.backtest.walkforward import Window, label_window_assignment
from ai_trading.ml.features import FEATURE_NAMES
from ai_trading.ml.folds import calibration_folds
from ai_trading.ml.heuristic import heuristic_score
from ai_trading.ml.purge import purged_train_mask
from ai_trading.ml.train import (
    decided_mask,
    fit_calibrated,
    preflight_reason,
    reliability_curve,
)

#: Report ``provenance`` for a window that produced an ML model.
PROVENANCE_WINDOW_MODEL = "window_model"
#: Report/scores ``provenance`` for heuristic-scored rows.
PROVENANCE_HEURISTIC = "heuristic"

_DECIDED = frozenset({OUTCOME_WIN, OUTCOME_LOSS})

#: Exact report schema (empty-frame pinned too).
REPORT_COLUMNS = (
    "window_id",
    "status",
    "reason",
    "n_train_decided",
    "n_test_decided",
    "n_timeout_flagged",
    "auc",
    "log_loss",
    "brier",
    "provenance",
)

#: Exact reliability schema.
RELIABILITY_COLUMNS = ("window_id", "bin", "prob_pred", "prob_true", "count")

#: Exact scores schema.
SCORES_COLUMNS = (
    "symbol",
    "timeframe",
    "entry_time",
    "direction",
    "outcome",
    "window_id",
    "p_win",
    "excluded",
    "score_source",
    "provenance",
    "artifact_version",
)


@dataclass
class EvalResult:
    """Walk-forward evaluation outputs: per-window report, reliability rows and
    per-label scores, all DataFrames."""

    report: pd.DataFrame
    reliability: pd.DataFrame
    scores: pd.DataFrame


def _nan():  # type: ignore[no-untyped-def]
    return float("nan")


def _empty_report() -> pd.DataFrame:
    data: dict[str, pd.Series] = {
        "window_id": pd.Series(dtype="int64"),
        "status": pd.Series(dtype="string"),
        "reason": pd.Series(dtype="string"),
        "n_train_decided": pd.Series(dtype="int64"),
        "n_test_decided": pd.Series(dtype="int64"),
        "n_timeout_flagged": pd.Series(dtype="int64"),
        "auc": pd.Series(dtype="float64"),
        "log_loss": pd.Series(dtype="float64"),
        "brier": pd.Series(dtype="float64"),
        "provenance": pd.Series(dtype="string"),
    }
    return pd.DataFrame(data)[list(REPORT_COLUMNS)]


def _empty_reliability() -> pd.DataFrame:
    data: dict[str, pd.Series] = {
        "window_id": pd.Series(dtype="int64"),
        "bin": pd.Series(dtype="int64"),
        "prob_pred": pd.Series(dtype="float64"),
        "prob_true": pd.Series(dtype="float64"),
        "count": pd.Series(dtype="int64"),
    }
    return pd.DataFrame(data)[list(RELIABILITY_COLUMNS)]


def _empty_scores() -> pd.DataFrame:
    data: dict[str, pd.Series] = {
        "symbol": pd.Series(dtype="string"),
        "timeframe": pd.Series(dtype="string"),
        "entry_time": pd.Series(dtype="datetime64[us]"),
        "direction": pd.Series(dtype="string"),
        "outcome": pd.Series(dtype="string"),
        "window_id": pd.Series(dtype="int64"),
        "p_win": pd.Series(dtype="float64"),
        "excluded": pd.Series(dtype="bool"),
        "score_source": pd.Series(dtype="string"),
        "provenance": pd.Series(dtype="string"),
        "artifact_version": pd.Series(dtype="float64"),
    }
    return pd.DataFrame(data)[list(SCORES_COLUMNS)]


def _headline_metrics(
    y_dec: pd.Series, p_dec: np.ndarray
) -> tuple[float, float, float]:
    """Decided-only headline metrics (AUC / log-loss / Brier) with nan guards.

    ``roc_auc_score`` returns NaN (with the documented reason) when the decided
    test slice is single-class; ``log_loss`` is always called with
    ``labels=[0, 1]`` so a single-class test set never raises; ``brier`` is
    computed on the decided rows.
    """
    y = pd.to_numeric(y_dec, errors="coerce")
    if y.nunique() < 2:
        auc = _nan()
    else:
        auc = float(roc_auc_score(y.to_numpy(), p_dec))
    log_l = float(log_loss(y.to_numpy(), p_dec, labels=[0, 1]))
    brier = float(brier_score_loss(y.to_numpy(), p_dec))
    return auc, log_l, brier


def run_walkforward_eval(
    labels: pd.DataFrame,
    features: pd.DataFrame,
    windows: list[Window],
    cfg,
) -> EvalResult:
    """Run the per-window walk-forward evaluation and return the three report
    shapes (``EvalResult.report`` / ``.reliability`` / ``.scores``).

    Args:
        labels: the label frame (the source-of-truth training/eval rows); every
            label carries ``entry_time``, ``exit_time``, ``outcome``,
            ``symbol``, ``timeframe``, ``direction``.
        features: the feature frame built by ``ml.features.build_feature_frame``;
            row i corresponds to ``labels`` row i (the alignment invariant).
        windows: the Phase 3 ``build_windows`` output (the ONLY splitter).
        cfg: frozen Config carrying the ml_* knobs.

    Raises:
        ValueError: when ``features`` row count differs from ``labels`` row
            count or either frame is empty, naming the misalignment.

    Every label lands in exactly one window via
    ``walkforward.label_window_assignment`` (the harness contract); that window
    is either trained (``fit_calibrated`` on the purged-decided train slice) or
    skipped with its test span heuristic-scored.
    """
    if len(features) != len(labels):
        raise ValueError(
            "run_walkforward_eval invariant violated: features row count "
            f"{len(features)} != labels row count {len(labels)} (the feature "
            "frame must align to the label frame row-for-row)"
        )
    if labels.empty or features.empty:
        raise ValueError(
            "run_walkforward_eval invariant violated: labels and features must "
            "be non-empty frames (a zero-candidate eval is a runner-level "
            "supported state, not an eval-level input)"
        )

    labels = labels.reset_index(drop=True)
    features = features.reset_index(drop=True)

    labels_w = label_window_assignment(labels, windows)
    window_of_label = labels_w["window_id"].to_numpy()

    outcomes = labels["outcome"].astype(str).to_numpy()
    decided_np = decided_mask(labels["outcome"]).to_numpy()
    y_win = pd.Series(
        (labels["outcome"].astype(str) == OUTCOME_WIN).astype("int64").to_numpy()
    )
    exit_times = labels["exit_time"]
    n = len(labels)

    # Per-label provenance/score state (filled per window, read back in order).
    score_state: dict[int, dict[str, Any]] = {i: None for i in range(n)}
    report_rows: list[dict[str, Any]] = []
    reliability_frames: list[pd.DataFrame] = []
    pooled_y: list[int] = []
    pooled_p: list[float] = []

    feature_names = list(FEATURE_NAMES)

    for w in windows:
        wid = int(w.window_id)
        train_mask_np = w.train_mask.to_numpy(dtype=bool)
        test_mask_np = w.test_mask.to_numpy(dtype=bool)

        # D-01 decided-only training + OQ5 purge over exit times.
        keep_mask = purged_train_mask(
            w.train_mask, exit_times, w.test_start, cfg.ml_embargo_bars
        )
        train_keep_np = (
            keep_mask.to_numpy(dtype=bool) & train_mask_np & decided_np
        )
        train_pos = np.flatnonzero(train_keep_np).tolist()

        test_pos = np.flatnonzero(test_mask_np).tolist()
        n_test_decided = int(sum(1 for i in test_pos if outcomes[i] in _DECIDED))
        n_timeout_flagged = int(sum(1 for i in test_pos if outcomes[i] == OUTCOME_TIMEOUT))

        # Calibration folds over the decided train slice (harness-derived).
        train_entry = labels["entry_time"].iloc[train_pos]
        train_exit = exit_times.iloc[train_pos]
        folds = calibration_folds(
            train_entry,
            train_exit,
            cfg.ml_cal_test_days,
            cfg.ml_cal_train_days,
            cfg.ml_embargo_bars,
        )
        y_train = y_win.iloc[train_pos].reset_index(drop=True)
        reason = preflight_reason(y_train, cfg.ml_min_train_labels, folds)

        n_train_decided = len(train_pos)

        if reason is not None:
            # Pattern 5: record the skip, cover the span heuristically.
            report_rows.append(
                {
                    "window_id": wid,
                    "status": "skipped",
                    "reason": reason,
                    "n_train_decided": n_train_decided,
                    "n_test_decided": n_test_decided,
                    "n_timeout_flagged": n_timeout_flagged,
                    "auc": _nan(),
                    "log_loss": _nan(),
                    "brier": _nan(),
                    "provenance": _nan(),
                }
            )
            _score_heuristic(
                features, feature_names, test_pos, outcomes, window_of_label,
                wid, score_state,
            )
            continue

        # Pattern: subset to the FEATURE_SPEC matrix, fit calibrated, score ALL
        # test rows (D-02: every candidate row gets a probability).
        X_train = features.iloc[train_pos][feature_names]
        calibrated = fit_calibrated(
            X_train, y_train, folds, cfg.ml_calibration_method, cfg
        )
        X_test = features.iloc[test_pos][feature_names]
        p_all = calibrated.predict_proba(X_test)[:, 1]

        decided_in_test = [k for k, i in enumerate(test_pos) if outcomes[i] in _DECIDED]
        y_test_dec = y_win.iloc[test_pos]
        y_dec = y_test_dec.iloc[decided_in_test].reset_index(drop=True)
        p_dec = p_all[decided_in_test]
        auc, log_l, brier = _headline_metrics(y_dec, p_dec)

        report_rows.append(
            {
                "window_id": wid,
                "status": "ok",
                "reason": _nan(),
                "n_train_decided": n_train_decided,
                "n_test_decided": n_test_decided,
                "n_timeout_flagged": n_timeout_flagged,
                "auc": auc,
                "log_loss": log_l,
                "brier": brier,
                "provenance": PROVENANCE_WINDOW_MODEL,
            }
        )

        # Reliability: per-window curve on decided ML probabilities.
        rel = reliability_curve(y_dec, p_dec)
        if not rel.empty:
            rel = rel.copy()
            rel["window_id"] = wid
            reliability_frames.append(rel)
        pooled_y.extend(int(v) for v in y_dec.tolist())
        pooled_p.extend(float(v) for v in p_dec.tolist())

        # Score every test row (decided + TIMEOUT) as ML.
        for k, i in enumerate(test_pos):
            score_state[i] = {
                "window_id": wid,
                "p_win": float(p_all[k]),
                "score_source": "ml",
                "provenance": PROVENANCE_WINDOW_MODEL,
            }

    report = _assemble_report(report_rows)
    reliability = _assemble_reliability(reliability_frames, pooled_y, pooled_p)
    scores = _assemble_scores(labels, outcomes, window_of_label, score_state)
    return EvalResult(report=report, reliability=reliability, scores=scores)


def _score_heuristic(
    features: pd.DataFrame,
    feature_names: list[str],
    test_pos: list[int],
    outcomes: np.ndarray,
    window_of_label: np.ndarray,
    wid: int,
    score_state: dict[int, dict[str, Any]],
) -> None:
    """Score a skipped window's test rows via the heuristic (Pattern 6)."""
    X_test = features.iloc[test_pos][feature_names]
    p = heuristic_score(X_test).to_numpy()
    for k, i in enumerate(test_pos):
        score_state[i] = {
            "window_id": wid,
            "p_win": float(p[k]),
            "score_source": "heuristic",
            "provenance": PROVENANCE_HEURISTIC,
        }


def _assemble_report(report_rows: list[dict[str, Any]]) -> pd.DataFrame:
    if not report_rows:
        return _empty_report()
    frame = pd.DataFrame(report_rows, columns=list(REPORT_COLUMNS))
    frame["window_id"] = frame["window_id"].astype("int64")
    frame["n_train_decided"] = frame["n_train_decided"].astype("int64")
    frame["n_test_decided"] = frame["n_test_decided"].astype("int64")
    frame["n_timeout_flagged"] = frame["n_timeout_flagged"].astype("int64")
    frame["auc"] = frame["auc"].astype("float64")
    frame["log_loss"] = frame["log_loss"].astype("float64")
    frame["brier"] = frame["brier"].astype("float64")
    frame["status"] = frame["status"].astype("string")
    frame["reason"] = frame["reason"].astype("string")
    frame["provenance"] = frame["provenance"].astype("string")
    return frame.sort_values("window_id").reset_index(drop=True)


def _assemble_reliability(
    reliability_frames: list[pd.DataFrame],
    pooled_y: list[int],
    pooled_p: list[float],
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = list(reliability_frames)
    if pooled_y:
        pooled = reliability_curve(
            pd.Series(pooled_y, dtype="int64"), pd.Series(pooled_p, dtype="float64")
        )
        if not pooled.empty:
            pooled = pooled.copy()
            pooled["window_id"] = -1
            frames.append(pooled)
    if not frames:
        return _empty_reliability()
    out = pd.concat(frames, ignore_index=True)
    out["bin"] = out["bin"].astype("int64")
    out["prob_pred"] = out["prob_pred"].astype("float64")
    out["prob_true"] = out["prob_true"].astype("float64")
    out["count"] = out["count"].astype("int64")
    out["window_id"] = out["window_id"].astype("int64")
    return out[list(RELIABILITY_COLUMNS)].sort_values(
        ["window_id", "bin"]
    ).reset_index(drop=True)


def _assemble_scores(
    labels: pd.DataFrame,
    outcomes: np.ndarray,
    window_of_label: np.ndarray,
    score_state: dict[int, dict[str, Any]],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for i in range(len(labels)):
        state = score_state[i]
        if state is None:  # defensive: every label must be scored (D-02)
            state = {
                "window_id": int(window_of_label[i]),
                "p_win": _nan(),
                "score_source": "heuristic",
                "provenance": PROVENANCE_HEURISTIC,
            }
        rows.append(
            {
                "symbol": labels["symbol"].iloc[i],
                "timeframe": labels["timeframe"].iloc[i],
                "entry_time": labels["entry_time"].iloc[i],
                "direction": labels["direction"].iloc[i],
                "outcome": outcomes[i],
                "window_id": int(state["window_id"]),
                "p_win": float(state["p_win"]),
                "excluded": outcomes[i] == OUTCOME_TIMEOUT,
                "score_source": state["score_source"],
                "provenance": state["provenance"],
                "artifact_version": _nan(),
            }
        )
    frame = pd.DataFrame(rows, columns=list(SCORES_COLUMNS))
    frame["symbol"] = frame["symbol"].astype("string")
    frame["timeframe"] = frame["timeframe"].astype("string")
    frame["direction"] = frame["direction"].astype("string")
    frame["outcome"] = frame["outcome"].astype("string")
    frame["entry_time"] = frame["entry_time"].astype("datetime64[us]")
    frame["window_id"] = frame["window_id"].astype("int64")
    frame["p_win"] = frame["p_win"].astype("float64")
    frame["excluded"] = frame["excluded"].astype("bool")
    frame["score_source"] = frame["score_source"].astype("string")
    frame["provenance"] = frame["provenance"].astype("string")
    frame["artifact_version"] = frame["artifact_version"].astype("float64")
    return frame.reset_index(drop=True)
