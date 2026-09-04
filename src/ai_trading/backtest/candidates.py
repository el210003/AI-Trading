"""Entry-candidate pure functions (D-01..D-04, D-08..D-13) — the single
definition of the entry rule, owned by Phase 3. Phase 6 setup assembly
imports THESE exact functions (D-03 / BT-01: whatever live analysis does,
the backtester replays — no parallel rule definitions).

Locked semantics implemented here:
- D-01: a candidate = sweep (SMC-03) + mitigated PD-zone tap on M15 only
  (D-06). Sweep-only and zone-only produce None.
- D-02: HTF bias agreement required (at least one of H1/H4 leans the trade
  direction; the other may be neutral/absent). Bias values are recorded on
  the candidate as-is regardless.
- D-04: no fill math here — entry_bar_idx is the next bar (S+1); the replay
  fills at that bar's open.
- D-08: SL structural raw, no buffer: beyond BOTH the swept pool level and
  the zone's far boundary.
- D-09: TP structural, nearest target strictly beyond the zone's far
  boundary from BOTH alternatives (live opposite pools, prior confirmed
  swings), no fixed R:R, no cap; fallback = the zone's far boundary.
  Liveness (D-09 is silent — planner convention, documented): opposite
  pools already resolved at or before the decision bar are EXCLUDED (a
  resolved pool provides no remaining liquidity); unresolved pools
  (resolved_at NaT or strictly after the decision bar) are selectable.
  Ties between pool and swing targets resolve to the pool.
- D-12: min-R:R filtering happens at FILL (replay) — the entry price is the
  next bar's open, so R:R is final only there.
- D-13: SL/TP are raw detector outputs used as-is.

Pure functions: no MetaTrader5 import, no I/O, input frames never mutated.
Visibility anchors mirror backtest.asof (close-time stamps vs bar-time
stamps) via the same visible_mask helper — the single choke point.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from ai_trading.backtest.asof import STAMP_BAR, STAMP_CLOSE, close_time_of, visible_mask

M15 = "M15"


@dataclass(frozen=True)
class Candidate:
    """One entry candidate assembled at the close of decision bar S; the
    fill happens at bar S+1's open (D-04) and is the replay's job."""

    symbol: str
    direction: str  # "long" | "short"
    sl_price: float
    tp_price: float
    entry_bar_idx: int  # index of the next bar (S+1)
    pool_id: str
    event_id: str
    zone_id: str
    bias_h1: Any  # str or pd.NA — recorded as-is (D-02)
    bias_h4: Any  # str or pd.NA — recorded as-is (D-02)
    timeframe: str = M15  # D-06: candidates are generated on M15 only


@dataclass(frozen=True)
class CandidateState:
    """The as-of state at the close of decision bar S (all slices already
    visibility-filtered by the caller; the rule re-applies its own anchors
    so Phase 6 can pass unfiltered frames and get identical results).

    ``m15_bars`` is the decision-bar context: the bars frame up to AND
    INCLUDING the decision bar (bar_t = last row's time_utc, decision close
    = last row's close, entry_bar_idx = len(m15_bars) = S+1).
    """

    m15_bars: pd.DataFrame
    events15: pd.DataFrame  # sweep events (event_type, pool_id, side, level, resolved_at)
    zones15: pd.DataFrame  # M15 zones (range_high/low, equilibrium, state, mitigated_at, ...)
    pools15: pd.DataFrame  # pools (side, level, activated_at, resolved_at) for SL/TP
    swings15: pd.DataFrame  # prior confirmed swings (price, confirmed_at) — D-09 TP source
    payload_row: Any  # pd.Series with bias_h1/bias_h4, or None — consumed as-is (D-15 P2)


def bias_agrees(bias_h1: Any, bias_h4: Any, direction: str) -> bool:
    """D-02: True iff at least one HTF bias leans the trade direction; the
    other may be neutral/NA and is never needed. NA-safe."""
    want = "bullish" if direction == "long" else "bearish"
    h1_ok = (not pd.isna(bias_h1)) and bias_h1 == want
    h4_ok = (not pd.isna(bias_h4)) and bias_h4 == want
    return bool(h1_ok or h4_ok)


def _nearest_target(
    pool_levels: list[float], swing_levels: list[float], direction: str
) -> float | None:
    """Nearest structural target from the pool/swing union (long: the lowest
    level beyond the zone; short: the highest); ties resolve to the pool
    target (planner pin)."""
    if direction == "long":
        best_pool = min(pool_levels) if pool_levels else None
        best_swing = min(swing_levels) if swing_levels else None
        if best_pool is not None and (best_swing is None or best_pool <= best_swing):
            return best_pool
        return best_swing
    best_pool = max(pool_levels) if pool_levels else None
    best_swing = max(swing_levels) if swing_levels else None
    if best_pool is not None and (best_swing is None or best_pool >= best_swing):
        return best_pool
    return best_swing


def _tp_for_direction(
    direction: str,
    zone: pd.Series,
    bar_t: pd.Timestamp,
    close_t: pd.Timestamp,
    pools15: pd.DataFrame,
    swings15: pd.DataFrame,
) -> float:
    """D-09 TP: nearest structural target strictly beyond the zone's far
    boundary from live opposite pools and prior confirmed swings; fallback
    = the zone's far boundary. Resolved pools are not selectable (module
    docstring liveness convention)."""
    pools = pools15 if pools15 is not None else pd.DataFrame()
    swings = swings15 if swings15 is not None else pd.DataFrame()
    if direction == "long":
        far = float(zone["range_high"])
        pool_levels: list[float] = []
        if not pools.empty:
            mask = (
                visible_mask(pools, "activated_at", STAMP_CLOSE, bar_t, close_t)
                & (pools["side"] == "high")
                & (pools["level"] > far)
                & (pools["resolved_at"].isna() | (pools["resolved_at"] > bar_t))
            )
            pool_levels = [float(v) for v in pools.loc[mask, "level"]]
        swing_levels: list[float] = []
        if not swings.empty:
            mask = (
                visible_mask(swings, "confirmed_at", STAMP_CLOSE, bar_t, close_t)
                & (swings["side"] == "high")
                & (swings["price"] > far)
            )
            swing_levels = [float(v) for v in swings.loc[mask, "price"]]
    else:
        far = float(zone["range_low"])
        pool_levels = []
        if not pools.empty:
            mask = (
                visible_mask(pools, "activated_at", STAMP_CLOSE, bar_t, close_t)
                & (pools["side"] == "low")
                & (pools["level"] < far)
                & (pools["resolved_at"].isna() | (pools["resolved_at"] > bar_t))
            )
            pool_levels = [float(v) for v in pools.loc[mask, "level"]]
        swing_levels = []
        if not swings.empty:
            mask = (
                visible_mask(swings, "confirmed_at", STAMP_CLOSE, bar_t, close_t)
                & (swings["side"] == "low")
                & (swings["price"] < far)
            )
            swing_levels = [float(v) for v in swings.loc[mask, "price"]]
    nearest = _nearest_target(pool_levels, swing_levels, direction)
    return nearest if nearest is not None else far


def candidate_at_bar(state: CandidateState, cfg) -> Candidate | None:
    """Assemble the entry candidate at the close of the decision bar (the
    last row of ``state.m15_bars``), or None when any D-01/D-02 gate fails.

    Steps: (1) latest visible sweep (bar-time resolved_at anchor); (2) tap =
    a zone mitigated ON this decision bar (mitigated_at == bar_t — each tap
    emits once); (3) direction = discount+low-pool long / premium+high-pool
    short (close exactly at equilibrium is no trade); (4) HTF bias agreement
    (D-02); (5) structural raw SL (D-08); (6) structural nearest TP with
    liveness (D-09); (7) entry_bar_idx = S+1 (D-04 — no fill math here).
    ``cfg`` is accepted for signature stability (Phase 6 imports this exact
    signature, D-03); the rule itself is config-free.
    """
    del cfg  # signature fidelity for Phase 6 (D-03); see docstring
    bars = state.m15_bars
    if bars is None or bars.empty:
        return None
    bar_t = bars["time_utc"].iloc[-1]
    decision_close = float(bars["close"].iloc[-1])
    close_t = close_time_of(bar_t, M15)

    # 1) Latest visible sweep (bar-time anchor; caller slices are already
    # visibility-filtered — re-applying the anchor keeps the rule pure).
    events = state.events15
    if events is None or events.empty:
        return None
    sweeps = events[
        visible_mask(events, "resolved_at", STAMP_BAR, bar_t, close_t)
        & (events["event_type"] == "sweep")
    ]
    if sweeps.empty:
        return None
    sweep = sweeps.sort_values(["resolved_at", "event_id"], kind="mergesort").iloc[-1]

    # 2) Tap trigger: a zone mitigated ON this decision bar (first row in
    # frame order — deterministic; frames are created_at-sorted).
    # Point-in-time state (D-15 as-of): the stored `state` column is the FINAL
    # lifecycle state from derive_zones (~99.9% `invalidated` on real data), so
    # testing it here would exclude zones that were legitimately mitigated on
    # this bar but invalidated at a LATER bar. Reconstruct the as-of tap: the
    # zone was mitigated exactly this bar AND not yet invalidated as of now
    # (invalidated_at is NaT, or strictly after bar_t). Preserves the D-01
    # same-bar tap semantics that the fixtures validate.
    zones = state.zones15
    if zones is None or zones.empty:
        return None
    taps = zones[
        (zones["mitigated_at"] == bar_t)
        & (zones["invalidated_at"].isna() | (zones["invalidated_at"] > bar_t))
    ]
    if taps.empty:
        return None
    zone = taps.iloc[0]

    # 3) Direction: right side only (D-01) — discount for longs, premium for
    # shorts; close exactly at equilibrium is no trade.
    side = str(sweep["side"])
    equilibrium = float(zone["equilibrium"])
    if side == "low" and decision_close < equilibrium:
        direction = "long"
    elif side == "high" and decision_close > equilibrium:
        direction = "short"
    else:
        return None

    # 4) HTF bias agreement (D-02); values recorded as-is.
    payload_row = state.payload_row
    if payload_row is not None:
        bias_h1 = payload_row["bias_h1"]
        bias_h4 = payload_row["bias_h4"]
    else:
        bias_h1 = pd.NA
        bias_h4 = pd.NA
    if not bias_agrees(bias_h1, bias_h4, direction):
        return None

    # 5) SL structural raw (D-08): beyond BOTH the swept pool level and the
    # zone's far boundary.
    pool_level = float(sweep["level"])
    if direction == "long":
        sl_price = min(pool_level, float(zone["range_low"]))
    else:
        sl_price = max(pool_level, float(zone["range_high"]))

    # 6) TP structural nearest (D-09).
    tp_price = _tp_for_direction(
        direction, zone, bar_t, close_t, state.pools15, state.swings15
    )

    return Candidate(
        symbol=str(sweep["symbol"]),
        direction=direction,
        sl_price=sl_price,
        tp_price=tp_price,
        entry_bar_idx=len(bars),  # S+1 (D-04)
        pool_id=str(sweep["pool_id"]),
        event_id=str(sweep["event_id"]),
        zone_id=str(zone["zone_id"]),
        bias_h1=bias_h1,
        bias_h4=bias_h4,
    )


def compute_rr(direction: str, entry: float, sl: float, tp: float) -> float:
    """Structural R:R at the given entry price. D-12 filtering happens at
    fill (replay) because the entry price is the next bar's open."""
    if direction == "long":
        risk = entry - sl
        if risk <= 0:
            return 0.0  # degenerate/zero-risk setup (entry at/below SL) — no valid trade
        return (tp - entry) / risk
    risk = sl - entry
    if risk <= 0:
        return 0.0  # degenerate/zero-risk setup (entry at/above SL)
    return (entry - tp) / risk
