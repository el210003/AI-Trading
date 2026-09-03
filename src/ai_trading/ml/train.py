"""Training core: decided-only target, preflight gate, deterministic LightGBM,
chronological-fold calibration, reliability helper (AI-02/AI-03/SC2/SC3, D-01).

This module is the PURE training tier — given decided feature/target frames it
fits and calibrates, with no file I/O and no MetaTrader5 import (Phase 4 runner
tier does persistence and walk-forward bookkeeping).

CONVENTIONS (pinned by named tests in test_ml_train.py):

- D-01 DECIDED-ONLY TARGET: the model predicts binary P(WIN) AMONG DECIDED
  trades. ``decided_mask``/``preflight_reason`` confine fitting to
  ``outcome in {WIN, LOSS}``; TIMEOUT rows are scored-and-flagged downstream
  (D-02), never fit against.
- SC3 NO SHUFFLED SPLITS: ``fit_calibrated`` receives an EXPLICIT chrono
  fold iterable (from ``ml.folds.calibration_folds``) as a REQUIRED positional
  argument with no default, and passes ``cv=folds`` with ``ensemble=True``.
  ``cv=None``/``cv=int`` would silently select ``StratifiedKFold`` — a
  class-stratified round-robin that destroys time ordering. ``ensemble=False``
  is a verified partition error on expanding folds. Both are therefore
  structurally impossible at the call sites (AST-pinned).
- DETERMINISM: ``lgbm_params`` sets ``deterministic=True``,
  ``force_row_wise=True``, ``num_threads=1``, a fixed ``random_state`` and
  ``boosting='gbdt'`` — retraining on identical inputs/seeds reproduces
  byte-identical ``predict_proba`` (T-04-05).
- NO IMBALANCE REWEIGHTING (T-04-08): ``is_unbalance`` / ``scale_pos_weight``
  are DELIBERATELY omitted. LightGBM's own docs state they damage individual
  class-probability estimates — the exact quantity this phase produces. Among
  decided trades at R:R >= 1 the imbalance is mild, and calibration handles the
  residual probability mapping.
- PATTERN 5 PREFLIGHT: starvation / single-class windows return a stable reason
  prefix and are skipped upstream — never an exception, never a fabricated
  model. ``CalibratedClassifierCV`` needs at least two viable folds.

``reliability_curve`` wraps ``sklearn.calibration.calibration_curve``
(``strategy='quantile'``) into a schema-stable DataFrame — the SC2 reliability
data source the runner persists per window.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.calibration import CalibratedClassifierCV, calibration_curve

from ai_trading.backtest.barriers import OUTCOME_LOSS, OUTCOME_WIN
from ai_trading.ml.features import FEATURE_SPEC

_CATEGORICAL_NAMES = frozenset(
    entry["name"] for entry in FEATURE_SPEC if entry["dtype"] == "categorical"
)


def _cast_categoricals(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with every FEATURE_SPEC categorical column cast to
    ``pd.CategoricalDtype`` LightGBM auto-detects (idempotent)."""
    out = frame.copy()
    for name in _CATEGORICAL_NAMES:
        if name in out.columns:
            out[name] = out[name].astype("category")
    return out


def decided_mask(outcomes: pd.Series) -> pd.Series:
    """Boolean Series — True where the outcome is WIN or LOSS (decided; D-01).

    TIMEOUT (and any unrecognized/NA outcome) rows are excluded: the training
    target is binary among decided trades.
    """
    outcomes = pd.Series(outcomes)
    return outcomes.isin([OUTCOME_WIN, OUTCOME_LOSS])


def _both_classes(labels: pd.Series) -> bool:
    labels = pd.Series(labels).dropna()
    return labels.nunique() >= 2


def preflight_reason(
    y_decided: pd.Series, min_labels: int, folds: list | None = None
) -> str | None:
    """Return a stable-prefix reason string when training must be SKIPPED, else
    ``None`` (Pattern 5 — skip+record upstream, never raise, never fabricate).

    Checks in order:
    1. decided count ``< min_labels`` -> ``"insufficient_decided_labels"``
    2. fewer than two classes among decided labels -> ``"single_class"``
    3. (when ``folds`` given) fewer than two folds remain after dropping folds
       whose test block is single-class -> ``"insufficient_calibration_folds"``

    Each reason carries the observed numbers for the skip+record log.
    """
    y = pd.Series(y_decided)
    n = int(len(y))
    if n < min_labels:
        return (
            f"insufficient_decided_labels: {n} decided < min_labels {min_labels}"
        )
    if not _both_classes(y):
        present = sorted({str(v) for v in set(y.tolist())})
        return f"single_class: decided labels all in {present}"
    if folds is not None:
        viable = 0
        for _train_pos, test_pos in folds:
            test_labels = y.iloc[list(test_pos)]
            if _both_classes(test_labels):
                viable += 1
        if viable < 2:
            return (
                f"insufficient_calibration_folds: only {viable} fold(s) have both "
                "classes in their test block (need >= 2)"
            )
    return None


def lgbm_params(cfg) -> dict:
    """Deterministic LightGBM binary parameters (D-01 target, T-04-05).

    Deliberately OMITS the imbalance-reweighting knobs (``is_unbalance`` /
    ``scale_pos_weight``): LightGBM's own documentation warns they damage
    individual class-probability estimates, which is the exact quantity this
    phase produces. Among decided trades at R:R >= 1 the imbalance is mild and
    calibration maps the residual.
    """
    return {
        "objective": "binary",
        "n_estimators": cfg.ml_n_estimators,
        "num_leaves": cfg.ml_num_leaves,
        "min_data_in_leaf": cfg.ml_min_data_in_leaf,
        "learning_rate": cfg.ml_learning_rate,
        "random_state": cfg.ml_random_state,
        "deterministic": True,
        "force_row_wise": True,
        "num_threads": 1,
        "verbose": -1,
        "boosting": "gbdt",
    }


def fit_lightgbm(X: pd.DataFrame, y: pd.Series, cfg) -> LGBMClassifier:
    """Fit a deterministic LightGBM binary classifier on ``(X, y)``.

    Casts the FEATURE_SPEC categorical columns to ``pd.CategoricalDtype``
    (idempotent — LightGBM aligns categories via the categorical dtype) and
    fits with :func:`lgbm_params`'s deterministic parameter set. ``y`` is
    assumed to be decided (D-01).
    """
    X_cat = _cast_categoricals(X)
    model = LGBMClassifier(**lgbm_params(cfg))
    model.fit(X_cat, y)
    return model


def fit_calibrated(
    X: pd.DataFrame, y: pd.Series, folds: list, method: str, cfg
) -> CalibratedClassifierCV:
    """Fit a ``CalibratedClassifierCV`` over ``(X, y)`` with explicit chronology.

    Args:
        X: feature frame (decided rows).
        y: binary target (decided rows — D-01).
        folds: REQUIRED positional iterable of ``(train, test)`` index pairs
            from ``ml.folds.calibration_folds``. It has no default: the SC3
            no-shuffle rule is structural, not a convention (AST-pinned).
        method: calibration method ("sigmoid" default, "isotonic" for later).
        cfg: frozen Config for the LightGBM hyperparameters.

    Raises:
        ValueError: when ``len(folds) < 2`` — a single viable fold cannot
            calibrate and is a skip/refuse condition, never a silent
            uncalibrated fallback (SC2).

    ``cv=folds`` + ``ensemble=True`` is the verified-correct chronological
    shape: ``ensemble=False`` routes through ``cross_val_predict``, which
    demands partitions and raises on expanding chronology.
    """
    if not folds or len(folds) < 2:
        raise ValueError(
            "fit_calibrated requires at least two explicit chronological folds "
            f"(got {len(folds) if folds is not None else 0}) — a single viable "
            "fold cannot calibrate; return a skip reason instead"
        )
    X_cat = _cast_categoricals(X)
    calibrator = CalibratedClassifierCV(
        estimator=fit_lightgbm(X_cat, y, cfg),
        method=method,
        cv=folds,
        ensemble=True,
    )
    calibrator.fit(X_cat, y)
    return calibrator


def _empty_reliability_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "bin": pd.Series(dtype="int64"),
            "prob_pred": pd.Series(dtype="float64"),
            "prob_true": pd.Series(dtype="float64"),
            "count": pd.Series(dtype="int64"),
        }
    )


def reliability_curve(
    y_true: pd.Series, p_pred: pd.Series, n_bins: int = 5
) -> pd.DataFrame:
    """Per-bin calibration curve via ``calibration_curve(strategy='quantile')``.

    Returns a schema-stable DataFrame with columns ``bin`` (int64),
    ``prob_pred``/``prob_true`` (float64) and ``count`` (int64 per bin) — the
    SC2 reliability rows the runner persists per window.

    Guard: a single-class target OR fewer than two distinct predicted values
    returns a schema-correct EMPTY frame (the nan-with-reason convention;
    never raises).
    """
    y = pd.Series(pd.to_numeric(y_true, errors="coerce"), dtype="int64").dropna()
    p = pd.Series(pd.to_numeric(p_pred, errors="coerce"), dtype="float64")
    if not _both_classes(y) or p.nunique() < 2:
        return _empty_reliability_frame()

    y_np = y.to_numpy()
    p_np = p.to_numpy()
    prob_true, prob_pred = calibration_curve(
        y_np, p_np, n_bins=n_bins, strategy="quantile"
    )
    k = len(prob_true)
    edges = np.unique(np.quantile(p_np, np.linspace(0.0, 1.0, n_bins + 1)))
    binid = np.searchsorted(edges, p_np, side="right") - 1
    binid = np.clip(binid, 0, k - 1)
    counts = np.bincount(binid, minlength=k)[:k]

    return pd.DataFrame(
        {
            "bin": np.arange(k, dtype="int64"),
            "prob_pred": pd.Series(prob_pred, dtype="float64"),
            "prob_true": pd.Series(prob_true, dtype="float64"),
            "count": pd.Series(counts, dtype="int64"),
        }
    )
