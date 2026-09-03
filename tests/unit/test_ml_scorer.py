"""Unit tests for the loadable scorer (SC4 / Phase-6 seam / Pitfall 7).

Named tests pin the score surface and category-restoration necessity:
- ``test_load_scorer_via_latest_pointer_and_explicit_dir``
- ``test_score_single_row_matches_training_frame``
- ``test_score_rejects_missing_feature_columns``
- ``test_score_unseen_category_becomes_missing_with_warning``
- ``test_score_output_schema``
- ``test_contributors_shape_and_bias_column``

No MetaTrader5 import anywhere.
"""

from __future__ import annotations

import logging

import pandas as pd
import pytest
from _ml_fixtures import make_labels, ml_cfg, synthetic_feature_frame

from ai_trading.ml.artifact import build_bundle, save_artifact
from ai_trading.ml.features import FEATURE_NAMES, FEATURE_SPEC
from ai_trading.ml.folds import calibration_folds
from ai_trading.ml.scorer import load_scorer
from ai_trading.ml.train import fit_calibrated

_CAT_NAMES = [e["name"] for e in FEATURE_SPEC if e["dtype"] == "categorical"]


@pytest.fixture
def trained(tmp_path):
    """Save one artifact and return (models_root, X, y)."""
    cfg = ml_cfg(ml_n_estimators=15)
    n = 72  # 3 days of hourly entries -> two valid chronological folds
    seed = 11
    X = synthetic_feature_frame(n, seed=seed)
    y = pd.Series([i % 2 for i in range(n)], dtype="int64")
    entry = pd.date_range("2026-01-01 00:00", periods=n, freq="h")
    labels = make_labels(
        [
            {
                "symbol": "EURUSD",
                "timeframe": "M15",
                "direction": "long",
                "entry_time": e,
                "exit_time": e + pd.Timedelta(hours=1),
            }
            for e in entry
        ]
    )
    folds = calibration_folds(labels["entry_time"], labels["exit_time"], 1, 1)
    cal = fit_calibrated(X, y, folds, "sigmoid", cfg)
    cat_specs = {name: list(X[name].cat.categories) for name in _CAT_NAMES}
    bundle = build_bundle(
        model=cal,
        cfg=cfg,
        feature_names=list(FEATURE_NAMES),
        categorical_specs=cat_specs,
        cv_fold_summary={"n_folds": 2},
        training_window={"start": "2026-01-01", "end": "2026-01-03"},
        label_counts={"decided": n, "wins": n // 2, "losses": n // 2, "timeouts": 0},
        reliability_summary={"bins": 5, "n_points": n},
    )
    models_root = tmp_path / "models"
    vdir = save_artifact(bundle, models_root)
    return models_root, X, y, vdir


@pytest.mark.unit
def test_load_scorer_via_latest_pointer_and_explicit_dir(trained):
    models_root, X, _, vdir = trained
    s_root = load_scorer(models_root)
    s_dir = load_scorer(vdir)
    assert s_root.artifact_version == 1
    assert s_dir.artifact_version == 1
    pd.testing.assert_frame_equal(s_root.score(X), s_dir.score(X))


@pytest.mark.unit
def test_score_single_row_matches_training_frame(trained):
    models_root, X, _, _ = trained
    scorer = load_scorer(models_root)
    full = scorer.score(X)
    one = scorer.score(X.iloc[[7]])
    assert float(one["p_win"].iloc[0]) == float(full["p_win"].iloc[7])


@pytest.mark.unit
def test_score_rejects_missing_feature_columns(trained):
    models_root, X, _, _ = trained
    scorer = load_scorer(models_root)
    bad = X.drop(columns=["symbol"])
    with pytest.raises(ValueError, match="symbol"):
        scorer.score(bad)


@pytest.mark.unit
def test_score_unseen_category_becomes_missing_with_warning(trained, caplog):
    models_root, X, _, _ = trained
    scorer = load_scorer(models_root)
    Xs = X.copy()
    # Strip the category dtype so the unseen value is not silently absorbed.
    Xs["symbol"] = Xs["symbol"].astype(object)
    Xs.loc[0, "symbol"] = "UNSEEN"
    with caplog.at_level(logging.WARNING, logger="ai_trading.ml.scorer"):
        out = scorer.score(Xs)
    assert "unseen" in caplog.text.lower()
    assert len(out) == len(X)
    assert (out["p_win"] >= 0).all() and (out["p_win"] <= 1).all()


@pytest.mark.unit
def test_score_output_schema(trained):
    models_root, X, _, _ = trained
    scorer = load_scorer(models_root)
    out = scorer.score(X)
    assert list(out.columns) == ["p_win", "score_source", "artifact_version"]
    assert out["score_source"].eq("ml").all()
    assert out["p_win"].dtype == "float64"
    assert int(out["artifact_version"].iloc[0]) == 1
    assert int(out["artifact_version"].iloc[-1]) == 1


@pytest.mark.unit
def test_contributors_shape_and_bias_column(trained):
    models_root, X, _, _ = trained
    scorer = load_scorer(models_root)
    contrib = scorer.contributors(X)
    assert contrib.shape == (len(X), len(FEATURE_NAMES) + 1)
    assert contrib.columns[-1] == "bias"
    assert list(contrib.columns[:-1]) == list(FEATURE_NAMES)
    # Deterministic across calls.
    pd.testing.assert_frame_equal(contrib, scorer.contributors(X))
