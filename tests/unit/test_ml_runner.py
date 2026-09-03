"""Unit tests for the ML retrain CLI (plan 04-03): exit-code contract
({2 config, 1 runtime refusal, 0 success}), the label-count gate with an
actionable D-21-style message, the complete chain on a synthetic store
(labels -> gate -> features -> audit artifact -> windows -> per-window eval ->
final calibrated model -> versioned bundle + LATEST + three report parquets),
eval vs train mode, dry-run, all-windows-skipped, and the data-root traversal
guard. main(argv) is called directly — no subprocess, no MT5.

The synthetic store is built with the single project write path
(``bar_store.merge_and_write`` via ``write_bars_parquet`` and the Phase 3
``backtest.reports.write_labels`` label writer) — never a second Parquet
writer.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest
from _backtest_fixtures import make_bars, write_bars_parquet
from _ml_fixtures import make_labels
from test_backtest_config import _base_values
from test_backtest_config import _write_config as _write_toml

from ai_trading.backtest.reports import write_labels
from ai_trading.ml.runner import main as runner_main

SYMBOL = "EURUSD"
_START = datetime(2026, 8, 20, 0, 0)
_SL = 1.08
_TP = 1.20


def _write_config(tmp_path: Path, bars_dir, **overrides) -> Path:
    defaults = dict(
        bars_dir=str(bars_dir),
        ml_min_train_labels=6,
        ml_cal_train_days=1,
        ml_cal_test_days=1,
        wf_test_days=1,
        wf_train_days=2,
        ml_n_estimators=40,
        ml_num_leaves=5,
        ml_min_data_in_leaf=3,
    )
    return _write_toml(tmp_path, _base_values(tmp_path, **{**defaults, **overrides}))


def _store(data_root: Path, n_bars: int = 400, label_indices=None) -> Path:
    """Build a synthetic store (bars + labels) under ``data_root`` and return it.

    Labels are written via the Phase 3 ``write_labels`` path; entry indices
    must map to valid decision bars in the M15 frame. Outcomes alternate
    WIN/LOSS with a TIMEOUT every 5th label so both classes are present.
    """
    bars_dir = data_root / "bars"
    labels_dir = data_root / "labels"
    bars_dir.mkdir(parents=True, exist_ok=True)
    m15 = make_bars(SYMBOL, "M15", _START, n_bars)
    h1 = make_bars(SYMBOL, "H1", _START, max(4, n_bars // 16))
    h4 = make_bars(SYMBOL, "H4", _START, max(4, n_bars // 64))
    for tf, frame in (("M15", m15), ("H1", h1), ("H4", h4)):
        write_bars_parquet(frame, bars_dir / f"{SYMBOL}_{tf}.parquet")

    if label_indices is None:
        label_indices = list(range(20, n_bars - 10, 6))
    rows = []
    for k, i in enumerate(label_indices):
        e = m15["time_utc"].iloc[i]
        outcome = "TIMEOUT" if k % 5 == 0 else ("WIN" if k % 2 == 0 else "LOSS")
        rows.append(
            {
                "symbol": SYMBOL,
                "timeframe": "M15",
                "direction": "long",
                "entry_time": e,
                "exit_time": e + pd.Timedelta(hours=1),
                "sl_price": _SL,
                "tp_price": _TP,
                "outcome": outcome,
            }
        )
    labels = make_labels(rows)
    write_labels(labels, labels_dir, SYMBOL, "M15")
    return data_root


def _assert_report_shapes(data_root: Path):
    reports = data_root / "reports"
    assert (reports / "ml_walkforward.parquet").exists()
    assert (reports / "ml_reliability.parquet").exists()
    assert (reports / "ml_scores.parquet").exists()
    assert (reports / "feature_audit.json").exists()


@pytest.mark.unit
def test_full_train_run_exit_0_writes_artifacts(tmp_path, caplog):
    data_root = tmp_path / "data"
    _store(data_root, n_bars=400)
    cfg_path = _write_config(tmp_path, data_root / "bars", ml_min_train_labels=6)
    with caplog.at_level(logging.INFO):
        rc = runner_main(["--config", str(cfg_path), "--train", "--write"])
    assert rc == 0
    # Versioned bundle + LATEST pointer.
    models = data_root / "models"
    assert (models / "LATEST.json").exists()
    v = models / "pooled" / "v1"
    assert (v / "model.joblib").exists()
    assert (v / "manifest.json").exists()
    # The three report parquets + the feature audit artifact.
    _assert_report_shapes(data_root)


@pytest.mark.unit
def test_all_windows_skipped_exit_0(tmp_path, caplog):
    data_root = tmp_path / "data"
    # Decided rows concentrated on the final day -> every window's train is
    # below the gate threshold -> all skip (Pattern 5), score artifact heuristic.
    _store(data_root, n_bars=400, label_indices=list(range(300, 400, 2)))
    cfg_path = _write_config(
        tmp_path, data_root / "bars", ml_min_train_labels=15, ml_n_estimators=20
    )
    with caplog.at_level(logging.INFO):
        rc = runner_main(["--config", str(cfg_path), "--eval", "--write"])
    assert rc == 0
    report = pd.read_parquet(data_root / "reports" / "ml_walkforward.parquet")
    assert len(report) >= 1
    assert (report["status"] == "skipped").all()
    scores = pd.read_parquet(data_root / "reports" / "ml_scores.parquet")
    assert (scores["score_source"] == "heuristic").all()


@pytest.mark.unit
def test_missing_labels_dir_exit_1_actionable(tmp_path, caplog):
    data_root = tmp_path / "data"
    # Bars only — no data/labels/ directory at all.
    bars_dir = data_root / "bars"
    bars_dir.mkdir(parents=True, exist_ok=True)
    m15 = make_bars(SYMBOL, "M15", _START, 200)
    h1 = make_bars(SYMBOL, "H1", _START, 12)
    h4 = make_bars(SYMBOL, "H4", _START, 6)
    for tf, frame in (("M15", m15), ("H1", h1), ("H4", h4)):
        write_bars_parquet(frame, bars_dir / f"{SYMBOL}_{tf}.parquet")
    cfg_path = _write_config(tmp_path, data_root / "bars", ml_min_train_labels=6)
    with caplog.at_level(logging.INFO):
        rc = runner_main(["--config", str(cfg_path), "--train", "--write"])
    assert rc == 1
    combined = "\n".join(r.message for r in caplog.records)
    assert "label store not found" in combined
    assert "data/labels" in combined
    assert "ai_trading.backtest" in combined  # the Phase 3 backtest remedy
    assert "backfill" in combined  # the MT5 history-backfill prerequisite


@pytest.mark.unit
def test_gate_refusal_exit_1_names_counts_and_threshold(tmp_path, caplog):
    data_root = tmp_path / "data"
    # Too few decided rows for the gate threshold.
    _store(data_root, n_bars=200, label_indices=list(range(20, 80, 6)))
    cfg_path = _write_config(tmp_path, data_root / "bars", ml_min_train_labels=30)
    with caplog.at_level(logging.INFO):
        rc = runner_main(["--config", str(cfg_path), "--train", "--write"])
    assert rc == 1
    combined = "\n".join(r.message for r in caplog.records)
    assert "label-count gate" in combined
    assert "decided=" in combined
    assert "ml_min_train_labels=30" in combined
    assert "wins=" in combined and "losses=" in combined
    assert "backtest" in combined and "backfill" in combined


@pytest.mark.unit
def test_missing_mode_flag_exit_2(tmp_path):
    data_root = tmp_path / "data"
    _store(data_root, n_bars=200)
    cfg_path = _write_config(tmp_path, data_root / "bars")
    assert runner_main(["--config", str(cfg_path)]) == 2


@pytest.mark.unit
def test_config_error_exit_2(tmp_path):
    assert runner_main(["--config", str(tmp_path / "nope.toml"), "--train"]) == 2


@pytest.mark.unit
def test_eval_mode_writes_reports_not_artifact(tmp_path, caplog):
    data_root = tmp_path / "data"
    _store(data_root, n_bars=400)
    cfg_path = _write_config(tmp_path, data_root / "bars", ml_min_train_labels=6)
    with caplog.at_level(logging.INFO):
        rc = runner_main(["--config", str(cfg_path), "--eval", "--write"])
    assert rc == 0
    _assert_report_shapes(data_root)
    # No versioned artifact was written (eval mode).
    models = data_root / "models"
    assert not (models / "LATEST.json").exists()
    assert not (models / "pooled").exists()


@pytest.mark.unit
def test_dry_run_writes_nothing(tmp_path, capsys):
    data_root = tmp_path / "data"
    _store(data_root, n_bars=400)
    cfg_path = _write_config(tmp_path, data_root / "bars", ml_min_train_labels=6)
    rc = runner_main(["--config", str(cfg_path), "--train"])
    out = capsys.readouterr().out
    assert rc == 0
    # No --write: zero artifacts created, summary still printed.
    assert not (data_root / "reports" / "ml_walkforward.parquet").exists()
    assert not (data_root / "models" / "LATEST.json").exists()
    assert not (data_root / "models" / "pooled").exists()
    assert "ml pipeline summary" in out


@pytest.mark.unit
def test_output_dir_traversal_refused(tmp_path):
    data_root = tmp_path / "data"
    data_root.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (data_root / "reports").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("directory symlinks unavailable on this platform")
    _store(data_root, n_bars=200)
    cfg_path = _write_config(tmp_path, data_root / "bars")
    assert runner_main(["--config", str(cfg_path), "--eval", "--write"]) == 1
