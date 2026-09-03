"""Unit tests for the versioned artifact bundle (SC4 / T-04-01): build shape,
atomic versioned save, JSON manifest, LATEST pointer, and loader validation.

Named tests pin:
- ``test_save_artifact_versions_increment_and_latest_pointer``: two saves
  produce v1 then v2; LATEST.json points at v2 with a matching config_hash.
- ``test_bundle_required_keys``: every SC4 key present, incl. ``reliability_summary``
  and the save-stamped ``artifact_version``.
- ``test_manifest_json_is_pickle_free``: manifest.json parses as JSON and
  carries the metadata but no pickled model object.
- ``test_atomic_writes_leave_no_tmp``: no ``.tmp`` siblings survive success.
- ``test_load_rejects_schema_version_mismatch`` / ``feature_list_mismatch`` /
  ``major_library_mismatch`` (the minor-mismatch path warns but loads).

No MetaTrader5 import anywhere; tiny trees keep writes fast.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from _ml_fixtures import make_labels, ml_cfg, synthetic_feature_frame

from ai_trading.ml.artifact import (
    ARTIFACT_SCHEMA_VERSION,
    REQUIRED_BUNDLE_KEYS,
    build_bundle,
    load_artifact,
    save_artifact,
)
from ai_trading.ml.features import FEATURE_NAMES, FEATURE_SPEC
from ai_trading.ml.folds import calibration_folds
from ai_trading.ml.train import fit_calibrated

_CAT_NAMES = [e["name"] for e in FEATURE_SPEC if e["dtype"] == "categorical"]


def _fitted(seed: int = 5):
    """Fit a tiny deterministic calibrator (2 chronological folds) on a synthetic
    decided frame; returns (cfg, X, y, calibrator)."""
    cfg = ml_cfg(ml_n_estimators=15)
    n = 72  # 3 days of hourly entries -> two valid chronological folds
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
    return cfg, X, y, cal


def _cat_specs(X: pd.DataFrame) -> dict:
    return {name: list(X[name].cat.categories) for name in _CAT_NAMES}


def _bundle(seed: int = 5) -> dict:
    cfg, X, y, cal = _fitted(seed)
    return build_bundle(
        model=cal,
        cfg=cfg,
        feature_names=list(FEATURE_NAMES),
        categorical_specs=_cat_specs(X),
        cv_fold_summary={"n_folds": 2},
        training_window={"start": "2026-01-01", "end": "2026-01-03"},
        label_counts={"decided": 48, "wins": 24, "losses": 24, "timeouts": 0},
        reliability_summary={"bins": 5, "n_points": 48},
    )


@pytest.fixture
def saved(tmp_path) -> Path:
    """A models root with one saved artifact (v1) plus its (cfg, X, y) for reuse."""
    bundle = _bundle()
    models = save_artifact(bundle, tmp_path / "models")
    cfg, X, _, _ = _fitted(5)
    return models  # the version directory path


@pytest.mark.unit
def test_save_artifact_versions_increment_and_latest_pointer(tmp_path):
    bundle = _bundle(seed=3)
    models_dir = tmp_path / "models"
    v1 = save_artifact(bundle, models_dir)
    v2 = save_artifact(bundle, models_dir)
    assert v1.name == "v1" and v2.name == "v2"
    latest = models_dir / "LATEST.json"
    pointer = json.loads(latest.read_text(encoding="utf-8"))
    assert pointer["artifact_version"] == 2
    assert Path(pointer["path"]) == v2
    assert pointer["config_hash"] == bundle["config_hash"]


@pytest.mark.unit
def test_bundle_required_keys(tmp_path):
    bundle = _bundle()
    for key in REQUIRED_BUNDLE_KEYS:
        assert key in bundle, f"bundle missing {key}"
    assert "reliability_summary" in bundle
    # build_bundle does NOT stamp artifact_version; save_artifact does.
    assert "artifact_version" not in bundle
    saved = save_artifact(bundle, tmp_path / "models")
    stamped = load_artifact(saved / "model.joblib")
    assert stamped["artifact_version"] == 1
    assert stamped["reliability_summary"] == {"bins": 5, "n_points": 48}


@pytest.mark.unit
def test_manifest_json_is_pickle_free(tmp_path):
    bundle = _bundle()
    vdir = save_artifact(bundle, tmp_path / "models")
    manifest = json.loads((vdir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["feature_names"] == list(FEATURE_NAMES)
    assert manifest["method"] == "sigmoid"
    assert manifest["seeds"] == 42
    assert manifest["config_hash"] == bundle["config_hash"]
    assert manifest["reliability_summary"] == {"bins": 5, "n_points": 48}
    assert "model" not in manifest
    assert "joblib" not in json.dumps(manifest)


@pytest.mark.unit
def test_atomic_writes_leave_no_tmp(tmp_path):
    bundle = _bundle()
    vdir = save_artifact(bundle, tmp_path / "models")
    (tmp_path / "models" / "pooled" / "v1").mkdir(parents=True, exist_ok=True)
    leftovers = list((tmp_path / "models").rglob("*.tmp"))
    assert leftovers == []
    assert (vdir / "model.joblib").exists()
    assert (vdir / "manifest.json").exists()


@pytest.mark.unit
def test_load_rejects_schema_version_mismatch(tmp_path):
    bundle = _bundle()
    bundle["artifact_schema_version"] = ARTIFACT_SCHEMA_VERSION + 1
    path = tmp_path / "model.joblib"
    import joblib

    joblib.dump(bundle, path)
    with pytest.raises(ValueError, match="artifact_schema_version"):
        load_artifact(path)


@pytest.mark.unit
def test_load_rejects_feature_list_mismatch(tmp_path):
    from ai_trading.ml.features import FEATURE_LIST_VERSION

    bundle = _bundle()
    bundle["feature_list_version"] = FEATURE_LIST_VERSION + 1
    path = tmp_path / "model.joblib"
    import joblib

    joblib.dump(bundle, path)
    with pytest.raises(ValueError, match="feature_list_version"):
        load_artifact(path)


@pytest.mark.unit
def test_load_rejects_major_library_mismatch(tmp_path, caplog):
    import logging

    import joblib

    bundle = _bundle()
    # Major mismatch -> refuse.
    bundle["sklearn_version"] = "99.0.0"
    path = tmp_path / "major.joblib"
    joblib.dump(bundle, path)
    with pytest.raises(ValueError, match="major version mismatch"):
        load_artifact(path)

    # Same major, different patch -> warns and loads.
    bundle2 = _bundle()
    bundle2["sklearn_version"] = "1.9.1"  # same major (1), different patch
    path2 = tmp_path / "minor.joblib"
    joblib.dump(bundle2, path2)
    with caplog.at_level(logging.WARNING, logger="ai_trading.ml.artifact"):
        loaded = load_artifact(path2)
    assert loaded["sklearn_version"] == "1.9.1"
    assert any("version differs" in r.message.lower() for r in caplog.records)
