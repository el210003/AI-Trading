"""THE anti-lookahead suite (BT-01 / ROADMAP SC1) — proves the whole replay
decision path (chain -> as-of slice -> candidate -> next-bar fill -> label)
is prefix-stable: replay(bars.iloc[:k]) labels equal EXACTLY the rows of
replay(full) whose entry_time < prefix_close_time(bars, k) (STRICT — a D-04
fill decided at bar k-1 has entry_time == t_k and cannot exist in the prefix
run), check_exact=True, over 1-by-1 AND chunked appends.

World: real Phase 2 chain output over a sculpted M15 frame (equal-low pool
at 1.07 swept at bar 30; M15 zone legs 1.07 -> 1.16; zone2 mitigated exactly
at bar 33; H1 zone 1.09-1.13 supplies a bullish payload bias; H4 flat).
Exactly one label: decision bar 33, entry bar 34 (open 1.10, spread 34 pts,
slip 0.5 pip), SL 1.068, TP 1.16, rr 1.875. Conventions adapted from
test_repaint.py + _detector_fixtures.assert_point_in_time_prefix_equality.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest
from _backtest_fixtures import bt_cfg, flat_bars, make_bars, prefix_close_time
from test_replay import entry_resolver as fake_resolver

from ai_trading.backtest.chain import run_chain
from ai_trading.backtest.replay import replay_symbol

SYMBOL = "EURUSD"
START = datetime(2026, 8, 20, 0, 0)
COUNT = 140  # entry at bar 34; 96-bar window [34, 130) fits for k >= 130
CFG = bt_cfg()


def _m15_world() -> pd.DataFrame:
    """Base 1.10/1.105 bars; equal-low pool touches at 12/16 (1.07); sweep
    pierce at 30 (1.068, same-bar close-back at 1.105); zone leg high at 20
    (1.16). Zigzag: low@12 -> high@20 -> low@30 -> zones (1.07-1.16) and
    (1.068-1.16)."""
    df = make_bars(SYMBOL, "M15", START, COUNT)
    df["open"] = 1.10000
    df["low"] = 1.10000
    df["close"] = 1.10500
    df["high"] = 1.10500
    for idx, price in ((12, 1.07000), (16, 1.07000), (30, 1.06800)):
        df.iloc[idx, df.columns.get_indexer(["low"])] = price
    df.iloc[20, df.columns.get_indexer(["high"])] = 1.16000
    return df


def _h1_world() -> pd.DataFrame:
    """H1 legs low@2 (1.09) / high@4 (1.13) -> zone 1.09-1.13 (eq 1.11)
    created at the close of H1 bar 6 (T0+7h) — bullish bias for the M15
    decision bar 33 (close 1.105 < 1.11), strictly before it."""
    df = make_bars(SYMBOL, "H1", START, 20)
    df["open"] = 1.10000
    df["low"] = 1.10000
    df["close"] = 1.10500
    df["high"] = 1.10500
    df.iloc[2, df.columns.get_indexer(["low"])] = 1.09000
    df.iloc[4, df.columns.get_indexer(["high"])] = 1.13000
    return df


H1_BARS = _h1_world()
H4_BARS = flat_bars(SYMBOL, "H4", START, 20, price=1.10)  # flat -> no H4 zones/bias


def runner(bars: pd.DataFrame) -> pd.DataFrame:
    """BT-01 production shape: the chain runs over the loaded (prefix)
    range; the replay consumes it through the as-of slicer."""
    return replay_symbol(bars, run_chain(bars, H1_BARS, H4_BARS), CFG, fake_resolver)


def barrier_stub(position: object, bars: pd.DataFrame, cfg: object) -> dict:
    """Local stub of 03-02's walk_barriers END-OF-DATA lens: the window
    [entry_idx, entry_idx + time_barrier_bars) is clamped to len(bars); an
    incomplete window yields TIMEOUT at the last available bar."""
    resolved = position.entry_idx + cfg.time_barrier_bars <= len(bars)
    if resolved:
        last_idx = position.entry_idx + cfg.time_barrier_bars - 1
        return {
            "outcome": "WIN",
            "exit_time": bars["time_utc"].iloc[last_idx],
            "exit_price": float(bars["close"].iloc[last_idx]),
            "exit_idx": last_idx,
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


def runner_bound(bars: pd.DataFrame) -> pd.DataFrame:
    return replay_symbol(bars, run_chain(bars, H1_BARS, H4_BARS), CFG, barrier_stub)


BARS = _m15_world()
FULL = runner(BARS.copy())
ENTRY_TIME = FULL.iloc[0]["entry_time"] if len(FULL) else None


@pytest.mark.unit
def test_world_produces_exactly_one_expected_label():
    """Fixture sanity: the sculpted world yields the single hand-derived
    label (decision bar 33 -> entry bar 34)."""
    assert len(FULL) == 1
    row = FULL.iloc[0]
    assert row["direction"] == "long"
    assert row["entry_time"] == BARS.iloc[34]["time_utc"]
    assert row["entry_price"] == 1.10000 + 34 * 0.00001 + 0.5 * 0.0001
    assert row["sl_price"] == 1.06800
    assert row["tp_price"] == 1.16000
    assert row["rr"] == (1.16 - 1.10) / (1.10 - 1.068)
    assert row["bias_h1"] == "bullish" and row["bias_h4"] is pd.NA


@pytest.mark.unit
def test_prefix_equivalence_one_by_one():
    """For every prefix, prefix labels == full labels with entry_time
    STRICTLY before the prefix close time (check_exact=True)."""
    for k in range(28, len(BARS)):
        prefix = runner(BARS.iloc[:k].copy())
        visible = FULL[FULL["entry_time"] < prefix_close_time(BARS, k)].reset_index(drop=True)
        pd.testing.assert_frame_equal(prefix, visible, check_exact=True)


@pytest.mark.unit
def test_prefix_equivalence_chunked_appends():
    """Equality also holds when future bars arrive in +5/+17-bar chunks and
    at the final exact prefix lengths."""
    for chunk in (5, 17):
        ks = list(range(28, len(BARS) - chunk, chunk)) + [len(BARS) - 1]
        for k in ks:
            prefix = runner(BARS.iloc[:k].copy())
            visible = FULL[FULL["entry_time"] < prefix_close_time(BARS, k)].reset_index(drop=True)
            pd.testing.assert_frame_equal(prefix, visible, check_exact=True)


@pytest.mark.unit
def test_prefix_boundary_timeout_truncation():
    """With the barrier-stub resolver (03-02 end-of-data lens):
    (a) fully-resolved labels (window inside the prefix) are byte-identical
        to the full-run row;
    (b) labels whose post-entry window crosses the prefix boundary are
        TIMEOUT in the prefix run — EXPECTED truncation, never a leak;
    (c) the decision path (candidate -> entry -> fill fields) is
        prefix-stable for BOTH cases."""
    assert len(FULL) == 1
    full_bound = runner_bound(BARS.copy())
    assert len(full_bound) == 1
    assert full_bound.iloc[0]["outcome"] == "WIN"  # window [34, 130) fits in 140 bars

    # (a) fully resolved: k >= 34 + 96 = 130
    for k in range(130, len(BARS)):
        prefix = runner_bound(BARS.iloc[:k].copy())
        pd.testing.assert_frame_equal(prefix, full_bound, check_exact=True)

    # (b) truncated: 35 <= k < 130 -> TIMEOUT at the last available bar
    for k in (35, 60, 100, 129):
        prefix = runner_bound(BARS.iloc[:k].copy())
        assert len(prefix) == 1
        assert prefix.iloc[0]["outcome"] == "TIMEOUT"
        assert prefix.iloc[0]["exit_idx"] == k - 1

    # (c) decision path prefix-stable in both regimes
    decision_cols = [
        "entry_time", "entry_price", "sl_price", "tp_price", "rr",
        "pool_id", "event_id", "zone_id", "bias_h1", "bias_h4", "direction",
    ]
    for k in (35, 40, 60, 90, 129, 130, 135, 139):
        prefix = runner_bound(BARS.iloc[:k].copy())
        assert len(prefix) == 1
        for col in decision_cols:
            got, expected = prefix.iloc[0][col], full_bound.iloc[0][col]
            if pd.isna(got) and pd.isna(expected):
                continue  # NA == NA is ambiguous in pandas
            assert got == expected, (k, col)


@pytest.mark.unit
def test_no_future_bar_access():
    """Every label of a prefix run references only bars inside that prefix:
    the entry bar (located by entry_time — the label schema carries no
    entry_idx column) and the exit bar both stay within the prefix."""
    times = BARS["time_utc"].reset_index(drop=True)
    for k in (40, 100, 129, 139):
        prefix = runner_bound(BARS.iloc[:k].copy())
        for _, row in prefix.iterrows():
            entry_pos = int(times[times == row["entry_time"]].index[0])
            assert entry_pos < k
            assert row["exit_idx"] <= k - 1


@pytest.mark.unit
def test_labels_deterministic():
    """Same inputs run twice -> byte-identical label frames."""
    again = runner(BARS.copy())
    pd.testing.assert_frame_equal(FULL, again, check_exact=True)
    bound_again = runner_bound(BARS.copy())
    pd.testing.assert_frame_equal(runner_bound(BARS.copy()), bound_again, check_exact=True)
