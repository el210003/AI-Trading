"""Phase-3 backtest test fixtures — local helper built over ``conftest`` and
``_detector_fixtures`` (both consumed via direct import, never extended —
Phase 1/2 contract; RESEARCH Wave-0 Gaps).

Helpers:
- ``set_spreads``: sculpt the recorded spread column deterministically so
  "recorded spread > 0" and "recorded spread == 0" scenarios (D-15 fallback
  tests) are exact, not incidental.
- ``bt_cfg``: frozen Config with the Phase-3 backtest defaults so label tests
  never depend on load_config or files on disk.
- ``write_bars_parquet``: persist synthetic bars through the single project
  write path (``bar_store.merge_and_write`` — atomic tmp + os.replace) so
  runner tests reuse it instead of inventing a second Parquet writer.

All helpers return new frames / never mutate inputs.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from _detector_fixtures import flat_bars, prefix_close_time

# Re-exported so Phase-3 test modules can import every helper from one place
# (same direct-import convention as the Phase 2 suites).
from conftest import _make_cfg, make_bars  # pytest puts tests/ on sys.path

from ai_trading.config import Config
from ai_trading.normalize import TIMEFRAME_MINUTES
from ai_trading.stores.bar_store import merge_and_write

__all__ = [
    "bt_cfg",
    "set_spreads",
    "write_bars_parquet",
    "make_bars",
    "_make_cfg",
    "flat_bars",
    "prefix_close_time",
]


def set_spreads(bars: pd.DataFrame, values) -> pd.DataFrame:
    """Return a copy of ``bars`` with the ``spread`` column replaced by
    ``values`` (length must equal len(bars), else ValueError)."""
    values = list(values)
    if len(values) != len(bars):
        raise ValueError(
            f"set_spreads invariant violated: {len(values)} values for {len(bars)} bars"
        )
    out = bars.copy()
    out["spread"] = values
    return out


def bt_cfg(**overrides) -> Config:
    """Thin wrapper over conftest ``_make_cfg`` carrying the Phase-3 backtest
    defaults; pass keyword overrides per test (never touches load_config)."""
    defaults = {
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
    return _make_cfg(**{**defaults, **overrides})


def write_bars_parquet(bars: pd.DataFrame, path: Path) -> Path:
    """Write ``bars`` through the single Parquet write path
    (``bar_store.merge_and_write``) and return the path.

    The timeframe is inferred from the median time_utc step. ``now_utc`` is
    placed after the last bar so the closed-bars guard never spuriously
    rejects historical synthetic fixtures (test-only; live collection keeps
    the true-clock guard inside merge_and_write).
    """
    diffs = bars["time_utc"].diff().dropna()
    if diffs.empty:
        raise ValueError(
            "write_bars_parquet invariant violated: need >= 2 bars to infer the timeframe"
        )
    minutes = int(diffs.mode().iloc[0].total_seconds() // 60)
    inverse = {m: tf for tf, m in TIMEFRAME_MINUTES.items()}
    if minutes not in inverse:
        raise ValueError(f"write_bars_parquet invariant violated: unknown bar step {minutes}min")
    now_after_last = bars["time_utc"].max() + pd.Timedelta(days=1)
    merge_and_write(
        new=bars,
        path=Path(path),
        timeframe=inverse[minutes],
        now_utc=now_after_last.to_pydatetime(),
    )
    return Path(path)
