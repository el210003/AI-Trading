"""Unit tests for the Phase-3 backtest config knobs: frozen-Config extension,
_REQUIRED_KEYS fail-fast loading, and the validation rejection matrix.

Mirrors test_normalize_and_config.py structure (_write_config + _base_values +
parametrized rejections). No MT5 import anywhere.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_trading.config import Config, load_config


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
        # Phase-3 backtest knobs (same values as config.toml)
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
    }
    values.update(overrides)
    return values


# ---------------------------------------------------------------------------
# Happy path: every new key loads onto the frozen Config
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_load_config_carries_backtest_knobs(tmp_path):
    path = _write_config(
        tmp_path,
        _base_values(
            tmp_path,
            slippage_pips_by_symbol={"EURUSD": 0.7},
            default_spread_points_by_symbol={"EURUSD": 30},
        ),
    )
    cfg = load_config(path)
    assert cfg.slippage_pips == 0.5
    assert cfg.slippage_pips_by_symbol == {"EURUSD": 0.7}
    assert cfg.default_spread_points == 20
    assert cfg.default_spread_points_by_symbol == {"EURUSD": 30}
    assert cfg.pip_size == {"EURUSD": 0.0001, "GBPUSD": 0.0001, "USDJPY": 0.01}
    assert cfg.min_rr == 1.0
    assert cfg.time_barrier_bars == 96
    assert cfg.wf_train_days == 180
    assert cfg.wf_test_days == 30
    assert cfg.min_history_days == 30
    assert cfg.warmup_bars == 0
    assert cfg.htf_warmup_days == 30


@pytest.mark.unit
def test_scalar_defaults_used_when_override_maps_empty(tmp_path):
    cfg = load_config(_write_config(tmp_path, _base_values(tmp_path)))
    assert cfg.slippage_pips_by_symbol == {}
    assert cfg.default_spread_points_by_symbol == {}


# ---------------------------------------------------------------------------
# Rejection matrix: every invalid knob raises ValueError naming the key
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize(
    ("overrides", "key"),
    [
        ({"slippage_pips": -0.1}, "slippage_pips"),
        ({"min_rr": 0}, "min_rr"),
        ({"default_spread_points": -1}, "default_spread_points"),
        ({"pip_size": {"GBPUSD": 0.0001, "USDJPY": 0.01}}, "pip_size"),
        ({"pip_size": {"EURUSD": 0, "GBPUSD": 0.0001, "USDJPY": 0.01}}, "pip_size"),
        ({"slippage_pips_by_symbol": {"AUDUSD": 0.7}}, "slippage_pips_by_symbol"),
        ({"default_spread_points_by_symbol": {"EURUSD": -5}}, "default_spread_points_by_symbol"),
        ({"time_barrier_bars": 0}, "time_barrier_bars"),
        ({"wf_train_days": 0}, "wf_train_days"),
        ({"wf_test_days": -5}, "wf_test_days"),
        ({"min_history_days": 0}, "min_history_days"),
        ({"warmup_bars": -1}, "warmup_bars"),
        ({"htf_warmup_days": 0}, "htf_warmup_days"),
    ],
)
def test_backtest_knob_rejections(tmp_path, overrides, key):
    path = _write_config(tmp_path, _base_values(tmp_path, **overrides))
    with pytest.raises(ValueError, match=key):
        load_config(path)


@pytest.mark.unit
def test_missing_new_required_key_raises(tmp_path):
    values = _base_values(tmp_path)
    del values["default_spread_points"]
    path = _write_config(tmp_path, values)
    with pytest.raises(ValueError, match="default_spread_points"):
        load_config(path)


# ---------------------------------------------------------------------------
# Direct construction: dataclass defaults keep conftest._make_cfg valid
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_direct_construction_uses_dataclass_defaults(tmp_path):
    """Config(**{fifteen old keys only}) must construct cleanly with the 12
    Phase-3 fields falling back to their dataclass defaults — proves
    tests/conftest.py _make_cfg remains valid WITHOUT modifying conftest."""
    dummy_terminal = tmp_path / "terminal64.exe"
    dummy_terminal.write_text("stub", encoding="utf-8")
    cfg = Config(
        symbols=("EURUSD",),
        timeframes=("M15", "H1", "H4"),
        terminal_path=str(dummy_terminal),
        expected_server="ICMarketsSC-Demo",
        broker_offset_hours=3,
        validated_at="2026-08-30T00:00:00Z",
        bars_dir=Path("data/bars"),
        meta_db=Path("data/meta/meta.sqlite"),
        init_timeout_ms=30000,
        poll_delay_seconds=3,
        lookback_bars=500,
        min_maxbars=100000,
        backfill_max_rounds=12,
        backfill_pause_seconds=0.7,
        initial_backfill_days=90,
    )
    assert cfg.slippage_pips == 0.5
    assert cfg.slippage_pips_by_symbol == {}
    assert cfg.default_spread_points == 20
    assert cfg.default_spread_points_by_symbol == {}
    assert cfg.pip_size == {"EURUSD": 0.0001, "GBPUSD": 0.0001, "USDJPY": 0.01}
    assert cfg.min_rr == 1.0
    assert cfg.time_barrier_bars == 96
    assert cfg.wf_train_days == 180
    assert cfg.wf_test_days == 30
    assert cfg.min_history_days == 30
    assert cfg.warmup_bars == 0
    assert cfg.htf_warmup_days == 30
