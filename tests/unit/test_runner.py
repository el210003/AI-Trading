"""Unit tests for the backtest runner CLI (plan 03-03): exit-code contract
(2 config / 1 runtime refusal / 0 success incl. zero-candidate runs), the
D-21 history gate with actionable message + --min-history-days override
(frozen-Config replace), offset-uniformity refusal, range resolution, full
pipeline wiring (chain -> replay -> walk_barriers -> stats -> walk-forward),
and the artifact layout (label-derived under data/labels/, window artifacts
under data/reports/). main(argv) is called directly — no subprocess, no MT5.

The happy path reuses THE sculpted world from test_replay_repaint (proven to
yield exactly one label through the real chain) with the REAL walk_barriers
resolver — the resolver seam from plan 03-01 closes here.
"""

from __future__ import annotations

import json
import logging

import pandas as pd
import pytest
from _backtest_fixtures import bt_cfg, flat_bars, make_bars, write_bars_parquet
from test_backtest_config import _base_values
from test_backtest_config import _write_config as _write_toml
from test_replay_repaint import START, SYMBOL, _h1_world, _m15_world

from ai_trading.backtest.replay import LABEL_COLUMNS
from ai_trading.backtest.runner import main as runner_main
from ai_trading.backtest.runner import resolve_range, run_backtest


def _write_config(tmp_path, bars_dir, **overrides):
    return _write_toml(tmp_path, _base_values(tmp_path, bars_dir=str(bars_dir), **overrides))


def _write_store(bars_dir, m15, h1=None, h4=None) -> None:
    """Persist synthetic bars through the single project write path."""
    bars_dir.mkdir(parents=True, exist_ok=True)
    write_bars_parquet(m15, bars_dir / f"{SYMBOL}_M15.parquet")
    if h1 is not None:
        write_bars_parquet(h1, bars_dir / f"{SYMBOL}_H1.parquet")
    if h4 is not None:
        write_bars_parquet(h4, bars_dir / f"{SYMBOL}_H4.parquet")


def _five_day_m15():
    """480 rising M15 bars (~5 days stored, .days == 4) — no candidates."""
    return make_bars(SYMBOL, "M15", START, 480)


# ---------------------------------------------------------------------------
# Exit code 2: config errors
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_missing_config_returns_2(tmp_path, caplog):
    with caplog.at_level(logging.ERROR):
        rc = runner_main(["--config", str(tmp_path / "nope.toml")])
    assert rc == 2
    assert "invalid configuration" in caplog.text


@pytest.mark.unit
def test_invalid_config_returns_2(tmp_path, caplog):
    bad = tmp_path / "bad.toml"
    bad.write_text('symbols = ["EURUSD"]\n', encoding="utf-8")  # missing required keys
    with caplog.at_level(logging.ERROR):
        rc = runner_main(["--config", str(bad)])
    assert rc == 2
    assert "invalid configuration" in caplog.text
    assert "missing required config key" in caplog.text


@pytest.mark.unit
def test_symbols_outside_config_returns_2(tmp_path):
    bars_dir = tmp_path / "bars"
    _write_store(bars_dir, m15=_five_day_m15())
    cfg_path = _write_config(tmp_path, bars_dir, min_history_days=30)
    assert runner_main(["--config", str(cfg_path), "--symbols", "GBPUSD"]) == 2


@pytest.mark.unit
def test_symbols_outside_engine_universe_returns_2(tmp_path):
    """BTCUSD collected but collect-only (setup_symbols split): explicitly
    backtesting it is a config error (exit 2), not a silent cost-model run."""
    bars_dir = tmp_path / "bars"
    _write_store(bars_dir, m15=_five_day_m15())
    cfg_path = _write_config(
        tmp_path,
        bars_dir,
        min_history_days=30,
        symbols=["EURUSD", "BTCUSD"],
        setup_symbols=["EURUSD"],
    )
    assert runner_main(["--config", str(cfg_path), "--symbols", "BTCUSD"]) == 2


@pytest.mark.unit
def test_min_history_days_must_be_positive(tmp_path, caplog):
    bars_dir = tmp_path / "bars"
    _write_store(bars_dir, m15=_five_day_m15())
    cfg_path = _write_config(tmp_path, bars_dir, min_history_days=30)
    with caplog.at_level(logging.ERROR):
        assert runner_main(["--config", str(cfg_path), "--min-history-days", "0"]) == 2
        assert runner_main(["--config", str(cfg_path), "--min-history-days", "-5"]) == 2
    assert "--min-history-days must be a positive integer" in caplog.text


# ---------------------------------------------------------------------------
# Exit code 1: runtime refusals (D-21 gate, offsets, range)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_gate_refusal_exit_1_with_actionable_message(tmp_path, caplog):
    bars_dir = tmp_path / "bars"
    _write_store(bars_dir, m15=_five_day_m15())  # 4 days stored
    cfg_path = _write_config(tmp_path, bars_dir, min_history_days=30)
    with caplog.at_level(logging.ERROR):
        rc = runner_main(["--config", str(cfg_path), "--write"])
    assert rc == 1
    message = caplog.text
    assert SYMBOL in message and "M15" in message  # symbol + timeframe
    assert "4 days stored < 30 required" in message  # both day counts
    assert "extend collection" in message and "--min-history-days" in message  # remedy
    assert not (tmp_path / "labels" / f"{SYMBOL}_M15.parquet").exists()
    assert not (tmp_path / "reports").exists()  # nothing written on refusal


@pytest.mark.unit
def test_gate_override_allows_short_store(tmp_path):
    bars_dir = tmp_path / "bars"
    _write_store(bars_dir, m15=_five_day_m15())
    cfg_path = _write_config(tmp_path, bars_dir, min_history_days=30)
    rc = runner_main(["--config", str(cfg_path), "--write", "--min-history-days", "3"])
    assert rc == 0
    # schema-correct (zero-candidate) artifacts all exist
    assert (tmp_path / "labels" / f"{SYMBOL}_M15.parquet").exists()
    assert (tmp_path / "labels" / "canonical_stats.json").exists()
    assert (tmp_path / "labels" / "run_manifest.json").exists()
    assert (tmp_path / "reports" / "walkforward.parquet").exists()
    assert (tmp_path / "reports" / "walkforward_manifest.json").exists()


@pytest.mark.unit
def test_mixed_offset_bars_refused(tmp_path, caplog):
    bars_dir = tmp_path / "bars"
    bars = _five_day_m15()
    # Faithful DST-flip simulation: same raw server-wall `time`, a few rows
    # re-derived under a different broker offset -> mixed time/time_utc deltas
    # (shifting `time` instead would collide with neighbouring bar-open times
    # and be silently deduped by merge_and_write's (time, keep=last) contract).
    mixed = bars.index[100:105]
    bars.loc[mixed, "time_utc"] = bars.loc[mixed, "time_utc"] - pd.Timedelta(hours=2)
    _write_store(bars_dir, m15=bars)
    cfg_path = _write_config(tmp_path, bars_dir, min_history_days=30)
    with caplog.at_level(logging.ERROR):
        rc = runner_main(["--config", str(cfg_path), "--write", "--min-history-days", "3"])
    assert rc == 1  # Pitfall 10: offset mixing must not silently reach labels
    assert SYMBOL in caplog.text and "offset" in caplog.text
    assert not (tmp_path / "labels" / f"{SYMBOL}_M15.parquet").exists()


@pytest.mark.unit
def test_invalid_range_returns_1_with_accepted_formats(tmp_path, caplog):
    bars_dir = tmp_path / "bars"
    _write_store(bars_dir, m15=_five_day_m15())
    cfg_path = _write_config(tmp_path, bars_dir, min_history_days=30)
    with caplog.at_level(logging.ERROR):
        rc = runner_main(
            ["--config", str(cfg_path), "--range", "nonsense", "--min-history-days", "3"]
        )
    assert rc == 1
    assert "YYYY-MM-DD:YYYY-MM-DD" in caplog.text and "last-ND" in caplog.text


@pytest.mark.unit
def test_range_outside_stored_bars_returns_1(tmp_path, caplog):
    bars_dir = tmp_path / "bars"
    _write_store(bars_dir, m15=_five_day_m15())
    cfg_path = _write_config(tmp_path, bars_dir, min_history_days=30)
    with caplog.at_level(logging.ERROR):
        rc = runner_main(
            [
                "--config", str(cfg_path),
                "--range", "2020-01-01:2020-01-31",
                "--min-history-days", "3",
            ]
        )
    assert rc == 1
    assert "does not intersect" in caplog.text


@pytest.mark.unit
def test_resolve_range_formats_and_clamping():
    bars = make_bars(SYMBOL, "M15", START, 96 * 3)  # 3 days from 2026-08-19 21:00 UTC
    assert resolve_range(None, bars) == (bars["time_utc"].min(), bars["time_utc"].max())
    start, end = resolve_range("2026-08-21:2026-08-22", bars)
    assert start == pd.Timestamp("2026-08-21 00:00")  # inclusive start day
    assert end == bars["time_utc"].max()  # clamped to stored bounds
    start, end = resolve_range("last-2", bars)
    assert start == pd.Timestamp("2026-08-20 20:45")
    assert end == bars["time_utc"].max()
    start, end = resolve_range("2026-08-01:2026-08-31", bars)  # superset clamps to store
    assert (start, end) == (bars["time_utc"].min(), bars["time_utc"].max())
    with pytest.raises(ValueError, match="last-ND"):
        resolve_range("bogus", bars)
    with pytest.raises(ValueError, match="after end day"):
        resolve_range("2026-08-22:2026-08-21", bars)


# ---------------------------------------------------------------------------
# Full pipeline + zero-candidate contract (exit 0)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_full_happy_path_end_to_end(tmp_path):
    bars_dir = tmp_path / "bars"
    _write_store(
        bars_dir,
        m15=_m15_world(),  # sculpted sweep+mitigation world (exactly one label)
        h1=_h1_world(),
        h4=flat_bars(SYMBOL, "H4", START, 20),
    )
    cfg_path = _write_config(tmp_path, bars_dir, min_history_days=30)
    rc = runner_main(["--config", str(cfg_path), "--write", "--min-history-days", "1"])
    assert rc == 0

    labels_path = tmp_path / "labels" / f"{SYMBOL}_M15.parquet"
    stored = pd.read_parquet(labels_path)
    assert list(stored.columns) == list(LABEL_COLUMNS)
    assert len(stored) == 1
    assert stored["outcome"].iloc[0] in {"WIN", "LOSS", "TIMEOUT"}

    assert (tmp_path / "labels" / "canonical_stats.json").exists()
    assert (tmp_path / "labels" / "run_manifest.json").exists()

    wf = pd.read_parquet(tmp_path / "reports" / "walkforward.parquet")
    assert len(wf) == 1
    assert wf["window_id"].iloc[0] == 0
    assert wf["symbol"].iloc[0] == SYMBOL

    manifest = json.loads(
        (tmp_path / "reports" / "walkforward_manifest.json").read_text("utf-8")
    )
    run_manifest = json.loads((tmp_path / "labels" / "run_manifest.json").read_text("utf-8"))
    assert manifest["config_hash"] == run_manifest["config_hash"]
    assert len(manifest["windows"]) == 1
    assert manifest["windows"][0]["test_days"] == 30  # cfg default

    # INFO-side layout: label-derived artifacts never under data/reports/
    assert not (tmp_path / "reports" / "canonical_stats.json").exists()
    assert not (tmp_path / "reports" / "run_manifest.json").exists()


@pytest.mark.unit
def test_run_backtest_produces_labels_via_walk_barriers(tmp_path):
    """Resolver wiring: run_backtest labels come from the REAL walk_barriers
    (outcomes restricted to the D-18 classes)."""
    bars_dir = tmp_path / "bars"
    _write_store(
        bars_dir,
        m15=_m15_world(),
        h1=_h1_world(),
        h4=flat_bars(SYMBOL, "H4", START, 20),
    )
    cfg = bt_cfg(bars_dir=bars_dir, min_history_days=1)
    result = run_backtest(cfg, (SYMBOL,), None, write=False)
    labels = result["labels"][SYMBOL]
    assert len(labels) == 1
    assert set(labels["outcome"].unique()).issubset({"WIN", "LOSS", "TIMEOUT"})
    assert result["canonical"].iloc[0]["trades"] == 1
    assert len(result["windows"]) == 1
    assert len(result["window_stats"]) == 1
    assert len(result["window_aggregate"]) == 1
    assert result["window_stats"].iloc[0]["timeouts"] == 1  # TP/SL never touched


@pytest.mark.unit
def test_zero_candidate_run_exits_0_with_empty_artifacts(tmp_path, caplog):
    """A gate-passing run with no signals is a valid outcome: exit 0 (never
    1/2/exception) with schema-correct empty artifacts everywhere."""
    bars_dir = tmp_path / "bars"
    _write_store(
        bars_dir,
        m15=flat_bars(SYMBOL, "M15", START, 480),  # flat: no sweep+mitigation
        h1=flat_bars(SYMBOL, "H1", START, 120),
        h4=flat_bars(SYMBOL, "H4", START, 30),
    )
    cfg_path = _write_config(tmp_path, bars_dir, min_history_days=30)
    with caplog.at_level(logging.INFO):
        rc = runner_main(
            ["--config", str(cfg_path), "--write", "--min-history-days", "3"]
        )
    assert rc == 0
    assert f"0 candidates for {SYMBOL}" in caplog.text

    stored = pd.read_parquet(tmp_path / "labels" / f"{SYMBOL}_M15.parquet")
    assert len(stored) == 0
    assert list(stored.columns) == list(LABEL_COLUMNS)
    assert stored["entry_time"].dtype == "datetime64[us]"  # pinned empty dtypes
    assert str(stored["symbol"].dtype) == "string"

    canonical = json.loads(
        (tmp_path / "labels" / "canonical_stats.json").read_text("utf-8")
    )
    assert canonical == {"records": {}}
    assert (tmp_path / "labels" / "run_manifest.json").exists()

    wf = pd.read_parquet(tmp_path / "reports" / "walkforward.parquet")
    assert len(wf) == 0
    manifest = json.loads(
        (tmp_path / "reports" / "walkforward_manifest.json").read_text("utf-8")
    )
    assert manifest["windows"] == []
    assert manifest["config_hash"]
