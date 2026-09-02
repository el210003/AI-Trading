"""Forward-pass replay state machine (per symbol, M15) — the loop that turns
chain output + entry candidates into labeled trades. Sequential-loop style
after detectors/pools.py::_detect_for_symbol, deliberately not vectorized.

Locked decisions implemented here:
- D-04: entry fill = NEXT bar's open (decision at the close of bar S, fill
  at bar S+1's open) with the BT-02 cost model; no intrabar/limit fills.
- D-05: one at a time per (symbol, timeframe) — while a position slot is
  held, no new candidate is generated. Slot-release timing: the resolver is
  invoked ONCE at fill time and returns the complete outcome (including
  exit_idx); the label row is appended at fill time, but the slot stays
  held until the loop advances PAST the resolver's exit_idx (a naive
  next-bar release would allow overlapping trades).
- D-07: the first N bars are warmup — candidates inside warmup are silently
  skipped, never errors.
- D-12: candidates whose fill-time structural R:R (next-bar open based) is
  below cfg.min_rr are discarded — no position, no label.
- D-21: check_history_gate refuses to run on insufficient stored history
  with an actionable message; never a silent empty report.
- Point-in-time discipline: per-bar as-of slices go through
  backtest.asof.visible_mask with the per-tier anchors (close-time stamps:
  swings.confirmed_at, pools.activated_at; bar-time stamps: events.resolved_at,
  zones.mitigated_at); the MTF payload row at bar_t is consumed AS-IS,
  never re-anchored (Phase 2 D-15).
- The resolver seam is interface-first: Callable[[Position, DataFrame,
  Config], dict] returning {outcome, exit_time, exit_price, exit_idx,
  r_gross, r_raw, r_net}. Plan 03-02 implements it (walk_barriers); the
  runner wires it in plan 03-03.
- MT5-free: pure pandas, no MetaTrader5 import, no I/O; input frames never
  mutated; empty input yields a schema-correct empty label frame.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd

from ai_trading.backtest.asof import STAMP_BAR, STAMP_CLOSE, close_time_of, visible_mask
from ai_trading.backtest.candidates import CandidateState, candidate_at_bar, compute_rr
from ai_trading.backtest.costs import effective_spread_points, entry_fill_price
from ai_trading.normalize import TIMEFRAME_MINUTES

_STR_DTYPE = pd.StringDtype()

#: The single label schema (BT-03 label store contract; Phase 4 consumes).
LABEL_COLUMNS = (
    "symbol",
    "timeframe",
    "direction",
    "entry_time",
    "entry_price",
    "sl_price",
    "tp_price",
    "rr",
    "pool_id",
    "event_id",
    "zone_id",
    "bias_h1",
    "bias_h4",
    "outcome",
    "exit_time",
    "exit_price",
    "exit_idx",
    "r_gross",
    "r_raw",
    "r_net",
)

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

_REQUIRED_BARS = ("symbol", "time_utc", "open", "high", "low", "close", "spread")


@dataclass(frozen=True)
class Position:
    """An open position from fill (bar entry_idx open) until its resolver
    returns the complete outcome."""

    symbol: str
    timeframe: str
    direction: str
    entry_open: float  # structural next-bar open (D-04)
    entry_spread_points: int  # effective spread at the fill bar (recorded or D-15 default)
    entry_price: float  # net filled price (spread + slippage applied)
    sl_price: float
    tp_price: float
    entry_idx: int
    entry_time: pd.Timestamp
    evidence: dict  # pool_id / event_id / zone_id / bias_h1 / bias_h4
    rr: float  # structural R:R at the fill open (D-12 gate input)


def _empty_labels_frame() -> pd.DataFrame:
    """Empty label frame with exactly LABEL_COLUMNS and pinned dtypes."""
    data = {}
    for col in LABEL_COLUMNS:
        if col in _STR_COLS:
            data[col] = pd.Series(dtype=_STR_DTYPE)
        elif col in _TS_COLS:
            data[col] = pd.Series(dtype="datetime64[us]")
        elif col in _INT_COLS:
            data[col] = pd.Series(dtype="int64")
        else:
            data[col] = pd.Series(dtype="float64")
    return pd.DataFrame(data)


def auto_warmup_bars(cfg) -> int:
    """Replay warmup in bars (D-07): cfg.warmup_bars when configured (> 0),
    else the auto constant 28 — ATR(14) NaN head (14) + 2-bar fractal
    right-side confirmation (2) + one completed zigzag leg margin (12).
    Candidates inside warmup are silently skipped, never an error."""
    return cfg.warmup_bars if cfg.warmup_bars > 0 else 28


def check_history_gate(
    days_stored: int, min_history_days: int, symbol: str, timeframe: str
) -> None:
    """D-21 history gate: refuse runs below the minimum stored depth with an
    actionable message (symbol, timeframe, both day counts, remedy) — never
    a silent empty report."""
    if days_stored < min_history_days:
        raise RuntimeError(
            f"insufficient stored history for {symbol} {timeframe}: {days_stored} days "
            f"stored < {min_history_days} required — extend collection (Phase 1 purge + "
            f"backfill) or pass --min-history-days override"
        )


def assert_offset_uniform(bars: pd.DataFrame) -> None:
    """Pitfall 10 carried obligation: the loaded range must not mix broker
    offsets (DST flip). Raises RuntimeError naming the symbol and the mixed
    offsets when bars['time'] - bars['time_utc'] is not one distinct value."""
    if bars.empty:
        return
    deltas = (bars["time"] - bars["time_utc"]).drop_duplicates().tolist()
    if len(deltas) > 1:
        symbol = str(bars["symbol"].iloc[0])
        mixed = sorted(str(d) for d in deltas)
        raise RuntimeError(
            f"assert_offset_uniform invariant violated: {symbol} bars mix broker offsets "
            f"{mixed} — DST/offset mixing must not silently reach labels"
        )


def _validate_bars(bars: pd.DataFrame) -> None:
    """Per-symbol input validators (never global): required columns, exactly
    one symbol, time_utc strictly increasing and unique."""
    missing = [c for c in _REQUIRED_BARS if c not in bars.columns]
    if missing:
        raise ValueError(
            f"replay_symbol invariant violated: bars is missing required columns {missing}"
        )
    if len(bars):
        symbols = bars["symbol"].astype(str).unique()
        if len(symbols) > 1:
            raise ValueError(
                "replay_symbol invariant violated: frame must contain exactly one symbol "
                f"(per-symbol replay), got {sorted(symbols)}"
            )
        t = bars["time_utc"]
        if not t.is_monotonic_increasing or not t.is_unique:
            raise ValueError(
                "replay_symbol invariant violated: time_utc must be strictly increasing "
                "and unique within the symbol"
            )


def _for_symbol(frame: pd.DataFrame | None, symbol: str) -> pd.DataFrame:
    """Isolate one symbol's tier rows (T-03-05: never validate or slice
    multi-symbol frames globally)."""
    if frame is None or frame.empty or "symbol" not in frame.columns:
        return frame if frame is not None else pd.DataFrame()
    return frame[frame["symbol"] == symbol]


def _infer_timeframe(bars: pd.DataFrame) -> str:
    diffs = bars["time_utc"].diff().dropna()
    minutes = int(diffs.mode().iloc[0].total_seconds() // 60)
    inverse = {m: tf for tf, m in TIMEFRAME_MINUTES.items()}
    if minutes not in inverse:
        raise ValueError(
            f"replay_symbol invariant violated: bar step {minutes}min is not a known "
            f"timeframe {sorted(TIMEFRAME_MINUTES)}"
        )
    return inverse[minutes]


def replay_symbol(
    m15_bars: pd.DataFrame,
    chain: dict[str, pd.DataFrame],
    cfg,
    resolver: Callable[[Position, pd.DataFrame, object], dict],
) -> pd.DataFrame:
    """Run the forward pass over one symbol's M15 bars and return the label
    frame with exactly LABEL_COLUMNS.

    ``chain`` is the run_chain output dict (only the M15 tiers + payload are
    consumed). ``resolver(position, bars, cfg)`` is invoked ONCE per fill
    and must return the complete outcome dict {outcome, exit_time,
    exit_price, exit_idx, r_gross, r_raw, r_net} — the interface-first seam
    implemented by plan 03-02 (walk_barriers).
    """
    _validate_bars(m15_bars)
    if len(m15_bars) < 2:
        return _empty_labels_frame()

    bars = m15_bars.reset_index(drop=True)  # positional indexing; input untouched
    symbol = str(bars["symbol"].iloc[0])
    timeframe = _infer_timeframe(bars)
    times = bars["time_utc"]

    swings_all = _for_symbol(chain.get("swings15"), symbol)
    pools_all = _for_symbol(chain.get("pools15"), symbol)
    events_all = _for_symbol(chain.get("events15"), symbol)
    zones_all = _for_symbol(chain.get("zones15"), symbol)
    payload_all = _for_symbol(chain.get("payload"), symbol)

    warmup = auto_warmup_bars(cfg)
    rows: list[dict] = []
    held_until = -1  # D-05: slot held through the resolver's exit_idx

    for i in range(len(bars)):
        if i < warmup:
            continue  # D-07: silent warmup skip
        if i <= held_until:
            continue  # D-05: slot held until past the position's exit bar

        bar_t = times.iloc[i]
        close_t = close_time_of(bar_t, timeframe)

        payload_rows = (
            payload_all[payload_all["time_utc"] == bar_t] if not payload_all.empty else payload_all
        )
        state = CandidateState(
            m15_bars=bars.iloc[: i + 1],
            events15=events_all[
                visible_mask(events_all, "resolved_at", STAMP_BAR, bar_t, close_t)
            ]
            if not events_all.empty
            else events_all,
            zones15=zones_all[
                visible_mask(zones_all, "mitigated_at", STAMP_BAR, bar_t, close_t)
            ]
            if not zones_all.empty
            else zones_all,
            pools15=pools_all[
                visible_mask(pools_all, "activated_at", STAMP_CLOSE, bar_t, close_t)
            ]
            if not pools_all.empty
            else pools_all,
            swings15=swings_all[
                visible_mask(swings_all, "confirmed_at", STAMP_CLOSE, bar_t, close_t)
            ]
            if not swings_all.empty
            else swings_all,
            payload_row=payload_rows.iloc[0] if len(payload_rows) else None,
        )

        cand = candidate_at_bar(state, cfg)
        if cand is None:
            continue

        entry_idx = i + 1
        if entry_idx >= len(bars):
            break  # D-04: no fill without a next bar

        fill_bar = bars.iloc[entry_idx]
        entry_open = float(fill_bar["open"])
        spread = effective_spread_points(cfg, symbol, fill_bar["spread"])
        entry_price = entry_fill_price(cand.direction, entry_open, spread, cfg, symbol)
        rr = compute_rr(cand.direction, entry_open, cand.sl_price, cand.tp_price)
        if rr < cfg.min_rr:
            continue  # D-12: discard below min R:R — no position, no label

        position = Position(
            symbol=symbol,
            timeframe=timeframe,
            direction=cand.direction,
            entry_open=entry_open,
            entry_spread_points=spread,
            entry_price=entry_price,
            sl_price=cand.sl_price,
            tp_price=cand.tp_price,
            entry_idx=entry_idx,
            entry_time=times.iloc[entry_idx],
            evidence={
                "pool_id": cand.pool_id,
                "event_id": cand.event_id,
                "zone_id": cand.zone_id,
                "bias_h1": cand.bias_h1,
                "bias_h4": cand.bias_h4,
            },
            rr=rr,
        )
        outcome = resolver(position, bars, cfg)  # invoked ONCE at fill time
        rows.append(
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "direction": cand.direction,
                "entry_time": position.entry_time,
                "entry_price": position.entry_price,
                "sl_price": cand.sl_price,
                "tp_price": cand.tp_price,
                "rr": rr,
                "pool_id": cand.pool_id,
                "event_id": cand.event_id,
                "zone_id": cand.zone_id,
                "bias_h1": cand.bias_h1,
                "bias_h4": cand.bias_h4,
                "outcome": outcome["outcome"],
                "exit_time": outcome["exit_time"],
                "exit_price": outcome["exit_price"],
                "exit_idx": outcome["exit_idx"],
                "r_gross": outcome["r_gross"],
                "r_raw": outcome["r_raw"],
                "r_net": outcome["r_net"],
            }
        )
        held_until = outcome["exit_idx"]

    if not rows:
        return _empty_labels_frame()
    labels = pd.DataFrame(rows, columns=LABEL_COLUMNS)
    for col in _STR_COLS:
        labels[col] = labels[col].astype(_STR_DTYPE)
    for col in _TS_COLS:
        labels[col] = labels[col].astype("datetime64[us]")
    for col in _INT_COLS:
        labels[col] = labels[col].astype("int64")
    for col in LABEL_COLUMNS:
        if col not in _STR_COLS and col not in _TS_COLS and col not in _INT_COLS:
            labels[col] = labels[col].astype("float64")
    return labels.reset_index(drop=True)
