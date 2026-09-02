"""Triple-barrier outcome walk (BT-03) — the pure labeling core that turns a
filled position into a truthful WIN/LOSS/TIMEOUT label. This module IS the
resolver seam declared by backtest.replay: ``replay_symbol`` invokes it once
per fill and appends the returned dict straight into the label row.

LOCKED CONVENTIONS (pinned by named tests; never "optimize" them away):

- D-10 SL-FIRST TIE RULE, ALL BARS INCLUDING THE ENTRY BAR: with only OHLC,
  the intrabar path is unknowable — when SL and TP are both touched inside
  one bar there is no way to know which was hit first. The locked
  conservative convention is SL-first on EVERY bar. There is deliberately NO
  close-direction, open-proximity, or TP-first branch in this module — a tie
  heuristic that flatters win rates is the exact failure mode this walk
  exists to prevent (threat T-03-01; test_tie_sl_first_including_entry_bar
  fails if any such heuristic sneaks in).
- D-11 GAP HANDLING: a bar that OPENS beyond a barrier fills at that bar's
  OPEN price (never at the level): long — open <= SL fills LOSS at the open,
  open >= TP fills WIN at the open; short mirrors. The gap check runs before
  any high/low check on every bar, entry bar included. Gapped fills never
  ignore gaps.
- D-17 TIME BARRIER: the window is bars [E, E + time_barrier_bars) —
  INCLUSIVE of the entry bar E, exactly ``time_barrier_bars`` bars (96 M15
  bars = 24h). With neither barrier hit, the outcome is TIMEOUT and the exit
  fills at the FINAL window bar's close (bar E + time_barrier_bars - 1).
  End-of-data lens: when the frame ends inside the window, the last
  available bar is the timeout bar.
- D-18 OUTCOME CLASSES: exactly WIN (TP hit) / LOSS (SL hit) / TIMEOUT — no
  sub-flags.

D-16 R VARIANTS, CONVENTION (a): all three R variants normalize by the SAME
gross/structural risk distance |entry_open - sl_price| — the structural
next-bar open vs the structural SL price, both cost-free detector-level
values. The denominator is NEVER a cost-adjusted net risk distance.

- r_gross: structural exit only — the barrier level (tp/sl), the bar open
  for gap fills, or the final close for TIMEOUT.
- r_raw: spread-only fills (costs.entry_fill_price / exit_fill_price with
  apply_slippage=False) over the structural exit.
- r_net: replay's net entry fill (position.entry_price, spread + slippage
  already charged) against the slippage-charged exit fill.

Consequences (pinned by literal tests): a clean SL hit yields
r_raw = -1 - spread_px/risk and r_net = -1 - (spread_px + 2*slip_px)/risk —
both strictly below -1.0 when costs > 0 — and r_net <= r_raw with equality
only at zero slippage. Per trade r_net - r_raw = -2*slip_px/risk (2x
slippage in PRICE units divided by the structural risk; the spread is
charged identically in raw and net and cancels from the delta).

Pure functions: zero I/O, zero MetaTrader5 import, input frames never
mutated.
"""

from __future__ import annotations

import pandas as pd

from ai_trading.backtest.costs import (
    effective_spread_points,
    entry_fill_price,
    exit_fill_price,
)

OUTCOME_WIN = "WIN"
OUTCOME_LOSS = "LOSS"
OUTCOME_TIMEOUT = "TIMEOUT"

_REQUIRED_BARS = ("time_utc", "open", "high", "low", "close", "spread")


def _invariant(message: str) -> ValueError:
    return ValueError(f"walk_barriers invariant violated: {message}")


def walk_barriers(position, bars: pd.DataFrame, cfg) -> dict:
    """Evaluate the triple-barrier window for one filled position.

    ``position`` carries the replay Position contract (entry_open,
    entry_spread_points, entry_price, sl_price, tp_price, entry_idx,
    direction, symbol); ``bars`` is that symbol's detector-timeframe bar
    frame; ``cfg`` supplies ``time_barrier_bars`` (default 96) and the cost
    knobs. Returns exactly {outcome, exit_price, exit_idx, exit_time,
    r_gross, r_raw, r_net} — the resolver contract of backtest.replay.
    """
    for field in ("entry_open", "sl_price", "tp_price", "entry_idx"):
        if getattr(position, field, None) is None:
            raise _invariant(f"position.{field} must not be None")
    direction = position.direction
    if direction not in ("long", "short"):
        raise _invariant(f"direction {direction!r} must be 'long' or 'short'")
    missing = [col for col in _REQUIRED_BARS if col not in bars.columns]
    if missing:
        raise _invariant(f"bars is missing required columns {missing}")

    entry_idx = int(position.entry_idx)
    entry_open = float(position.entry_open)
    sl_price = float(position.sl_price)
    tp_price = float(position.tp_price)
    if bars.empty or entry_idx < 0 or entry_idx >= len(bars):
        raise _invariant(f"entry_idx {entry_idx} out of range for {len(bars)} bars")

    # Convention (a): the ONE structural risk distance every R variant shares.
    risk = entry_open - sl_price if direction == "long" else sl_price - entry_open
    if risk == 0.0:
        raise _invariant("zero risk distance")
    if risk < 0.0:
        raise _invariant(
            f"sl_price {sl_price} on the wrong side of entry_open {entry_open} "
            f"for {direction}"
        )

    time_barrier_bars = int(getattr(cfg, "time_barrier_bars", 96))
    if time_barrier_bars <= 0:
        raise _invariant(f"time_barrier_bars must be positive, got {time_barrier_bars}")

    window_end = min(entry_idx + time_barrier_bars, len(bars))
    outcome: str | None = None
    exit_price = 0.0
    exit_idx = entry_idx
    for idx in range(entry_idx, window_end):
        bar = bars.iloc[idx]
        bar_open = float(bar["open"])
        # D-11: gap check on the OPEN before any high/low check, entry bar included.
        if direction == "long":
            if bar_open <= sl_price:
                outcome, exit_price, exit_idx = OUTCOME_LOSS, bar_open, idx
                break
            if bar_open >= tp_price:
                outcome, exit_price, exit_idx = OUTCOME_WIN, bar_open, idx
                break
            if float(bar["low"]) <= sl_price:  # D-10: SL-first on ALL bars
                outcome, exit_price, exit_idx = OUTCOME_LOSS, sl_price, idx
                break
            if float(bar["high"]) >= tp_price:
                outcome, exit_price, exit_idx = OUTCOME_WIN, tp_price, idx
                break
        else:
            if bar_open >= sl_price:
                outcome, exit_price, exit_idx = OUTCOME_LOSS, bar_open, idx
                break
            if bar_open <= tp_price:
                outcome, exit_price, exit_idx = OUTCOME_WIN, bar_open, idx
                break
            if float(bar["high"]) >= sl_price:
                outcome, exit_price, exit_idx = OUTCOME_LOSS, sl_price, idx
                break
            if float(bar["low"]) <= tp_price:
                outcome, exit_price, exit_idx = OUTCOME_WIN, tp_price, idx
                break

    if outcome is None:  # D-17: neither barrier hit inside the window
        exit_idx = window_end - 1
        exit_price = float(bars.iloc[exit_idx]["close"])
        outcome = OUTCOME_TIMEOUT

    exit_time = bars.iloc[exit_idx]["time_utc"]
    exit_bar_spread = effective_spread_points(
        cfg, position.symbol, bars.iloc[exit_idx]["spread"]
    )

    if direction == "long":
        r_gross = (exit_price - entry_open) / risk
    else:
        r_gross = (entry_open - exit_price) / risk

    # r_raw: spread-only fills over the structural exit (no slippage either side).
    entry_raw = entry_fill_price(
        direction, entry_open, position.entry_spread_points, cfg, position.symbol,
        apply_slippage=False,
    )
    exit_raw = exit_fill_price(
        direction, exit_price, exit_bar_spread, cfg, position.symbol, apply_slippage=False
    )
    if direction == "long":
        r_raw = (exit_raw - entry_raw) / risk
    else:
        r_raw = (entry_raw - exit_raw) / risk

    # r_net: replay's net entry fill against the slippage-charged exit fill.
    entry_net = float(position.entry_price)
    exit_net = exit_fill_price(
        direction, exit_price, exit_bar_spread, cfg, position.symbol, apply_slippage=True
    )
    if direction == "long":
        r_net = (exit_net - entry_net) / risk
    else:
        r_net = (entry_net - exit_net) / risk

    return {
        "outcome": outcome,
        "exit_price": float(exit_price),
        "exit_idx": int(exit_idx),
        "exit_time": exit_time,
        "r_gross": float(r_gross),
        "r_raw": float(r_raw),
        "r_net": float(r_net),
    }
