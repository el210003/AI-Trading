"""Unit tests (DATA-03 foundation): config loader/validation + pure UTC
normalization. No MT5 import anywhere."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ai_trading.config import load_config
from ai_trading.normalize import COLUMNS, rates_to_dataframe

# MT5 copy_rates* structured-array dtype (time = epoch seconds of server wall time).
RATES_DTYPE = [
    ("time", "int64"),
    ("open", "float64"),
    ("high", "float64"),
    ("low", "float64"),
    ("close", "float64"),
    ("tick_volume", "int64"),
    ("spread", "int64"),
    ("real_volume", "float64"),
]

VALID_SYMBOLS = ["EURUSD", "EURUSD.a", "EURUSD.abc123"]
INVALID_SYMBOLS = ["eurusd", "EURUS", "EURUSDQ", "EURUSD.", "EURUSD.a.x"]


def _server_epoch_seconds(naive_server_wall: datetime) -> int:
    """Encode a naive server-wall datetime as epoch seconds so that
    pd.to_datetime(unit='s') decodes it back to the exact same wall clock."""
    return int(naive_server_wall.replace(tzinfo=UTC).timestamp())


def _rates(times: list[datetime]) -> np.ndarray:
    rows = [
        (_server_epoch_seconds(t), 1.10000, 1.20000, 1.00000, 1.15000, 10, 2, 0)
        for t in times
    ]
    return np.array(rows, dtype=RATES_DTYPE)


def _write_config(tmp: Path, values: dict, name: str = "config.toml") -> Path:
    def toml_value(val: object) -> str:
        # dict -> TOML inline table ("{ K = V }"); json.dumps alone emits JSON
        # object syntax ("K": V) which tomllib rejects (plan 03-01 fix).
        if isinstance(val, dict):
            return "{ " + ", ".join(f"{k} = {json.dumps(v)}" for k, v in val.items()) + " }"
        return json.dumps(val)

    lines = [f"{key} = {toml_value(val)}" for key, val in values.items()]
    path = tmp / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _base_values(tmp: Path, **overrides: object) -> dict:
    dummy_terminal = tmp / "terminal64.exe"
    if not dummy_terminal.exists():
        dummy_terminal.write_text("stub terminal for path validation", encoding="utf-8")
    values: dict = {
        "symbols": ["EURUSD"],
        "timeframes": ["M15", "H1", "H4"],
        "terminal_path": str(dummy_terminal),
        "expected_server": "",
        "broker_offset_hours": 3,
        "validated_at": "2026-08-30T00:00:00Z",
        "bars_dir": "data/bars",
        "meta_db": "data/meta/meta.sqlite",
        "init_timeout_ms": 30000,
        "poll_delay_seconds": 3,
        "lookback_bars": 500,
        "min_maxbars": 100000,
        "backfill_max_rounds": 12,
        "backfill_pause_seconds": 0.7,
        "initial_backfill_days": 90,
        # Phase-3 backtest knobs (same values as config.toml) — required since
        # plan 03-01 extended _REQUIRED_KEYS.
        "slippage_pips": 0.5,
        "slippage_pips_by_symbol": {},
        "default_spread_points": 20,
        "default_spread_points_by_symbol": {},
        "pip_size": {"EURUSD": 0.0001, "GBPUSD": 0.0001, "USDJPY": 0.01},
        "min_rr": 1.0,
        "time_barrier_bars": 96,
        "wf_train_days": 180,
        "wf_test_days": 30,
        "min_history_days": 30,
        "warmup_bars": 0,
        "htf_warmup_days": 30,
        # Phase-4 ML scoring knobs (same values as config.toml) — required since
        # plan 04-01 extended _REQUIRED_KEYS.
        "ml_feature_list_version": 1,
        "ml_calibration_method": "sigmoid",
        "ml_embargo_bars": 0,
        "ml_min_train_labels": 30,
        "ml_cal_train_days": 2,
        "ml_cal_test_days": 1,
        "ml_random_state": 42,
        "ml_n_estimators": 200,
        "ml_num_leaves": 7,
        "ml_min_data_in_leaf": 5,
        "ml_learning_rate": 0.1,
        "ml_retrain_enabled": False,
        "ml_retrain_interval_hours": 24,
    }
    values.update(overrides)
    return values


# ---------------------------------------------------------------------------
# UTC normalization math (DATA-03)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_offset_three_maps_server_wall_to_true_utc():
    """Plan success criterion: server 2026-08-29 00:00 -> time_utc 2026-08-28 21:00."""
    server = datetime(2026, 8, 29, 0, 0)
    df = rates_to_dataframe(_rates([server]), "EURUSD", 3)
    assert df.loc[0, "time"] == pd.Timestamp("2026-08-29 00:00:00")
    assert df.loc[0, "time_utc"] == pd.Timestamp("2026-08-28 21:00:00")


@pytest.mark.unit
def test_negative_offset_five_adds_hours():
    server = datetime(2026, 8, 28, 21, 0)
    df = rates_to_dataframe(_rates([server]), "EURUSD", -5)
    assert df.loc[0, "time_utc"] == pd.Timestamp("2026-08-29 02:00:00")


@pytest.mark.unit
def test_zero_offset_identity_and_raw_time_preserved():
    server = datetime(2026, 8, 29, 0, 0)
    zero = rates_to_dataframe(_rates([server]), "EURUSD", 0)
    assert zero.loc[0, "time"] == zero.loc[0, "time_utc"] == pd.Timestamp("2026-08-29 00:00:00")
    # raw server column must be untouched regardless of the offset applied
    shifted = rates_to_dataframe(_rates([server]), "EURUSD", 3)
    assert shifted.loc[0, "time"] == pd.Timestamp("2026-08-29 00:00:00")


@pytest.mark.unit
def test_output_columns_are_exactly_c_columns_and_naive():
    server = datetime(2026, 8, 29, 0, 0)
    df = rates_to_dataframe(_rates([server]), "EURUSD.a", 3)
    assert list(df.columns) == COLUMNS
    assert df["time"].dt.tz is None
    assert df["time_utc"].dt.tz is None
    assert (df["symbol"] == "EURUSD.a").all()


# ---------------------------------------------------------------------------
# Config loader happy path
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_load_config_happy_path(tmp_path):
    path = _write_config(tmp_path, _base_values(tmp_path))
    cfg = load_config(path)
    assert cfg.symbols == ("EURUSD",)
    assert cfg.timeframes == ("M15", "H1", "H4")
    assert cfg.broker_offset_hours == 3
    assert cfg.bars_dir == Path("data/bars")
    assert cfg.meta_db == Path("data/meta/meta.sqlite")


@pytest.mark.unit
def test_local_override_shallow_merge_wins(tmp_path):
    base = _write_config(tmp_path, _base_values(tmp_path, terminal_path="", symbols=["EURUSD"]))
    _write_config(
        tmp_path,
        {"terminal_path": str(tmp_path / "terminal64.exe"), "symbols": ["GBPUSD"]},
        name="config.local.toml",
    )
    cfg = load_config(base)
    assert cfg.symbols == ("GBPUSD",)  # local value wins
    assert cfg.terminal_path == str(tmp_path / "terminal64.exe")  # local fills invalid base value


# ---------------------------------------------------------------------------
# Offset bounds (±14 h per RESEARCH test map)
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize("offset", [-14, 14])
def test_offset_bounds_accepted(tmp_path, offset):
    path = _write_config(tmp_path, _base_values(tmp_path, broker_offset_hours=offset))
    assert load_config(path).broker_offset_hours == offset


@pytest.mark.unit
@pytest.mark.parametrize("offset", [-15, 15])
def test_offset_bounds_rejected(tmp_path, offset):
    path = _write_config(tmp_path, _base_values(tmp_path, broker_offset_hours=offset))
    with pytest.raises(ValueError, match="broker_offset_hours"):
        load_config(path)


# ---------------------------------------------------------------------------
# Symbol validation matrix
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize("sym", VALID_SYMBOLS)
def test_symbol_names_accepted(tmp_path, sym):
    path = _write_config(tmp_path, _base_values(tmp_path, symbols=[sym]))
    assert load_config(path).symbols == (sym,)


@pytest.mark.unit
@pytest.mark.parametrize("sym", INVALID_SYMBOLS)
def test_symbol_names_rejected(tmp_path, sym):
    path = _write_config(tmp_path, _base_values(tmp_path, symbols=[sym]))
    with pytest.raises(ValueError, match="symbols"):
        load_config(path)


# ---------------------------------------------------------------------------
# Other validation failures + startup warning
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_missing_required_key_raises_value_error(tmp_path):
    values = _base_values(tmp_path)
    del values["min_maxbars"]
    path = _write_config(tmp_path, values)
    with pytest.raises(ValueError, match="min_maxbars"):
        load_config(path)


@pytest.mark.unit
def test_nonexistent_terminal_path_rejected(tmp_path):
    path = _write_config(
        tmp_path,
        _base_values(tmp_path, terminal_path=str(tmp_path / "no-such-terminal.exe")),
    )
    with pytest.raises(ValueError, match="terminal_path"):
        load_config(path)


@pytest.mark.unit
def test_empty_terminal_path_rejected(tmp_path):
    path = _write_config(tmp_path, _base_values(tmp_path, terminal_path=""))
    with pytest.raises(ValueError, match="terminal_path"):
        load_config(path)


@pytest.mark.unit
def test_empty_validated_at_warns_but_loads(tmp_path, caplog):
    path = _write_config(tmp_path, _base_values(tmp_path, validated_at=""))
    with caplog.at_level(logging.WARNING, logger="ai_trading.config"):
        cfg = load_config(path)
    assert cfg.validated_at == ""
    assert "broker offset not yet validated" in caplog.text
