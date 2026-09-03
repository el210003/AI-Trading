"""Phase-4 ML test fixtures — local helper built over ``_backtest_fixtures``
(and ``conftest``/``_detector_fixtures``) via direct import, never extended
(Phase 1/2 contract; 04-RESEARCH Wave-0 Gaps).

Helpers:
- ``ml_cfg``: frozen Config carrying the Phase-4 ``ml_*`` defaults so ML tests
  never depend on ``load_config`` or files on disk.
- ``make_labels``: build a label frame with exactly ``replay.LABEL_COLUMNS`` and
  replay's pinned dtypes (string columns as ``pd.StringDtype``,
  ``entry_time``/``exit_time`` as ``datetime64[us]``, ``exit_idx`` int64,
  remaining columns float64) from a list of row dicts.
- ``sculpted_label_world``: a single-symbol synthetic world whose ``run_chain``
  + ``replay_symbol`` pass yields at least one WIN and one LOSS label with
  known ``sl_price``/``tp_price`` (point-in-time audit L1/L3 fixtures).
- ``synthetic_feature_frame``: (added in plan 04-01 Task 2 — it mirrors
  FEATURE_SPEC, which does not exist until then.)

All helpers return new frames / never mutate inputs.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
from _backtest_fixtures import bt_cfg
from _detector_fixtures import flat_bars

from ai_trading.backtest.chain import run_chain
from ai_trading.backtest.replay import LABEL_COLUMNS, replay_symbol

__all__ = [
    "ml_cfg",
    "make_labels",
    "sculpted_label_world",
    "synthetic_feature_frame",
    "LABEL_COLUMNS",
]

SYMBOL = "EURUSD"
_START = datetime(2026, 8, 20, 0, 0)

_STR_COLS = (
    "symbol",
    "timeframe",
    "direction",
    "pool_id",
    "event_id",
    "zone_id",
    "bias_h1",
    "bias_h4",
    "outcome",
)
_TS_COLS = ("entry_time", "exit_time")
_INT_COLS = ("exit_idx",)


def ml_cfg(**overrides) -> Any:
    """Frozen Config carrying the Phase-4 ``ml_*`` defaults (and all Phase-3
    backtest defaults) via ``_backtest_fixtures.bt_cfg``; pass keyword
    overrides per test (never touches ``load_config``)."""
    return bt_cfg(**overrides)


def _default_for(col: str):
    """Type-aware placeholder for an unprovided label column so the final
    dtype casts succeed (pd.NA would break numeric/ts/int casts)."""
    if col in _STR_COLS:
        return pd.NA
    if col in _TS_COLS:
        return pd.NaT
    if col in _INT_COLS:
        return 0
    return float("nan")


def make_labels(rows: list[dict]) -> pd.DataFrame:
    """Build a label frame with exactly ``LABEL_COLUMNS`` and replay's pinned
    dtypes from a list of row dicts. Unprovided columns fall back to a
    dtype-appropriate missing placeholder (pd.NA / NaT / 0 / NaN). Empty
    ``rows`` yields a schema-correct empty frame with pinned dtypes."""
    data = {col: [] for col in LABEL_COLUMNS}
    for row in rows:
        for col in LABEL_COLUMNS:
            value = row.get(col)
            data[col].append(_default_for(col) if value is None or value is pd.NA else value)
    labels = pd.DataFrame(data, columns=LABEL_COLUMNS)
    for col in _STR_COLS:
        labels[col] = labels[col].astype(pd.StringDtype())
    for col in _TS_COLS:
        labels[col] = labels[col].astype("datetime64[us]")
    for col in _INT_COLS:
        labels[col] = labels[col].astype("int64")
    for col in LABEL_COLUMNS:
        if col not in _STR_COLS and col not in _TS_COLS and col not in _INT_COLS:
            labels[col] = labels[col].astype("float64")
    return labels


def _m15_world() -> pd.DataFrame:
    """Sculpted M15 frame (base 1.100/1.105) producing two long taps: a low
    pool at 1.07 (bars 12/16) with zone high 1.16 (bar 20) and sweep at 1.068
    (bar 30), plus a later negative sweep price path so the second tap LOSES."""
    df = flat_bars(SYMBOL, "M15", _START, 220, price=1.10000)
    df["close"] = 1.10500  # flat base close above open (see make_bars align)
    df["high"] = 1.10500
    df["low"] = 1.10000
    # Scene A: equal-low pool at 1.07, zone high 1.16, sweep 1.068 -> long
    for idx in (12, 16):
        df.iloc[idx, df.columns.get_indexer(["low"])] = 1.07000
    df.iloc[30, df.columns.get_indexer(["low"])] = 1.06800
    df.iloc[20, df.columns.get_indexer(["high"])] = 1.16000
    # First trade WINS: price rises to the 1.16 target at bar 36
    df.iloc[35, df.columns.get_indexer(["high"])] = 1.13000
    df.iloc[36, df.columns.get_indexer(["high"])] = 1.16000
    # Second tap same pool structure; price then falls to the 1.068 SL -> LOSS
    df.iloc[50, df.columns.get_indexer(["low"])] = 1.09000
    df.iloc[54, df.columns.get_indexer(["low"])] = 1.09000
    df.iloc[58, df.columns.get_indexer(["high"])] = 1.13000
    df.iloc[62, df.columns.get_indexer(["low"])] = 1.08800
    df.iloc[70, df.columns.get_indexer(["low"])] = 1.06000
    return df


def _h1_world() -> pd.DataFrame:
    """H1 bullish-bias feed (zone 1.09-1.13, eq 1.11) so D-02 bias agreement
    holds for the M15 longs (mirrors test_replay_repaint)."""
    df = flat_bars(SYMBOL, "H1", _START, 40, price=1.10000)
    df.iloc[2, df.columns.get_indexer(["low"])] = 1.09000
    df.iloc[4, df.columns.get_indexer(["high"])] = 1.13000
    return df


def _h4_world() -> pd.DataFrame:
    return flat_bars(SYMBOL, "H4", _START, 40, price=1.10)


def _barrier_stub(position, bars, cfg) -> dict:
    """End-of-data lens resolver (03-02 walk_barriers analogue): walk forward
    from the fill bar; a LONG resolves WIN when the high reaches the TP, LOSS
    when the low reaches the SL, TIMEOUT otherwise (barrier has no fixed
    expiry here — the audit's prefix filter only cares about the outcome)."""
    start = position.entry_idx
    end = len(bars)
    for j in range(start, end):
        bar = bars.iloc[j]
        if position.direction == "long":
            if bar["low"] <= position.sl_price:
                return {
                    "outcome": "LOSS",
                    "exit_time": bars["time_utc"].iloc[j],
                    "exit_price": float(bar["low"]),
                    "exit_idx": j,
                    "r_gross": -1.0,
                    "r_raw": -1.0,
                    "r_net": -1.0,
                }
            if bar["high"] >= position.tp_price:
                return {
                    "outcome": "WIN",
                    "exit_time": bars["time_utc"].iloc[j],
                    "exit_price": float(bar["high"]),
                    "exit_idx": j,
                    "r_gross": 1.0,
                    "r_raw": 1.0,
                    "r_net": 1.0,
                }
    return {
        "outcome": "TIMEOUT",
        "exit_time": bars["time_utc"].iloc[-1],
        "exit_price": float(bars["close"].iloc[-1]),
        "exit_idx": len(bars) - 1,
        "r_gross": 0.0,
        "r_raw": 0.0,
        "r_net": 0.0,
    }


def sculpted_label_world() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return ``(m15_bars, h1_bars, h4_bars, labels)`` for a single-symbol
    synthetic world whose ``run_chain`` + ``replay_symbol`` pass yields at
    least one WIN and one LOSS label with known ``sl_price``/``tp_price``.

    The world is deterministic (flat base + fixed sculpts, no RNG)."""
    m15 = _m15_world()
    h1 = _h1_world()
    h4 = _h4_world()
    labels = replay_symbol(m15, run_chain(m15, h1, h4), ml_cfg(), _barrier_stub)
    return m15, h1, h4, labels


def synthetic_feature_frame(n_rows: int, seed: int = 0) -> pd.DataFrame:
    """Deterministic feature frame whose columns are exactly the FEATURE_SPEC
    names (categorical columns as ``pd.CategoricalDtype``, numeric columns
    float64), seeded via ``numpy.default_rng(seed)`` and scaled to plausible
    ranges. Consumed by the train/scorer tests in plan 04-02. Never mutates
    its inputs (returns a new frame)."""
    from ai_trading.ml.features import FEATURE_SPEC

    rng = np.random.default_rng(seed)
    categorical = [e["name"] for e in FEATURE_SPEC if e["dtype"] == "categorical"]
    numeric = [e["name"] for e in FEATURE_SPEC if e["dtype"] == "float64"]

    data: dict[str, Any] = {}
    cat_values = {
        "symbol": ["EURUSD", "GBPUSD", "USDJPY", "EURUSD.a"],
        "timeframe": ["M15", "H1"],
        "direction": ["long", "short"],
        "bias_h1": [pd.NA, "bullish", "bearish", "neutral"],
        "bias_h4": [pd.NA, "bullish", "bearish", "neutral"],
    }
    for name in categorical:
        choices = cat_values.get(name, [pd.NA, "a", "b"])
        data[name] = pd.Series(rng.choice(choices, size=n_rows)).astype("category")
    # Plausible numeric ranges.
    for name in numeric:
        if name in ("rr_at_decision",):
            data[name] = rng.uniform(0.5, 4.0, size=n_rows)
        elif name in ("sl_dist_atr", "tp_dist_atr", "atr14"):
            data[name] = rng.uniform(0.2, 3.0, size=n_rows)
        elif name in ("zone_position",):
            data[name] = rng.uniform(0.0, 1.0, size=n_rows)
        elif name in ("bars_since_sweep", "bars_since_zone_created"):
            data[name] = rng.integers(0, 30, size=n_rows).astype("float64")
        elif name in ("htf_bias_agreement",):
            data[name] = rng.integers(0, 3, size=n_rows).astype("float64")
        elif name in ("htf_dist_to_eq_atr_h1", "htf_dist_to_eq_atr_h4"):
            data[name] = rng.uniform(-3.0, 3.0, size=n_rows)
        elif name in ("spread_points",):
            data[name] = rng.integers(0, 60, size=n_rows).astype("float64")
        elif name in ("utc_hour_sin", "utc_hour_cos"):
            data[name] = rng.uniform(-1.0, 1.0, size=n_rows)
        else:
            data[name] = rng.uniform(0.0, 1.0, size=n_rows)
        data[name] = data[name].astype("float64")
    return pd.DataFrame(data, columns=[e["name"] for e in FEATURE_SPEC])
