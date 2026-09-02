"""Walk-forward window derivation + per-window canonical stats (BT-05).

Pure pandas — no I/O, no MetaTrader5, inputs never mutated. This module is
THE splitter of record (threat T-03-01): Phase 4's ML training reuses the
exact same windows (AI-04), so every invariant pinned here carries forward.

LOCKED CONVENTIONS (pinned by named tests):

- D-19 CHRONOLOGICAL SPLIT, EXPANDING TRAIN / ROLLING FIXED-LENGTH TEST:
  window k's test span is [b_k, b_k + test_days) with b_{k+1} == b_k +
  test_days — consecutive windows touch (next test_start == previous
  test_end), zero overlap, zero gaps, ascending order, NO shuffles anywhere
  (sklearn TimeSeriesSplit semantics; anti-pattern Pitfall 7).
  Train labels are ALL labels with entry_time STRICTLY BEFORE the window's
  test_start (expanding accumulation — a label AT test_start belongs to the
  TEST mask, never the train mask; boundary pinned by test).
- D-20 DAY-CONFIGURABLE WINDOWS: defaults live on Config (180/30), but the
  harness must work on small day-windows (1-2 days) so it is usable on the
  ~90-day store today. ``train_days`` is the documented/validated knob
  retained on the Window contract for Phase 4 — Phase 3 computes train
  masks from expanding accumulation (D-19), which for an expanding split is
  equivalent to "everything before test_start" regardless of train_days.
- ENTRY-TIME SPLITTING (Phase 4 purge contract): labels are assigned to the
  window containing their ENTRY bar time — NEVER their exit time. A label
  whose [entry_time, exit_time] life crosses a window boundary belongs to
  exactly one window (the entry one); Phase 4 must purge train labels whose
  outcome interval overlaps a test window separately (AFML ch. 7
  purging/embargo — the obligation is documented here, implemented there).
- D-22 PER-WINDOW REPORTS: window_stats_table gives full canonical stats
  per (window_id, symbol, timeframe); window_aggregate pools ALL symbols'
  labels per window into one cross-symbol row. Per-symbol grouping
  everywhere — never a global row (threat T-03-05).
- D-16 RAW + NET: both stats helpers compute canonical_stats twice (r_raw
  and r_net) and emit raw_/net_-prefixed columns plus
  cost_delta_expectancy = net_expectancy - raw_expectancy.

ZERO-LABEL CONTRACT (a supported state, never an error): empty entry times
yield zero windows; empty label frames flow through assignment and both
stats helpers as schema-correct empty frames with pinned dtypes. A
legitimate no-candidate range must never crash the harness or escape the
runner's exit-code contract.

``window_start``/``window_end`` in the stats frames are the OBSERVED
entry-time span of the labels inside each window (min/max entry_time); the
authoritative window boundaries live on the Window objects and in the
walkforward manifest written by backtest.reports.write_window_manifest.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ai_trading.backtest.stats import canonical_stats

_R_COLS = ("r_raw", "r_net")
_VARIANT_KEYS = ("win_rate", "profit_factor", "expectancy", "avg_r", "max_dd")
_COUNT_KEYS = ("trades", "wins", "losses", "timeouts")

#: Exact output schema of window_stats_table (empty-frame pinned too).
WINDOW_STATS_COLUMNS = (
    "window_id",
    "window_start",
    "window_end",
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

#: Exact output schema of window_aggregate (cross-symbol pooled rows).
WINDOW_AGG_COLUMNS = (
    "window_id",
    "window_start",
    "window_end",
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
    return ValueError(f"walkforward invariant violated: {message}")


@dataclass(frozen=True, eq=False)
class Window:
    """One walk-forward test window plus its label masks.

    ``train_mask``/``test_mask`` are boolean Series over the label index the
    windows were built from (no shuffles, input order preserved). ``eq=False``
    because structural equality over Series fields is ambiguous (elementwise
    truth value) — compare fields individually.

    ``train_days`` semantics: retained as documented metadata for Phase 4;
    Phase 3's train mask is expanding accumulation (every label with
    entry_time strictly before test_start — D-19), the SAME harness Phase 4
    consumes (AI-04, no shuffled splits anywhere).
    """

    test_start: pd.Timestamp
    test_end: pd.Timestamp
    window_id: int
    train_mask: pd.Series
    test_mask: pd.Series


def _validate_window_days(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise _invariant(f"{name} must be a positive integer (days), got {value!r}")
    return int(value)


def build_windows(
    entry_times: pd.Series,
    test_days: int,
    train_days: int,
    start: pd.Timestamp | None = None,
    end: pd.Timestamp | None = None,
) -> list[Window]:
    """Derive the chronological expanding-train / rolling-test windows.

    Boundaries: b_0 = floor(start to day), b_{k+1} = b_k + test_days days,
    one window per b_k <= end (zero overlap, zero gaps — D-19). The loop
    bound is <= (not <) so a label whose entry_time lands EXACTLY on the
    domain's last boundary is covered by the half-open window starting
    there — required by the exactly-one-window contract below and never
    emitting an empty trailing window (the plan's `while b_k < end` prose
    would strand a boundary-aligned max entry outside every window, which
    label_window_assignment correctly refuses). ``start``/``end`` default
    to min/max of ``entry_times``. ``train_days`` is the documented/validated
    knob retained on each Window (D-20); the train mask is expanding
    accumulation (entry_time strictly before test_start).

    Small day-windows (test_days=1, train_days=2) produce valid windows on
    short stores (D-20). Empty ``entry_times`` returns [] — a zero-candidate
    range is a supported state, never an error. test_days/train_days <= 0
    (or non-int) raise ValueError.
    """
    _validate_window_days(test_days, "test_days")
    _validate_window_days(train_days, "train_days")

    times = entry_times if isinstance(entry_times, pd.Series) else pd.Series(entry_times)
    if times.empty:
        return []
    if not pd.api.types.is_datetime64_any_dtype(times):
        times = pd.to_datetime(times)

    start = times.min() if start is None else pd.Timestamp(start)
    end = times.max() if end is None else pd.Timestamp(end)
    if pd.isna(start) or pd.isna(end):
        raise _invariant("start/end must not be NaT")
    if end < start:
        raise _invariant(f"inverted domain: end {end} < start {start}")

    b_0 = start.normalize()  # floor to day
    step = pd.Timedelta(days=int(test_days))
    windows: list[Window] = []
    b = b_0
    while b <= end:
        test_end = b + step
        windows.append(
            Window(
                test_start=b,
                test_end=test_end,
                window_id=len(windows),
                train_mask=times < b,  # expanding: strictly before (D-19)
                test_mask=(times >= b) & (times < test_end),
            )
        )
        b = test_end
    return windows


def label_window_assignment(labels: pd.DataFrame, windows: list[Window]) -> pd.DataFrame:
    """Assign every label to EXACTLY ONE window by its ENTRY bar time.

    Adds an int64 ``window_id`` column (window k = test_start <= entry_time
    < test_end; O(n log n) via searchsorted over the window starts). A label
    outside every window (or with a NaT entry_time) raises ValueError naming
    the entry_time — labels outside the domain are an error, never dropped
    silently (Pitfall 7). The input frame is never mutated. An empty labels
    frame returns a schema-correct empty frame (input columns + window_id),
    even with zero windows.
    """
    out = labels.copy()
    if out.empty:
        out["window_id"] = pd.Series(dtype="int64", index=out.index)
        return out
    if "entry_time" not in out.columns:
        raise _invariant("labels is missing required columns ['entry_time']")
    if not windows:
        raise _invariant(
            "labels present but no windows derived — labels outside the window "
            "domain are an error, never dropped silently"
        )

    starts = pd.DatetimeIndex([w.test_start for w in windows])
    ends = pd.DatetimeIndex([w.test_end for w in windows])
    ids = [int(w.window_id) for w in windows]
    # Exactly-one-window precondition: starts strictly increasing, windows
    # disjoint (next start >= previous end). build_windows guarantees this;
    # a hand-built overlapping list would make "exactly one" ambiguous.
    if len(starts) > 1 and (
        not starts.is_monotonic_increasing or bool((starts[1:] < ends[:-1]).any())
    ):
        raise _invariant("windows must be strictly chronological and non-overlapping")

    times = pd.to_datetime(out["entry_time"])
    valid = ~times.isna()
    pos = pd.Series(-1, index=out.index, dtype="int64")
    if valid.any():
        pos.loc[valid] = starts.searchsorted(times.loc[valid].to_numpy(), side="right") - 1

    inside = pos >= 0
    assigned = pd.Series(False, index=out.index)
    if inside.any():
        pos_inside = pos.loc[inside].to_numpy()
        assigned.loc[inside] = times.loc[inside].to_numpy() < ends.to_numpy()[pos_inside]

    if not bool(assigned.all()):
        bad_idx = out.index[~assigned][0]
        raise _invariant(
            f"label entry_time {out.loc[bad_idx, 'entry_time']} does not fall in "
            "exactly one window (zero matches) — labels outside the domain are "
            "an error, never dropped silently"
        )
    out["window_id"] = pd.Series([ids[p] for p in pos.tolist()], index=out.index, dtype="int64")
    return out


def _stats_row(
    window_id: int, group: pd.DataFrame, symbol: str | None, timeframe: str | None
) -> dict:
    """Canonical raw+net stats for one label group (canonical_stats reuse)."""
    raw = canonical_stats(group, "r_raw")
    net = canonical_stats(group, "r_net")
    row: dict = {
        "window_id": int(window_id),
        "window_start": pd.Timestamp(group["entry_time"].min()),
        "window_end": pd.Timestamp(group["entry_time"].max()),
    }
    if symbol is not None:
        row["symbol"] = str(symbol)
        row["timeframe"] = str(timeframe)
    for key in _COUNT_KEYS:
        row[key] = raw[key]
    for key in _VARIANT_KEYS:
        row[f"raw_{key}"] = raw[key]
        row[f"net_{key}"] = net[key]
    row["cost_delta_expectancy"] = net["expectancy"] - raw["expectancy"]
    return row


def _check_r_col(r_col: object) -> None:
    if r_col not in _R_COLS:
        raise _invariant(f"r_col {r_col!r} must be one of {_R_COLS}")


def _require_columns(labels_w: pd.DataFrame, required: tuple[str, ...]) -> None:
    missing = [col for col in required if col not in labels_w.columns]
    if missing:
        raise _invariant(f"labels_w is missing required columns {missing}")


def _cast_stats_frame(frame: pd.DataFrame, columns: tuple[str, ...]) -> pd.DataFrame:
    for col in columns:
        if col == "window_id" or col in _COUNT_KEYS:
            frame[col] = frame[col].astype("int64")
        elif col in ("window_start", "window_end"):
            frame[col] = frame[col].astype("datetime64[us]")
        elif col in ("symbol", "timeframe"):
            frame[col] = frame[col].astype(_STR_DTYPE)
        else:
            frame[col] = frame[col].astype("float64")
    return frame


def _empty_stats_frame(columns: tuple[str, ...]) -> pd.DataFrame:
    data: dict = {}
    for col in columns:
        if col == "window_id" or col in _COUNT_KEYS:
            data[col] = pd.Series(dtype="int64")
        elif col in ("window_start", "window_end"):
            data[col] = pd.Series(dtype="datetime64[us]")
        elif col in ("symbol", "timeframe"):
            data[col] = pd.Series(dtype=_STR_DTYPE)
        else:
            data[col] = pd.Series(dtype="float64")
    return pd.DataFrame(data)


def window_stats_table(labels_w: pd.DataFrame, r_col: str = "r_net") -> pd.DataFrame:
    """Full canonical stats per (window_id, symbol, timeframe) — D-22.

    Reuses stats.canonical_stats per group for BOTH r variants (D-16:
    raw_/net_ columns plus cost_delta_expectancy). ``r_col`` is validated
    and retained for API symmetry with canonical_stats; D-16 requires both
    variants in every row, so both are always emitted. Output columns are
    exactly WINDOW_STATS_COLUMNS sorted by (window_id, symbol, timeframe).
    Empty input yields a schema-correct empty frame (pinned dtypes, no
    raise) — a zero-candidate range is supported, never an error.
    """
    _check_r_col(r_col)
    _require_columns(
        labels_w, ("window_id", "symbol", "timeframe", "outcome", "entry_time", "r_raw", "r_net")
    )
    if labels_w.empty:
        return _empty_stats_frame(WINDOW_STATS_COLUMNS)

    rows = [
        _stats_row(window_id, group, symbol, timeframe)
        for (window_id, symbol, timeframe), group in labels_w.groupby(
            ["window_id", "symbol", "timeframe"], sort=True
        )
    ]
    frame = pd.DataFrame(rows, columns=WINDOW_STATS_COLUMNS)
    frame = _cast_stats_frame(frame, WINDOW_STATS_COLUMNS)
    return frame.sort_values(["window_id", "symbol", "timeframe"]).reset_index(drop=True)


def window_aggregate(labels_w: pd.DataFrame, r_col: str = "r_net") -> pd.DataFrame:
    """Per-window aggregate ACROSS symbols (D-22) — canonical stats pooled
    over every label in the window regardless of symbol/timeframe.

    Groups by window_id ONLY (explicit cross-symbol pooling; per-symbol rows
    live in window_stats_table — threat T-03-05). Output columns are exactly
    WINDOW_AGG_COLUMNS sorted by window_id. Empty input yields a
    schema-correct empty frame (pinned dtypes, no raise).
    """
    _check_r_col(r_col)
    _require_columns(labels_w, ("window_id", "outcome", "entry_time", "r_raw", "r_net"))
    if labels_w.empty:
        return _empty_stats_frame(WINDOW_AGG_COLUMNS)

    rows = [
        _stats_row(window_id, group, None, None)
        for window_id, group in labels_w.groupby("window_id", sort=True)
    ]
    frame = pd.DataFrame(rows, columns=WINDOW_AGG_COLUMNS)
    frame = _cast_stats_frame(frame, WINDOW_AGG_COLUMNS)
    return frame.sort_values("window_id").reset_index(drop=True)
