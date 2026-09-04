"""Unit tests for the setup engine scheduler (SETUP-01..04 / D-05) — assembly +
persistence over a fixture bar store, D-05 one-setup-per-symbol suppression,
terminal setups not re-resolved, and the MT5-free invariant.

Runs offline against a temp Parquet bar store (no MT5, no live model/LLM).
"""

from __future__ import annotations

import inspect

import pandas as pd
import pytest
from _backtest_fixtures import write_bars_parquet
from _llm_fixtures import FakeLLMProvider
from _ml_fixtures import _h1_world, _h4_world, _m15_world
from _setup_fixtures import make_setup_frame, setup_cfg

from ai_trading.setup.scheduler import run_engine_once
from ai_trading.setup.store import read_setups, upsert_setups

#: M15 slice ending at decision bar 61 (a known candidate bar in the world).
_DECISION_K = 62


class FakeScorer:
    """Deterministic scorer double (no model artifact needed)."""

    def __init__(self, p_win=0.62, artifact_version=1):
        self.p_win = p_win
        self.artifact_version = artifact_version

    def score(self, features: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "p_win": [self.p_win],
                "score_source": ["ml"],
                "artifact_version": [self.artifact_version],
            }
        )

    def contributors(self, features: pd.DataFrame) -> pd.DataFrame:
        row = {col: 0.05 for col in features.columns}
        row["bias"] = 0.0
        return pd.DataFrame([row])


def _write_world(tmp_path, k=_DECISION_K):
    """Write the m15/h1/h4 world into ``tmp_path/data/bars`` (M15 sliced to the
    first ``k`` bars so the last bar is a candidate decision bar)."""
    m15 = _m15_world()
    h1 = _h1_world()
    h4 = _h4_world()
    bars_dir = tmp_path / "data" / "bars"
    bars_dir.mkdir(parents=True, exist_ok=True)
    write_bars_parquet(m15.iloc[:k].reset_index(drop=True), bars_dir / "EURUSD_M15.parquet")
    write_bars_parquet(h1, bars_dir / "EURUSD_H1.parquet")
    write_bars_parquet(h4, bars_dir / "EURUSD_H4.parquet")
    return bars_dir


@pytest.mark.unit
def test_run_engine_once_assembles_and_persists(tmp_path):
    cfg = setup_cfg(bars_dir=_write_world(tmp_path))
    summary = run_engine_once(cfg, scorer=FakeScorer(), llm_provider=FakeLLMProvider())
    assert summary["assembled"] == 1
    setups = read_setups(cfg)
    assert len(setups) == 1
    row = setups.iloc[0]
    assert row["status"] == "pending"
    assert row["symbol"] == "EURUSD"
    assert not pd.isna(row["entry"])
    # No .tmp left behind after the atomic write.
    store = tmp_path / "data" / "setups" / "setups.parquet"
    assert store.exists()
    assert not store.with_name("setups.parquet.tmp").exists()


@pytest.mark.unit
def test_run_engine_once_suppresses_second_setup_d05(tmp_path):
    cfg = setup_cfg(bars_dir=_write_world(tmp_path))
    run_engine_once(cfg, scorer=FakeScorer(), llm_provider=FakeLLMProvider())
    # Second pass: EURUSD already has a pending setup -> suppressed (D-05).
    summary = run_engine_once(cfg, scorer=FakeScorer(), llm_provider=FakeLLMProvider())
    assert summary["assembled"] == 0
    assert len(read_setups(cfg)) == 1


@pytest.mark.unit
def test_run_engine_once_keeps_terminal_setup(tmp_path):
    cfg = setup_cfg(bars_dir=_write_world(tmp_path))
    # Inject a resolved terminal setup for EURUSD.
    upsert_setups(
        cfg,
        make_setup_frame(
            [{
                "status": "tp_hit",
                "outcome": "WIN",
                "trigger_bar_idx": 3,
                "trigger_time": pd.Timestamp("2026-08-20T12:45:00"),
                "exit_price": 1.15,
                "r_gross": 5.0,
            }]
        ),
    )
    run_engine_once(cfg, scorer=FakeScorer(), llm_provider=FakeLLMProvider())
    setups = read_setups(cfg)
    # The resolved setup is never re-resolved (terminal status is stable).
    resolved = setups[setups["status"] == "tp_hit"]
    assert len(resolved) == 1
    assert float(resolved.iloc[0]["r_gross"]) == pytest.approx(5.0)
    assert float(resolved.iloc[0]["exit_price"]) == pytest.approx(1.15)


@pytest.mark.unit
def test_setup_package_is_mt5_free():
    """No MetaTrader5 / mt5_client import reaches the setup surface."""
    import ai_trading.setup
    import ai_trading.setup.assembly
    import ai_trading.setup.lifecycle  # noqa: F401
    import ai_trading.setup.scheduler
    import ai_trading.setup.store  # noqa: F401

    for module in (
        ai_trading.setup,
        ai_trading.setup.assembly,
        ai_trading.setup.lifecycle,
        ai_trading.setup.scheduler,
        ai_trading.setup.store,
    ):
        source = inspect.getsource(module)
        for needle in (
            "import metatrader5",
            "from metatrader5",
            "mt5_client",
        ):
            assert needle not in source
