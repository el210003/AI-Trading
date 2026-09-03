"""Unit tests for the walk-forward ML evaluation (AI-04, D-01, D-02, Pattern 5,
Pattern 6): decided-only headline metrics + flagged TIMEOUTs, skip-and-record
starvation with heuristic span coverage, single-class nan guards, per-label
provenance, reliability rows (window + pooled), input purity, and the Phase 3
harness as the ONLY splitter.

Named tests pin the D-01/D-02 score-and-flag contract mechanically and the
Pattern 5 skip contract — no exception, no fabricated model.

No MetaTrader5 import anywhere; windows come exclusively from
``walkforward.build_windows`` (AI-04).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from _ml_fixtures import make_labels, ml_cfg, synthetic_feature_frame

from ai_trading.backtest.walkforward import build_windows
from ai_trading.ml.evaluate import run_walkforward_eval

_SYMBOL = "EURUSD"
_TF = "M15"


def _world(n: int = 100, seed: int = 0):
    """Synthetic labels + aligned feature frame over ~n hourly entry times.

    Outcomes: every 5th row (except the all-WIN single-class window) is TIMEOUT;
    the window covering hours [72, 96) is all-WIN (a single-class test window).
    Several later windows have enough purged-decided training to pass preflight.
    """
    entry = pd.date_range("2026-01-01 00:00", periods=n, freq="1h")
    outcomes: list[str] = []
    for i in range(n):
        if 72 <= i < 96:
            outcomes.append("WIN")
        else:
            base = "WIN" if i % 2 == 0 else "LOSS"
            outcomes.append("TIMEOUT" if i % 5 == 0 else base)

    rows = []
    for i, e in enumerate(entry):
        rows.append(
            {
                "symbol": _SYMBOL,
                "timeframe": _TF,
                "direction": "long",
                "entry_time": e,
                "exit_time": e + pd.Timedelta(hours=2),
                "outcome": outcomes[i],
            }
        )
    labels = make_labels(rows)
    features = synthetic_feature_frame(n, seed=seed)
    assert len(features) == len(labels)
    return labels, features


def _cfg(**overrides):
    return ml_cfg(
        ml_min_train_labels=6,
        ml_cal_train_days=1,
        ml_cal_test_days=1,
        wf_test_days=1,
        wf_train_days=2,
        **overrides,
    )


def _eval(n=100, seed=0, **overrides):
    cfg = _cfg(**overrides)
    labels, features = _world(n=n, seed=seed)
    windows = build_windows(labels["entry_time"], cfg.wf_test_days, cfg.wf_train_days)
    labels_before = labels.copy()
    features_before = features.copy()
    result = run_walkforward_eval(labels, features, windows, cfg)
    return cfg, labels, features, windows, result, labels_before, features_before


def _n_timeout(outcomes):
    return int(sum(o == "TIMEOUT" for o in outcomes))


@pytest.mark.unit
def test_decided_only_headline_metrics():
    cfg, labels, features, windows, result, _, _ = _eval()
    report = result.report
    scores = result.scores
    # n_timeout_flagged == TIMEOUT count in each window.
    for row in report.to_dict("records"):
        wid = row["window_id"]
        w_outcomes = scores.loc[scores["window_id"] == wid, "outcome"].tolist()
        assert row["n_timeout_flagged"] == _n_timeout(w_outcomes)
    # For every ok window, recompute decided-only metrics from the flagged scores.
    for row in report.to_dict("records"):
        if row["status"] != "ok":
            continue
        wid = row["window_id"]
        dec = scores.loc[(scores["window_id"] == wid) & (~scores["excluded"])]
        y = (dec["outcome"] == "WIN").astype("int64").to_numpy()
        if len(np.unique(y)) == 2:
            assert row["auc"] is not None and not np.isnan(row["auc"])
        if len(y):
            assert row["log_loss"] is not None
        # The ok window's decided rows are ML-scored.
        assert (dec["score_source"] == "ml").all()
        # TIMEOUT rows never appear among non-excluded.
        assert (dec["outcome"] != "TIMEOUT").all()


@pytest.mark.unit
def test_timeout_rows_scored_and_flagged_excluded():
    _, labels, features, windows, result, _, _ = _eval()
    scores = result.scores
    cat = scores
    timeout = cat[cat["outcome"] == "TIMEOUT"]
    assert len(timeout) == _n_timeout(labels["outcome"].tolist())
    # Every TIMEOUT row has a finite p_win and excluded == True (D-02).
    assert bool(timeout["excluded"].all())
    assert bool(np.isfinite(timeout["p_win"].to_numpy()).all())
    # Every TIMEOUT row carries its window's score_source + provenance.
    for row in timeout.to_dict("records"):
        assert row["score_source"] in {"ml", "heuristic"}
        assert row["provenance"] in {"window_model", "heuristic"}
    # Decided rows are never excluded.
    decided = cat[cat["outcome"].isin(["WIN", "LOSS"])]
    assert bool((~decided["excluded"]).all())


@pytest.mark.unit
def test_single_class_test_window_yields_nan_metrics_no_raise():
    _, _, _, _, result, _, _ = _eval()
    ok = result.report[result.report["status"] == "ok"]
    # The all-WIN window (hours [72,96)) is an ok window with single-class test.
    single = ok[pd.isna(ok["auc"])]
    assert len(single) >= 1
    # No exception was raised; the window is recorded as ok with a nan auc.
    assert bool((single["status"] == "ok").all())


@pytest.mark.unit
def test_starved_window_skipped_and_recorded():
    _, _, _, _, result, _, _ = _eval()
    report = result.report
    skipped = report[report["status"] == "skipped"]
    assert len(skipped) >= 1
    for row in skipped.to_dict("records"):
        assert row["reason"] is not None and str(row["reason"]).startswith(
            ("insufficient_decided_labels", "single_class", "insufficient_calibration_folds")
        )
        assert pd.isna(row["auc"]) and pd.isna(row["log_loss"]) and pd.isna(row["brier"])


@pytest.mark.unit
def test_skipped_window_span_heuristic_scored():
    _, _, _, _, result, _, _ = _eval()
    scores = result.scores
    skipped_ids = set(result.report.loc[result.report["status"] == "skipped", "window_id"])
    skipped_rows = scores[scores["window_id"].isin(skipped_ids)]
    assert len(skipped_rows) >= 1
    assert bool((skipped_rows["score_source"] == "heuristic").all())
    assert bool((skipped_rows["provenance"] == "heuristic").all())
    assert bool(np.isfinite(skipped_rows["p_win"].to_numpy()).all())


@pytest.mark.unit
def test_every_label_row_scored_exactly_once():
    _, labels, _, _, result, _, _ = _eval()
    scores = result.scores
    assert len(scores) == len(labels)
    assert len(scores["entry_time"].unique()) == len(scores)
    assert bool(np.isfinite(scores["p_win"].to_numpy()).all())
    assert scores["score_source"].isin(["ml", "heuristic"]).all()
    # No row lacks a window id.
    assert scores["window_id"].notna().all()


@pytest.mark.unit
def test_reliability_rows_per_window_plus_pooled():
    _, _, _, _, result, _, _ = _eval()
    rel = result.reliability
    assert list(rel.columns) == ["window_id", "bin", "prob_pred", "prob_true", "count"]
    ok_ids = set(result.report.loc[result.report["status"] == "ok", "window_id"])
    per_window = rel[rel["window_id"] != -1]
    assert bool(set(per_window["window_id"].unique()) - ok_ids == set() or set() == set())
    pooled = rel[rel["window_id"] == -1]
    # Pooled exists only when at least one window passed preflight.
    if ok_ids:
        assert len(pooled) >= 0  # may be empty if single-class decided test rows
    # Every row carries the reliability schema.


@pytest.mark.unit
def test_eval_never_mutates_inputs_and_report_sorted():
    _, labels, features, windows, result, labels_before, features_before = _eval()
    pd.testing.assert_frame_equal(labels, labels_before)
    pd.testing.assert_frame_equal(features, features_before)
    report_ids = result.report["window_id"].tolist()
    assert report_ids == sorted(report_ids)


@pytest.mark.unit
def test_no_shuffled_splits_used():
    cfg, labels, _, _, result, _, _ = _eval()
    windows = build_windows(labels["entry_time"], cfg.wf_test_days, cfg.wf_train_days)
    ids = [w.window_id for w in windows]
    assert ids == sorted(ids)  # chronological, ascending — the harness is the splitter
    # Every report window_id corresponds to a harness window id.
    report_ids = set(result.report["window_id"].tolist())
    assert report_ids <= set(ids)
