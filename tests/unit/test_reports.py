"""Unit tests for the label/canonical artifact writers: the atomic
tmp + os.replace discipline copied from bar_store (no .tmp residue, even on
failed writes), byte determinism across re-runs, idempotent
(symbol, entry_time) overwrite, label/manifest separation, and config-hash
stability. Mirrors test_idempotent_store.py conventions; tmp_path throughout."""

from __future__ import annotations

import json

import pandas as pd
import pytest
from _backtest_fixtures import bt_cfg

from ai_trading.backtest.replay import LABEL_COLUMNS, _empty_labels_frame
from ai_trading.backtest.reports import (
    config_hash,
    write_canonical_stats,
    write_labels,
    write_run_manifest,
)

SYMBOL = "EURUSD"
TIMEFRAME = "M15"


def _labels(n: int = 3) -> pd.DataFrame:
    """Minimal schema-complete label frame with deterministic values."""
    rows = []
    for i in range(n):
        rows.append(
            {
                "symbol": SYMBOL,
                "timeframe": TIMEFRAME,
                "direction": "long",
                "entry_time": pd.Timestamp("2026-08-20 00:00:00") + pd.Timedelta(minutes=15 * i),
                "entry_price": 1.10000,
                "sl_price": 1.09900,
                "tp_price": 1.10200,
                "rr": 2.0,
                "pool_id": f"P{i}",
                "event_id": f"E{i}",
                "zone_id": f"Z{i}",
                "bias_h1": "bullish",
                "bias_h4": pd.NA,
                "outcome": "WIN",
                "exit_time": pd.Timestamp("2026-08-20 12:00:00") + pd.Timedelta(minutes=15 * i),
                "exit_price": 1.10200,
                "exit_idx": 10 + i,
                "r_gross": 2.0,
                "r_raw": 1.8,
                "r_net": 1.7,
            }
        )
    return pd.DataFrame(rows, columns=LABEL_COLUMNS)


def _stats_frame() -> pd.DataFrame:
    """One canonical-stats row carrying the full grouped column set."""
    return pd.DataFrame(
        [
            {
                "symbol": SYMBOL,
                "timeframe": TIMEFRAME,
                "trades": 4,
                "wins": 2,
                "losses": 1,
                "timeouts": 1,
                "raw_win_rate": 2 / 3,
                "net_win_rate": 2 / 3,
                "raw_profit_factor": 1.5,
                "net_profit_factor": 1.4,
                "raw_expectancy": 0.1,
                "net_expectancy": 0.05,
                "raw_avg_r": 0.1,
                "net_avg_r": 0.05,
                "raw_max_dd": -0.5,
                "net_max_dd": -0.55,
                "cost_delta_expectancy": -0.05,
            }
        ]
    )


def _meta() -> dict:
    return {
        "run_id": "run-0001",
        "config_hash": "deadbeef",
        "range_start": "2026-06-01T00:00:00",
        "range_end": "2026-08-30T00:00:00",
        "min_history_days": 30,
        "time_barrier_bars": 96,
        "wf_train_days": 180,
        "wf_test_days": 30,
        "created_at": "2026-09-02T00:00:00Z",
    }


# ---------------------------------------------------------------------------
# Atomicity: tmp + os.replace, no residue
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_no_tmp_file_remains_after_successful_write(tmp_path):
    path = write_labels(_labels(3), tmp_path / "labels", SYMBOL, TIMEFRAME)
    assert path.exists()
    assert list(tmp_path.rglob("*.tmp")) == []


@pytest.mark.unit
def test_failed_parquet_write_leaves_no_tmp_residue_and_reraises(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", boom)
    with pytest.raises(RuntimeError, match="disk full"):
        write_labels(_labels(3), tmp_path / "labels", SYMBOL, TIMEFRAME)
    assert list(tmp_path.rglob("*.tmp")) == []


@pytest.mark.unit
def test_failed_json_write_leaves_no_tmp_residue_and_reraises(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(json, "dump", boom)
    with pytest.raises(RuntimeError, match="disk full"):
        write_run_manifest(_meta(), tmp_path / "reports")
    assert list(tmp_path.rglob("*.tmp")) == []


@pytest.mark.unit
def test_writers_create_parent_directories(tmp_path):
    write_labels(_labels(1), tmp_path / "deep" / "labels", SYMBOL, TIMEFRAME)
    write_canonical_stats(_stats_frame(), tmp_path / "deep" / "reports")
    write_run_manifest(_meta(), tmp_path / "deep" / "reports")
    assert (tmp_path / "deep" / "labels" / f"{SYMBOL}_{TIMEFRAME}.parquet").exists()
    assert (tmp_path / "deep" / "reports" / "canonical_stats.json").exists()
    assert (tmp_path / "deep" / "reports" / "run_manifest.json").exists()


# ---------------------------------------------------------------------------
# Determinism: byte-identical re-runs
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_labels_write_is_byte_deterministic(tmp_path):
    labels = _labels(3)
    path_a = write_labels(labels, tmp_path / "a", SYMBOL, TIMEFRAME)
    path_b = write_labels(labels, tmp_path / "b", SYMBOL, TIMEFRAME)
    assert path_a.read_bytes() == path_b.read_bytes()


@pytest.mark.unit
def test_canonical_stats_json_is_deterministic(tmp_path):
    stats = _stats_frame()
    path_a = write_canonical_stats(stats, tmp_path / "a")
    path_b = write_canonical_stats(stats, tmp_path / "b")
    text_a = path_a.read_text(encoding="utf-8")
    assert text_a == path_b.read_text(encoding="utf-8")
    parsed = json.loads(text_a)
    assert SYMBOL in parsed["records"] and TIMEFRAME in parsed["records"][SYMBOL]
    row = parsed["records"][SYMBOL][TIMEFRAME]
    assert row["raw_expectancy"] == 0.1 and row["cost_delta_expectancy"] == -0.05


@pytest.mark.unit
def test_canonical_stats_non_finite_serialize_as_null(tmp_path):
    stats = _stats_frame()
    stats.loc[0, "net_profit_factor"] = float("inf")
    path = write_canonical_stats(stats, tmp_path / "reports")
    text = path.read_text(encoding="utf-8")
    assert "Infinity" not in text and "NaN" not in text  # strict-JSON safe
    assert json.loads(text)["records"][SYMBOL][TIMEFRAME]["net_profit_factor"] is None


# ---------------------------------------------------------------------------
# Idempotent (symbol, entry_time) overwrite
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_writing_same_labels_twice_yields_no_duplicates(tmp_path):
    labels_dir = tmp_path / "labels"
    write_labels(_labels(3), labels_dir, SYMBOL, TIMEFRAME)
    write_labels(_labels(3), labels_dir, SYMBOL, TIMEFRAME)  # re-run
    stored = pd.read_parquet(labels_dir / f"{SYMBOL}_{TIMEFRAME}.parquet")
    assert len(stored) == 3


@pytest.mark.unit
def test_revised_row_same_key_keeps_last(tmp_path):
    labels = _labels(2)
    revised = labels.copy()
    revised.loc[revised.index[-1], "r_net"] = 0.42
    duped = pd.concat([labels, revised], ignore_index=True)

    labels_dir = tmp_path / "labels"
    write_labels(duped, labels_dir, SYMBOL, TIMEFRAME)
    stored = pd.read_parquet(labels_dir / f"{SYMBOL}_{TIMEFRAME}.parquet")

    assert len(stored) == 2  # no duplicates on the shared key
    key_time = revised["entry_time"].iloc[-1]
    row = stored[stored["entry_time"] == key_time]
    assert len(row) == 1
    assert row["r_net"].iloc[0] == 0.42  # keep="last" wins
    assert list(stored["entry_time"]) == list(sorted(stored["entry_time"]))  # sorted


@pytest.mark.unit
def test_empty_labels_roundtrip_preserves_schema(tmp_path):
    empty = _empty_labels_frame()
    path = write_labels(empty, tmp_path / "labels", SYMBOL, TIMEFRAME)
    stored = pd.read_parquet(path)
    assert len(stored) == 0
    assert list(stored.columns) == list(LABEL_COLUMNS)


# ---------------------------------------------------------------------------
# Schema validation + manifest separation
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_write_labels_missing_column_raises(tmp_path):
    bad = _labels(2).drop(columns=["r_net"])
    with pytest.raises(ValueError, match="invariant violated"):
        write_labels(bad, tmp_path / "labels", SYMBOL, TIMEFRAME)


@pytest.mark.unit
def test_manifest_regeneration_does_not_touch_label_bytes(tmp_path):
    labels_dir = tmp_path / "labels"
    reports_dir = tmp_path / "reports"
    path = write_labels(_labels(3), labels_dir, SYMBOL, TIMEFRAME)
    before = path.read_bytes()

    write_run_manifest(_meta(), reports_dir)
    write_run_manifest(_meta(), reports_dir)  # regenerate

    assert path.read_bytes() == before  # label bytes untouched by run metadata
    manifest = json.loads((reports_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["config_hash"] == "deadbeef"
    assert manifest["range_start"] == "2026-06-01T00:00:00"
    assert manifest["range_end"] == "2026-08-30T00:00:00"
    assert manifest["run_id"] == "run-0001"
    assert manifest["created_at"] == "2026-09-02T00:00:00Z"  # timestamps live HERE only


@pytest.mark.unit
def test_run_manifest_key_contract(tmp_path):
    meta = _meta()
    del meta["config_hash"]
    with pytest.raises(ValueError, match="invariant violated"):
        write_run_manifest(meta, tmp_path / "reports")
    meta = _meta()
    meta["sneaky_extra"] = 1
    with pytest.raises(ValueError, match="invariant violated"):
        write_run_manifest(meta, tmp_path / "reports")


# ---------------------------------------------------------------------------
# config_hash stability
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_config_hash_stable_across_equal_configs():
    assert config_hash(bt_cfg()) == config_hash(bt_cfg())


@pytest.mark.unit
def test_config_hash_changes_when_a_knob_changes():
    base = config_hash(bt_cfg())
    assert config_hash(bt_cfg(time_barrier_bars=48)) != base
    assert config_hash(bt_cfg(slippage_pips=1.0)) != base
    assert config_hash(bt_cfg(wf_test_days=14)) != base


@pytest.mark.unit
def test_config_hash_is_hex_digest():
    digest = config_hash(bt_cfg())
    assert len(digest) == 64
    int(digest, 16)  # parses as hex
