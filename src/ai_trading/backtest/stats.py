"""Canonical backtest statistics (BT-04) — pure pandas with explicit edge
guards, computed per (symbol, timeframe) ONLY (never global — threat
T-03-04). Everything is in R units, never currency.

PINNED CONVENTIONS:

- A4 win-rate denominator: win_rate = wins / (wins + losses); TIMEOUT is
  EXCLUDED from the denominator and reported separately as timeouts_share
  (timeouts / trades). A run of only TIMEOUTs yields win_rate = nan, not 0.
- A5 expectancy / avg_r: mean signed R over ALL trades INCLUDING TIMEOUTs
  (a timeout's R ties to its final-close exit and is usually slightly
  negative) — both keys kept for report compatibility.
- D-16 raw + net: every stat is computed twice — r_col="r_raw" (spread-only)
  and r_col="r_net" (spread + slippage) — and stats_by_symbol_timeframe
  exposes both variants plus cost_delta_expectancy = net - raw so the cost
  impact is visible in R units (per convention (a) of backtest.barriers the
  per-trade delta is exactly -2*slip_px/risk; the spread cancels).
- profit_factor is a DECIDED-trade ratio, A4-consistent with the win-rate
  denominator: R-sign sums (sum(r > 0) / abs(sum(r < 0))) over rows whose
  outcome is WIN or LOSS — TIMEOUT rows are excluded from BOTH sums. Zero
  loss-sum with positive win-sum -> inf; both zero -> nan. (The plan's
  hand-pinned series — wins +1.0/+0.5, loss -1.0, timeout -0.1 — pins PF at
  exactly 1.5, i.e. the -0.1 timeout never pollutes the denominator; an
  all-TIMEOUT run therefore reports PF nan, mirroring its nan win_rate.)
  max_dd = min(eq / eq.cummax() - 1) over eq = r.cumsum() (per-trade
  cumulative R curve, ALL trades incl. TIMEOUT); empty input -> 0.0.
- NaN propagation never raises: an empty or all-NaN series yields nan
  fields, never exceptions.

Pure functions: no I/O, no MetaTrader5, inputs never mutated.
"""

from __future__ import annotations

import pandas as pd

_R_COLUMNS = ("r_raw", "r_net")
_VARIANT_KEYS = ("win_rate", "profit_factor", "expectancy", "avg_r", "max_dd")

#: Exact output schema of stats_by_symbol_timeframe (empty-frame pinned too).
STATS_COLUMNS = (
    "symbol",
    "timeframe",
    "trades",
    "wins",
    "losses",
    "timeouts",
    "raw_win_rate",
    "net_win_rate",
    "raw_profit_factor",
    "net_profit_factor",
    "raw_expectancy",
    "net_expectancy",
    "raw_avg_r",
    "net_avg_r",
    "raw_max_dd",
    "net_max_dd",
    "cost_delta_expectancy",
)

_STR_DTYPE = pd.StringDtype()


def _invariant(message: str) -> ValueError:
    return ValueError(f"stats invariant violated: {message}")


def canonical_stats(labels: pd.DataFrame, r_col: str) -> dict:
    """Canonical statistics over one label frame for the R variant ``r_col``.

    Returns exactly the keys {trades, wins, losses, timeouts, win_rate,
    timeouts_share, profit_factor, expectancy, avg_r, max_dd, r_col} —
    see the module docstring for the pinned A4/A5/D-16 conventions and the
    nan/inf guard table.
    """
    if r_col not in _R_COLUMNS:
        raise _invariant(f"r_col {r_col!r} must be one of {_R_COLUMNS}")
    required = ("outcome", r_col)
    missing = [col for col in required if col not in labels.columns]
    if missing:
        raise _invariant(f"labels is missing required columns {missing}")

    outcomes = labels["outcome"]
    r = labels[r_col]
    trades = int(len(labels))
    wins = int((outcomes == "WIN").sum())
    losses = int((outcomes == "LOSS").sum())
    timeouts = int((outcomes == "TIMEOUT").sum())

    # A4: TIMEOUT excluded from the win-rate denominator, share reported apart.
    decided = wins + losses
    win_rate = wins / decided if decided else float("nan")
    timeouts_share = timeouts / trades if trades else float("nan")

    # PF is a decided-trade ratio (A4-consistent): TIMEOUT rows are excluded
    # from both R-sign sums — the hand-pinned plan series (timeout -0.1)
    # requires the denominator to carry LOSS rows only.
    decided_mask = outcomes != "TIMEOUT"
    decided_r = r[decided_mask]
    win_sum = float(decided_r[decided_r > 0].sum())
    loss_sum = float(decided_r[decided_r < 0].sum())
    if loss_sum == 0.0:
        profit_factor = float("inf") if win_sum > 0.0 else float("nan")
    else:
        profit_factor = win_sum / abs(loss_sum)

    # A5: signed R over ALL trades, TIMEOUTs included.
    expectancy = float(r.mean()) if trades else float("nan")
    avg_r = expectancy

    if trades:
        eq = r.cumsum()
        max_dd = float((eq / eq.cummax() - 1).min())
    else:
        max_dd = 0.0

    return {
        "trades": trades,
        "wins": wins,
        "losses": losses,
        "timeouts": timeouts,
        "win_rate": win_rate,
        "timeouts_share": timeouts_share,
        "profit_factor": profit_factor,
        "expectancy": expectancy,
        "avg_r": avg_r,
        "max_dd": max_dd,
        "r_col": r_col,
    }


def stats_by_symbol_timeframe(labels: pd.DataFrame) -> pd.DataFrame:
    """Aggregate canonical stats per (symbol, timeframe) for r_raw AND r_net.

    Groups strictly by ("symbol", "timeframe") — never a global row (threat
    T-03-04). Output carries the raw_/net_ prefixed variants of every
    variant stat plus cost_delta_expectancy = net_expectancy -
    raw_expectancy (D-16, in R units). Empty input yields a schema-correct
    empty frame with exactly STATS_COLUMNS and pinned dtypes.
    """
    required = ("symbol", "timeframe", "outcome", "r_raw", "r_net")
    missing = [col for col in required if col not in labels.columns]
    if missing:
        raise _invariant(f"labels is missing required columns {missing}")

    rows: list[dict] = []
    for (symbol, timeframe), group in labels.groupby(["symbol", "timeframe"], sort=True):
        raw = canonical_stats(group, "r_raw")
        net = canonical_stats(group, "r_net")
        row: dict = {
            "symbol": str(symbol),
            "timeframe": str(timeframe),
            "trades": raw["trades"],
            "wins": raw["wins"],
            "losses": raw["losses"],
            "timeouts": raw["timeouts"],
        }
        for key in _VARIANT_KEYS:
            row[f"raw_{key}"] = raw[key]
            row[f"net_{key}"] = net[key]
        row["cost_delta_expectancy"] = net["expectancy"] - raw["expectancy"]
        rows.append(row)

    if not rows:
        return _empty_stats_frame()

    frame = pd.DataFrame(rows, columns=STATS_COLUMNS)
    frame["symbol"] = frame["symbol"].astype(_STR_DTYPE)
    frame["timeframe"] = frame["timeframe"].astype(_STR_DTYPE)
    for col in ("trades", "wins", "losses", "timeouts"):
        frame[col] = frame[col].astype("int64")
    for col in STATS_COLUMNS:
        if col not in ("symbol", "timeframe", "trades", "wins", "losses", "timeouts"):
            frame[col] = frame[col].astype("float64")
    return frame.sort_values(["symbol", "timeframe"]).reset_index(drop=True)


def _empty_stats_frame() -> pd.DataFrame:
    """Empty frame with exactly STATS_COLUMNS and pinned dtypes."""
    data = {}
    for col in STATS_COLUMNS:
        if col in ("symbol", "timeframe"):
            data[col] = pd.Series(dtype=_STR_DTYPE)
        elif col in ("trades", "wins", "losses", "timeouts"):
            data[col] = pd.Series(dtype="int64")
        else:
            data[col] = pd.Series(dtype="float64")
    return pd.DataFrame(data)
