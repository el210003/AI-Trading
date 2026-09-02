"""Unit tests for canonical stats (BT-04): hand-computed R series, the pinned
edge-guard table (empty / all-win / all-loss / zero-loss PF / zero-both PF —
nan/inf/0.0, never raise), the A4 win-rate denominator and A5 TIMEOUT
inclusion, per-(symbol, timeframe) grouping without cross-symbol leakage, and
the D-16 raw-vs-net cost delta computed over labels produced by the REAL
walk_barriers (convention (a): per-trade delta = -2*slip_px/risk)."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest
from _backtest_fixtures import bt_cfg, make_bars, set_spreads
from _detector_fixtures import sculpt_high, sculpt_low

from ai_trading.backtest.barriers import walk_barriers
from ai_trading.backtest.costs import effective_spread_points, entry_fill_price
from ai_trading.backtest.replay import Position
from ai_trading.backtest.stats import STATS_COLUMNS, canonical_stats, stats_by_symbol_timeframe

START = datetime(2026, 8, 20, 0, 0)
BASE = 1.10000
SL = 1.09900
TP = 1.10200
ENTRY_IDX = 5


def _labels_frame(outcomes, r_values, symbol="EURUSD", timeframe="M15") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": [symbol] * len(outcomes),
            "timeframe": [timeframe] * len(outcomes),
            "outcome": list(outcomes),
            "r_raw": list(r_values),
            "r_net": list(r_values),
        }
    )


# ---------------------------------------------------------------------------
# Hand-computed series
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_hand_computed_series():
    """wins 2 (+1.0, +0.5), losses 1 (-1.0), timeouts 1 (-0.1)."""
    labels = _labels_frame(["WIN", "WIN", "LOSS", "TIMEOUT"], [1.0, 0.5, -1.0, -0.1])
    stats = canonical_stats(labels, "r_raw")
    assert set(stats) == {
        "trades", "wins", "losses", "timeouts", "win_rate", "timeouts_share",
        "profit_factor", "expectancy", "avg_r", "max_dd", "r_col",
    }
    assert stats["trades"] == 4
    assert stats["wins"] == 2 and stats["losses"] == 1 and stats["timeouts"] == 1
    assert stats["win_rate"] == pytest.approx(2 / 3)
    assert stats["timeouts_share"] == pytest.approx(0.25)
    assert stats["profit_factor"] == pytest.approx(1.5)
    # A5: (1.0 + 0.5 - 1.0 - 0.1) / 4 over ALL trades
    assert stats["expectancy"] == pytest.approx(0.1)
    assert stats["avg_r"] == pytest.approx(0.1)
    # R curve: eq = [1.0, 1.5, 0.5, 0.4]; cummax = [1.0, 1.5, 1.5, 1.5]
    # -> min drawdown = 0.4/1.5 - 1
    assert stats["max_dd"] == pytest.approx(0.4 / 1.5 - 1)
    assert stats["r_col"] == "r_raw"


@pytest.mark.unit
def test_invalid_r_col_raises():
    labels = _labels_frame(["WIN"], [1.0])
    with pytest.raises(ValueError, match="invariant violated"):
        canonical_stats(labels, "r_gross")


# ---------------------------------------------------------------------------
# Edge guards (never raise)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_empty_labels_yield_nan_stats_and_zero_dd():
    stats = canonical_stats(_labels_frame([], []), "r_net")
    assert stats["trades"] == 0
    assert stats["wins"] == 0 and stats["losses"] == 0 and stats["timeouts"] == 0
    assert pd.isna(stats["win_rate"])
    assert pd.isna(stats["timeouts_share"])
    assert pd.isna(stats["profit_factor"])
    assert pd.isna(stats["expectancy"]) and pd.isna(stats["avg_r"])
    assert stats["max_dd"] == 0.0


@pytest.mark.unit
@pytest.mark.parametrize(
    ("outcomes", "r_values", "expected_pf"),
    [
        (["WIN", "WIN"], [1.0, 0.5], float("inf")),  # zero loss-sum, positive win-sum
        (["LOSS", "LOSS"], [-1.0, -0.5], 0.0),  # zero win-sum over real losses
        (["WIN", "LOSS"], [1.0, -1.0], 1.0),
        (["TIMEOUT", "TIMEOUT"], [0.0, 0.0], float("nan")),  # zero-both guard
        (["WIN", "LOSS", "TIMEOUT"], [0.0, 0.0, 0.0], float("nan")),
        (["WIN", "LOSS", "TIMEOUT"], [1.0, -1.0, -0.1], 1.0),  # timeout excluded
        (["TIMEOUT", "TIMEOUT"], [-0.1, -0.2], float("nan")),  # negative timeouts
    ],
)
def test_profit_factor_guards(outcomes, r_values, expected_pf):
    stats = canonical_stats(_labels_frame(outcomes, r_values), "r_raw")
    if pd.isna(expected_pf):
        assert pd.isna(stats["profit_factor"])
    else:
        assert stats["profit_factor"] == expected_pf


@pytest.mark.unit
def test_all_timeout_stats():
    """All-TIMEOUT run: win_rate nan (A4), PF nan (no decided trades), but
    expectancy INCLUDES the timeouts (A5)."""
    labels = _labels_frame(["TIMEOUT", "TIMEOUT"], [-0.1, -0.2])
    stats = canonical_stats(labels, "r_net")
    assert stats["trades"] == 2 and stats["timeouts"] == 2
    assert pd.isna(stats["win_rate"])
    assert pd.isna(stats["profit_factor"])
    assert stats["expectancy"] == pytest.approx(-0.15)
    assert stats["avg_r"] == pytest.approx(-0.15)


@pytest.mark.unit
def test_all_win_stats():
    labels = _labels_frame(["WIN", "WIN"], [1.0, 0.5])
    stats = canonical_stats(labels, "r_raw")
    assert stats["win_rate"] == 1.0
    assert stats["profit_factor"] == float("inf")
    assert stats["max_dd"] == 0.0  # never below the running peak


@pytest.mark.unit
def test_single_trade_stats():
    stats = canonical_stats(_labels_frame(["WIN"], [1.0]), "r_net")
    assert stats["trades"] == 1
    assert stats["win_rate"] == 1.0
    assert stats["profit_factor"] == float("inf")
    assert stats["expectancy"] == pytest.approx(1.0)
    assert stats["max_dd"] == 0.0


@pytest.mark.unit
def test_win_rate_denominator_ignores_timeouts():
    """2 wins / 2 losses / 3 timeouts -> win_rate 0.5 (denominator 4, not 7)."""
    labels = _labels_frame(
        ["WIN", "WIN", "LOSS", "LOSS", "TIMEOUT", "TIMEOUT", "TIMEOUT"],
        [1.0, 0.5, -1.0, -0.5, -0.1, -0.1, -0.1],
    )
    stats = canonical_stats(labels, "r_net")
    assert stats["win_rate"] == 0.5
    assert stats["timeouts_share"] == pytest.approx(3 / 7)
    assert stats["trades"] == 7


# ---------------------------------------------------------------------------
# Per-(symbol, timeframe) grouping — never global
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_stats_by_symbol_timeframe_groups_without_leakage():
    rows = [
        ("EURUSD", "M15", "WIN", 1.0),
        ("EURUSD", "M15", "WIN", 0.5),
        ("EURUSD", "H1", "WIN", 1.0),
        ("EURUSD", "H1", "LOSS", -1.0),
        ("GBPUSD", "M15", "TIMEOUT", -0.1),
        ("GBPUSD", "M15", "TIMEOUT", -0.2),
        ("GBPUSD", "H1", "LOSS", -1.0),
    ]
    labels = pd.DataFrame(
        {
            "symbol": [r[0] for r in rows],
            "timeframe": [r[1] for r in rows],
            "outcome": [r[2] for r in rows],
            "r_raw": [r[3] for r in rows],
            "r_net": [r[3] for r in rows],
        }
    )
    stats = stats_by_symbol_timeframe(labels)
    assert len(stats) == 4
    assert list(stats.columns) == list(STATS_COLUMNS)
    # sorted by (symbol, timeframe)
    assert list(stats["symbol"]) == ["EURUSD", "EURUSD", "GBPUSD", "GBPUSD"]
    assert list(stats["timeframe"]) == ["H1", "M15", "H1", "M15"]

    def _row(symbol, timeframe):
        return stats[(stats["symbol"] == symbol) & (stats["timeframe"] == timeframe)].iloc[0]

    eur_m15 = _row("EURUSD", "M15")
    assert eur_m15["trades"] == 2 and eur_m15["raw_win_rate"] == 1.0
    eur_h1 = _row("EURUSD", "H1")
    assert eur_h1["trades"] == 2 and eur_h1["raw_win_rate"] == 0.5
    gbp_m15 = _row("GBPUSD", "M15")
    assert gbp_m15["trades"] == 2 and pd.isna(gbp_m15["raw_win_rate"])
    gbp_h1 = _row("GBPUSD", "H1")
    assert gbp_h1["trades"] == 1 and gbp_h1["raw_win_rate"] == 0.0
    # per-group counts never leak across symbols
    assert list(stats["wins"]) == [1, 2, 0, 0]
    assert list(stats["losses"]) == [1, 0, 1, 0]
    assert list(stats["timeouts"]) == [0, 0, 0, 2]
    # StringDtype / int64 pins (detector-frame style)
    assert stats["symbol"].dtype == pd.StringDtype()
    assert stats["trades"].dtype == "int64"


@pytest.mark.unit
def test_stats_by_symbol_timeframe_empty_labels():
    empty = pd.DataFrame(columns=["symbol", "timeframe", "outcome", "r_raw", "r_net"])
    stats = stats_by_symbol_timeframe(empty)
    assert stats.empty
    assert list(stats.columns) == list(STATS_COLUMNS)
    assert stats["symbol"].dtype == pd.StringDtype()
    assert stats["trades"].dtype == "int64"
    assert stats["cost_delta_expectancy"].dtype == "float64"


# ---------------------------------------------------------------------------
# D-16 cost delta over REAL walk_barriers output (convention (a))
# ---------------------------------------------------------------------------

def _walked_labels() -> pd.DataFrame:
    """Label records produced by the REAL walk_barriers over a pinned path:
    EURUSD, risk 0.00100, spread 20 pt, slippage 0.5 pip — one WIN, one LOSS,
    one TIMEOUT, all long with identical structure."""
    cfg = bt_cfg()
    rows = []
    for outcome in ("WIN", "LOSS", "TIMEOUT"):
        bars = make_bars("EURUSD", "M15", START, 20)
        for col in ("open", "high", "low", "close"):
            bars[col] = BASE
        bars = set_spreads(bars, [20] * len(bars))
        if outcome == "WIN":
            bars = sculpt_high(bars, ENTRY_IDX + 1, TP)
        elif outcome == "LOSS":
            bars = sculpt_low(bars, ENTRY_IDX + 1, SL)
        spread = effective_spread_points(cfg, "EURUSD", bars.iloc[ENTRY_IDX]["spread"])
        position = Position(
            symbol="EURUSD",
            timeframe="M15",
            direction="long",
            entry_open=BASE,
            entry_spread_points=spread,
            entry_price=entry_fill_price("long", BASE, spread, cfg, "EURUSD"),
            sl_price=SL,
            tp_price=TP,
            entry_idx=ENTRY_IDX,
            entry_time=bars["time_utc"].iloc[ENTRY_IDX],
            evidence={},
            rr=2.0,
        )
        result = walk_barriers(position, bars, cfg)
        assert result["outcome"] == outcome  # fixture sanity: the sculpted world
        rows.append(
            {
                "symbol": "EURUSD",
                "timeframe": "M15",
                "outcome": result["outcome"],
                "r_raw": result["r_raw"],
                "r_net": result["r_net"],
            }
        )
    return pd.DataFrame(rows)


@pytest.mark.unit
def test_cost_delta_expectancy_from_real_walk_barriers():
    """Per convention (a) every per-trade r_net - r_raw == -2*slip_px/risk ==
    -0.10 exactly (2x slippage in PRICE units over the structural risk; the
    spread cancels), so cost_delta_expectancy == -0.10 for the walked fixture
    (asserted as an exact float delta — NEVER as an additive '2x slippage' R
    claim, which only holds in price units)."""
    labels = _walked_labels()
    assert set(labels["outcome"]) == {"WIN", "LOSS", "TIMEOUT"}
    per_trade = labels["r_net"] - labels["r_raw"]
    assert (per_trade - -0.10).abs().max() < 1e-12

    stats = stats_by_symbol_timeframe(labels)
    assert len(stats) == 1
    row = stats.iloc[0]
    assert row["cost_delta_expectancy"] == pytest.approx(-0.10, abs=1e-12)
    assert row["net_expectancy"] == pytest.approx(row["raw_expectancy"] - 0.10, abs=1e-12)
    # both variants present with the delta visible
    for col in ("raw_expectancy", "net_expectancy", "cost_delta_expectancy"):
        assert col in stats.columns
