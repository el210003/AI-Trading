"""Multi-timeframe point-in-time context join (SMC-06, ROADMAP SC4).

Pattern of record: RESEARCH.md Pattern 6 — ``merge_asof(direction="backward",
allow_exact_matches=False, by="symbol")`` over CONFIRMATION timestamps, with
the point-in-time discipline of ``collector.fetch_closed_bars``.

Hard rules (locked decisions):
- D-15 (the #1 lookahead trap): an M15 decision bar at time T sees only HTF
  zone state whose confirmation happened STRICTLY before T.
  ``allow_exact_matches=False`` — an HTF confirmation at exactly T is NOT
  visible. Never an HTF bar-open-time join, never a latest-row lookup
  (Pitfall 1).
- D-13: bias from the M15 close's position inside the latest LIVE HTF zone
  range: close above equilibrium -> bearish (premium), below -> bullish
  (discount), exactly at -> neutral (A9). No live HTF range -> bias NA with
  NaN range fields and empty zone IDs.
- D-14: lean payload per HTF (H1 AND H4) per M15 bar: bias, HTF range
  high/low/equilibrium, signed distance-to-equilibrium in M15 ATR(14) units
  (A1), and IDs of live HTF zones whose range contains the M15 close (A2,
  sorted by (created_at, zone_id)). No HTF pool/sweep payload in v1.
- Planner pin: if the latest strictly-before HTF zone is already invalidated
  as of T, payload fields are NA/NaN/empty until the next leg completes a new
  zone — no stale bias from a broken range. Liveness: a zone is live as of T
  when invalidated_at is NA or >= T (an invalidation stamped at exactly T is
  not yet visible).
- Pitfall 9: both merge_asof inputs explicitly sorted immediately before the
  join; ``by="symbol"`` isolates instruments (T-2-05).
- DST safety (Pitfall 8): joins key on stored time_utc values as-is — HTF and
  M15 frames shift together across broker-offset transitions; no grid
  re-flooring anywhere.
- Zero adapter-tier imports, zero file I/O; input frames never mutated.
"""

from __future__ import annotations

import pandas as pd

from ai_trading.detectors.atr import wilders_atr
from ai_trading.detectors.zones import ZONE_COLUMNS

PAYLOAD_COLUMNS = [
    "symbol",
    "time_utc",
    "bias_h1",
    "htf_range_high_h1",
    "htf_range_low_h1",
    "htf_equilibrium_h1",
    "htf_dist_to_eq_atr_h1",
    "htf_zone_ids_h1",
    "bias_h4",
    "htf_range_high_h4",
    "htf_range_low_h4",
    "htf_equilibrium_h4",
    "htf_dist_to_eq_atr_h4",
    "htf_zone_ids_h4",
]

_REQUIRED_M15 = ("symbol", "time_utc", "open", "high", "low", "close")
_REQUIRED_ZONES = tuple(ZONE_COLUMNS)

_STR_DTYPE = pd.StringDtype()


def _empty_payload_frame() -> pd.DataFrame:
    frame = pd.DataFrame({col: pd.Series(dtype=_STR_DTYPE) for col in PAYLOAD_COLUMNS})
    for col in ("time_utc",):
        frame[col] = pd.Series(dtype="datetime64[us]")
    for col in (
        "htf_range_high_h1",
        "htf_range_low_h1",
        "htf_equilibrium_h1",
        "htf_dist_to_eq_atr_h1",
        "htf_range_high_h4",
        "htf_range_low_h4",
        "htf_equilibrium_h4",
        "htf_dist_to_eq_atr_h4",
    ):
        frame[col] = pd.Series(dtype="float64")
    for col in ("htf_zone_ids_h1", "htf_zone_ids_h4"):
        frame[col] = pd.Series(dtype="object")
    return frame


def _validate_m15(m15: pd.DataFrame) -> None:
    missing = [c for c in _REQUIRED_M15 if c not in m15.columns]
    if missing:
        raise ValueError(
            f"htf_context invariant violated: m15 is missing required columns {missing}"
        )
    # Multi-symbol frames are time-monotonic and unique per symbol, not
    # globally — combined frames legitimately repeat timestamps across symbols.
    for _, sym_bars in m15.groupby("symbol", sort=False):
        t = sym_bars["time_utc"]
        if not t.is_monotonic_increasing or not t.is_unique:
            raise ValueError(
                "htf_context invariant violated: m15 time_utc must be strictly "
                "increasing and unique within each symbol"
            )
    for col in ("open", "high", "low", "close"):
        if not m15[col].notna().all():
            raise ValueError(
                f"htf_context invariant violated: m15 column '{col}' must be finite"
            )


def _validate_zones(zones: pd.DataFrame, label: str) -> None:
    missing = [c for c in _REQUIRED_ZONES if c not in zones.columns]
    if missing:
        raise ValueError(
            f"htf_context invariant violated: {label} zones frame is missing "
            f"required columns {missing}"
        )


def _is_live(invalidated_at, t) -> bool:
    """A zone is live as of T when its invalidation is NA or stamped at/after
    T (an invalidation at exactly T is not yet visible)."""
    return pd.isna(invalidated_at) or invalidated_at >= t


def _payload_for_tf(
    m15s: pd.DataFrame, atr: pd.Series, zones: pd.DataFrame, suffix: str
) -> pd.DataFrame:
    """Build one HTF timeframe's lean payload columns for every M15 bar."""
    n = len(m15s)
    bias = pd.Series(pd.NA, index=m15s.index, dtype=_STR_DTYPE)
    range_high = pd.Series(float("nan"), index=m15s.index)
    range_low = pd.Series(float("nan"), index=m15s.index)
    equilibrium = pd.Series(float("nan"), index=m15s.index)
    dist = pd.Series(float("nan"), index=m15s.index)
    zone_ids: list[list[str]] = [[] for _ in range(n)]

    if not zones.empty:
        timeline = zones[
            [
                "created_at",
                "zone_id",
                "range_high",
                "range_low",
                "equilibrium",
                "invalidated_at",
                "symbol",
            ]
        ].sort_values("created_at", kind="mergesort").copy()
        # Pitfall 9: normalize join-key dtypes on both sides (make_bars emits
        # datetime64[ns]/object symbols; zone frames pin [us]/StringDtype).
        timeline["symbol"] = timeline["symbol"].astype(_STR_DTYPE)
        timeline["created_at"] = timeline["created_at"].astype("datetime64[us]")
        left = m15s[["symbol", "time_utc", "close"]].copy()
        left["symbol"] = left["symbol"].astype(_STR_DTYPE)
        left["time_utc"] = left["time_utc"].astype("datetime64[us]")
        joined = pd.merge_asof(
            left,
            timeline,
            left_on="time_utc",
            right_on="created_at",
            by="symbol",
            direction="backward",
            allow_exact_matches=False,  # D-15: strictly before the decision bar
        )
        zones_by_symbol: dict[str, list] = {}
        for row in zones.itertuples(index=False):
            zones_by_symbol.setdefault(row.symbol, []).append(row)

        for i, row in joined.iterrows():
            t = row["time_utc"]
            if pd.isna(row["created_at"]):
                continue  # no HTF confirmation strictly before T yet
            if not _is_live(row["invalidated_at"], t):
                continue  # planner pin: no stale bias from a broken range
            close = row["close"]
            eq = row["equilibrium"]
            if close > eq:
                bias.iloc[i] = "bearish"  # premium (D-13)
            elif close < eq:
                bias.iloc[i] = "bullish"  # discount
            else:
                bias.iloc[i] = "neutral"  # exact equilibrium (A9)
            range_high.iloc[i] = row["range_high"]
            range_low.iloc[i] = row["range_low"]
            equilibrium.iloc[i] = eq
            atr_val = atr.iloc[i]
            if not pd.isna(atr_val) and atr_val != 0:
                dist.iloc[i] = (close - eq) / atr_val  # signed, A1
            # Containment: live zones as of T containing the close (A2).
            ids = [
                z.zone_id
                for z in zones_by_symbol.get(row["symbol"], [])
                if z.created_at < t
                and _is_live(z.invalidated_at, t)
                and z.range_low <= close <= z.range_high
            ]
            zone_ids[i] = sorted(
                ids,
                key=lambda zid: next(
                    (z.created_at, z.zone_id)
                    for z in zones_by_symbol[row["symbol"]]
                    if z.zone_id == zid
                ),
            )

    return pd.DataFrame(
        {
            f"bias_{suffix}": bias,
            f"htf_range_high_{suffix}": range_high,
            f"htf_range_low_{suffix}": range_low,
            f"htf_equilibrium_{suffix}": equilibrium,
            f"htf_dist_to_eq_atr_{suffix}": dist,
            f"htf_zone_ids_{suffix}": pd.Series(zone_ids, index=m15s.index, dtype="object"),
        }
    )


def htf_context(
    m15: pd.DataFrame, htf_zones_h1: pd.DataFrame, htf_zones_h4: pd.DataFrame
) -> pd.DataFrame:
    """Join H1+H4 zone state onto each M15 decision bar, point-in-time.

    Strictly-before confirmation visibility (D-15), bias from the close's
    position inside the latest live HTF range (D-13), lean per-HTF payload
    with ATR-scaled distance and live-zone containment IDs (D-14). Returns
    the pinned 14-column wide payload sorted by (symbol, time_utc).
    """
    _validate_m15(m15)
    _validate_zones(htf_zones_h1, "H1")
    _validate_zones(htf_zones_h4, "H4")
    if m15.empty:
        return _empty_payload_frame()

    m15s = m15.sort_values("time_utc", kind="mergesort").reset_index(drop=True)
    atr = wilders_atr(m15s).reset_index(drop=True)

    h1 = _payload_for_tf(m15s, atr, htf_zones_h1, "h1")
    h4 = _payload_for_tf(m15s, atr, htf_zones_h4, "h4")
    out = pd.concat(
        [m15s[["symbol", "time_utc"]].reset_index(drop=True), h1, h4], axis=1
    )

    for col in ("symbol", "bias_h1", "bias_h4"):
        if col in out.columns:
            out[col] = out[col].astype(_STR_DTYPE)
    for col in ("time_utc",):
        if col in out.columns:
            out[col] = out[col].astype("datetime64[us]")
    for col in (
        "htf_range_high_h1",
        "htf_range_low_h1",
        "htf_equilibrium_h1",
        "htf_dist_to_eq_atr_h1",
        "htf_range_high_h4",
        "htf_range_low_h4",
        "htf_equilibrium_h4",
        "htf_dist_to_eq_atr_h4",
    ):
        if col in out.columns:
            out[col] = out[col].astype("float64")
    return out[PAYLOAD_COLUMNS].sort_values(
        ["symbol", "time_utc"], kind="mergesort"
    ).reset_index(drop=True)
