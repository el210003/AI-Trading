"""Unit tests for the training core (AI-02/AI-03/SC2/SC3, D-01): decided-only
target, preflight gate, deterministic LightGBM, chronological-fold calibration,
and the reliability-curve helper.

Named tests pin:
- ``decided_mask`` excludes the third outcome class (D-01)
- preflight reason prefixes for starvation / single-class / insufficient folds
- byte-identical deterministic ``predict_proba`` across refits
- no imbalance reweighting flags in ``lgbm_params`` (T-04-08)
- ``fit_calibrated`` requires EXACTLY explicit chronological folds (SC3) — the
  ``folds`` parameter has no default and every ``CalibratedClassifierCV`` call
  passes ``cv``+``ensemble=True`` (AST static guard)
- end-to-end sigmoid calibration returns probabilities in [0, 1]
- ``reliability_curve`` schema + counts + empty-frame guard

No MetaTrader5 import anywhere; tiny trees keep the module under the ~30s budget.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from _ml_fixtures import make_labels, ml_cfg, synthetic_feature_frame

from ai_trading.ml.folds import calibration_folds
from ai_trading.ml.train import (
    decided_mask,
    fit_calibrated,
    fit_lightgbm,
    lgbm_params,
    preflight_reason,
    reliability_curve,
)

_SRC_TRAIN = (
    Path(__file__).resolve().parents[2] / "src" / "ai_trading" / "ml" / "train.py"
)


def _imbalance_keys() -> set[str]:
    return {"is_unbalance", "scale_pos_weight"}


@pytest.mark.unit
def test_decided_mask_excludes_third_class():
    outcomes = pd.Series(["WIN", "LOSS", "TIMEOUT", "WIN", "TIMEOUT"])
    mask = decided_mask(outcomes)
    assert list(mask) == [True, True, False, True, False]


@pytest.mark.unit
def test_preflight_reason_insufficient_decided_labels():
    y = pd.Series([0, 1])
    reason = preflight_reason(y, min_labels=30, folds=None)
    assert reason is not None and reason.startswith("insufficient_decided_labels")


@pytest.mark.unit
def test_preflight_reason_single_class():
    y = pd.Series([0, 0, 0, 0, 0])
    reason = preflight_reason(y, min_labels=3, folds=None)
    assert reason is not None and reason.startswith("single_class")


@pytest.mark.unit
def test_preflight_reason_insufficient_calibration_folds():
    y = pd.Series([0, 1, 0, 1, 0, 1])  # both classes, count >= min
    # Both fold test blocks are single-class -> zero viable folds.
    folds = [([4], [0, 2]), ([0], [1, 3])]
    reason = preflight_reason(y, min_labels=3, folds=folds)
    assert reason is not None and reason.startswith("insufficient_calibration_folds")


@pytest.mark.unit
def test_preflight_passes_returns_none():
    y = pd.Series([0, 1, 0, 1, 0, 1, 0, 1])
    folds = [([0, 1], [2, 3]), ([0, 1, 2, 3], [4, 5]), ([0, 3], [6, 7])]
    assert preflight_reason(y, min_labels=3, folds=folds) is None


@pytest.mark.unit
def test_fit_lightgbm_deterministic_probabilities():
    cfg = ml_cfg(ml_n_estimators=40)
    X = synthetic_feature_frame(100, seed=0)
    y = pd.Series([0, 1] * 50, dtype="int64")
    m1 = fit_lightgbm(X, y, cfg)
    m2 = fit_lightgbm(X, y, cfg)
    assert np.array_equal(m1.predict_proba(X), m2.predict_proba(X))


@pytest.mark.unit
def test_lgbm_params_no_imbalance_flags():
    cfg = ml_cfg()
    params = lgbm_params(cfg)
    assert params["objective"] == "binary"
    assert params["boosting"] == "gbdt"
    assert params["deterministic"] is True
    assert params["force_row_wise"] is True
    assert params["num_threads"] == 1
    assert params["random_state"] == cfg.ml_random_state
    assert _imbalance_keys().isdisjoint(params), "imbalance flags distort probabilities"


@pytest.mark.unit
def test_fit_calibrated_requires_explicit_folds():
    cfg = ml_cfg(ml_n_estimators=20)
    X = synthetic_feature_frame(30, seed=1)
    y = pd.Series([0, 1] * 15, dtype="int64")
    with pytest.raises(ValueError):
        fit_calibrated(X, y, [], "sigmoid", cfg)  # empty folds
    with pytest.raises(ValueError):
        fit_calibrated(X, y, [([0, 1], [2, 3])], "sigmoid", cfg)  # single fold
    # Structural SC3 rule: the folds parameter carries NO default.
    sig = inspect.signature(fit_calibrated)
    assert sig.parameters["folds"].default is inspect.Parameter.empty


@pytest.mark.unit
def test_fit_calibrated_end_to_end_sigmoid():
    cfg = ml_cfg(ml_n_estimators=30)
    n = 72  # 3 days of hourly entries -> two valid expanding/sequential folds
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
    # Alternating target so every fold train/test block carries both classes.
    y = pd.Series([i % 2 for i in range(n)], dtype="int64")
    X = synthetic_feature_frame(n, seed=7)
    folds = calibration_folds(labels["entry_time"], labels["exit_time"], 1, 1)
    assert len(folds) >= 2
    calibrated = fit_calibrated(X, y, folds, "sigmoid", cfg)
    p = calibrated.predict_proba(X)[:, 1]
    assert p.shape == (n,)
    assert bool(((p >= 0) & (p <= 1)).all())


@pytest.mark.unit
def test_no_default_cv_call_sites():
    """AST static guard: every CalibratedClassifierCV call in ml/train.py passes
    an explicit ``cv`` and ``ensemble=True`` (the SC3 no-shuffle rule)."""
    from ai_trading.ml import train as train_mod

    tree = ast.parse(Path(_SRC_TRAIN).read_text(encoding="utf-8"))
    calls = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name == "CalibratedClassifierCV":
            calls.append(node)
    assert calls, "no CalibratedClassifierCV call site found in ml/train.py"
    for call in calls:
        kws = {k.arg: k.value for k in call.keywords if k.arg is not None}
        assert "cv" in kws, "CalibratedClassifierCV must pass an explicit cv iterable"
        ens = kws.get("ensemble")
        assert isinstance(ens, ast.Constant) and ens.value is True, "ensemble must be True"
    # The source module constructs the calibrator with cv=folds (a Name read).
    assert train_mod.fit_calibrated is not None


@pytest.mark.unit
def test_reliability_curve_shape_and_counts():
    y = pd.Series([0, 1, 0, 1, 0, 1, 0, 1, 0, 1], dtype="int64")
    p = np.linspace(0.1, 0.9, len(y))
    rf = reliability_curve(y, p, n_bins=5)
    assert list(rf.columns) == ["bin", "prob_pred", "prob_true", "count"]
    assert rf["bin"].dtype == "int64"
    assert rf["prob_pred"].dtype == "float64"
    assert rf["prob_true"].dtype == "float64"
    assert rf["count"].dtype == "int64"
    assert int(rf["count"].sum()) == len(y)
    # Guard: single-class input returns a schema-correct EMPTY frame.
    rf2 = reliability_curve(pd.Series([0, 0, 0], dtype="int64"), np.array([0.3, 0.5, 0.7]))
    assert rf2.empty
    assert list(rf2.columns) == ["bin", "prob_pred", "prob_true", "count"]
    # Guard: fewer than two distinct predicted values also returns empty.
    rf3 = reliability_curve(y, np.full(len(y), 0.5))
    assert rf3.empty
    assert list(rf3.columns) == ["bin", "prob_pred", "prob_true", "count"]
