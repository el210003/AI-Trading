"""Point-in-time feature builder from SMC detector state (AI-01).

Every feature for a labeled trade is assembled ONLY from state visible at the
close of the decision bar S (the bar whose close triggers the candidate/entry
rule of ``backtest.candidates``). The builder consumes the SAME ``CandidateState``
as-of slices that ``backtest.replay.replay_symbol`` used (through
``backtest.asof.visible_mask`` with the exact per-tier anchors), plus the D-14
MTF payload row consumed as-is — so Phase 6 live scoring shares one code path
(BT-01) and inherits the Phase 2/3 prefix-stability guarantees.

The one subtle leak the module docstring names: the label frame's fill-based
R:R column (``rr``) and the other post-decision-bar columns (``entry_price``,
``exit_*``, ``r_*``, ``outcome``) are FORBIDDEN inputs. The decision-time R:R
is recomputed at the decision close; ``sl_price``/``tp_price`` are frozen
detector outputs from pre-decision state, and the entry-time join key is
legitimate because the fill lands at the next bar's open (D-04), so
``entry_time`` equals the decision bar's close time except across session gaps.

NA policy: payload-as-is fields propagate NA/None as missing; ATR(14) warmup
NaN propagates; zone/event lookups that find no visible row yield missing
(never raise) — LightGBM handles missing natively.

Pure: zero MetaTrader5 imports, zero file I/O, input frames never mutated.
"""

from __future__ import annotations

import math

import pandas as pd

from ai_trading.backtest.asof import STAMP_BAR, STAMP_CLOSE, close_time_of, visible_mask
from ai_trading.backtest.candidates import CandidateState, compute_rr
from ai_trading.detectors.atr import wilders_atr

#: The three legal ``stamp_kind`` values (as-of anchor, or payload-as-is).
STAMP_PAYLOAD = "payload-as-is"

#: Ordered source of truth for the feature list version (cfg.ml_feature_list_version).
#: Each entry: name, dtype (categorical|float64), source_tier, source_columns, stamp_kind.
FEATURE_SPEC = (
    # --- decision-time identity / categorical -----------------------------
    {"name": "symbol", "dtype": "categorical", "source_tier": "label",
     "source_columns": ("symbol",), "stamp_kind": STAMP_BAR},
    {"name": "timeframe", "dtype": "categorical", "source_tier": "label",
     "source_columns": ("timeframe",), "stamp_kind": STAMP_BAR},
    {"name": "direction", "dtype": "categorical", "source_tier": "label",
     "source_columns": ("direction",), "stamp_kind": STAMP_BAR},
    {"name": "bias_h1", "dtype": "categorical", "source_tier": "payload",
     "source_columns": ("bias_h1",), "stamp_kind": STAMP_PAYLOAD},
    {"name": "bias_h4", "dtype": "categorical", "source_tier": "payload",
     "source_columns": ("bias_h4",), "stamp_kind": STAMP_PAYLOAD},
    # --- numeric / float64 ------------------------------------------------
    {"name": "rr_at_decision", "dtype": "float64", "source_tier": "label+cand",
     "source_columns": ("direction", "close", "sl_price", "tp_price"),
     "stamp_kind": STAMP_CLOSE},
    {"name": "sl_dist_atr", "dtype": "float64", "source_tier": "m15_bars+label",
     "source_columns": ("close", "sl_price", "atr14"), "stamp_kind": STAMP_CLOSE},
    {"name": "tp_dist_atr", "dtype": "float64", "source_tier": "m15_bars+label",
     "source_columns": ("close", "tp_price", "atr14"), "stamp_kind": STAMP_CLOSE},
    {"name": "atr14", "dtype": "float64", "source_tier": "m15_bars",
     "source_columns": ("high", "low", "close"), "stamp_kind": STAMP_CLOSE},
    {"name": "zone_position", "dtype": "float64", "source_tier": "zones15",
     "source_columns": ("range_high", "range_low", "close"), "stamp_kind": STAMP_BAR},
    {"name": "bars_since_sweep", "dtype": "float64", "source_tier": "events15",
     "source_columns": ("resolved_at", "bar_t"), "stamp_kind": STAMP_BAR},
    {"name": "bars_since_zone_created", "dtype": "float64", "source_tier": "zones15",
     "source_columns": ("created_at", "bar_t"), "stamp_kind": STAMP_CLOSE},
    {"name": "htf_bias_agreement", "dtype": "float64", "source_tier": "payload",
     "source_columns": ("bias_h1", "bias_h4", "direction"), "stamp_kind": STAMP_PAYLOAD},
    {"name": "htf_dist_to_eq_atr_h1", "dtype": "float64", "source_tier": "payload",
     "source_columns": ("htf_dist_to_eq_atr_h1",), "stamp_kind": STAMP_PAYLOAD},
    {"name": "htf_dist_to_eq_atr_h4", "dtype": "float64", "source_tier": "payload",
     "source_columns": ("htf_dist_to_eq_atr_h4",), "stamp_kind": STAMP_PAYLOAD},
    {"name": "spread_points", "dtype": "float64", "source_tier": "m15_bars",
     "source_columns": ("spread",), "stamp_kind": STAMP_BAR},
    {"name": "utc_hour_sin", "dtype": "float64", "source_tier": "m15_bars",
     "source_columns": ("time_utc",), "stamp_kind": STAMP_BAR},
    {"name": "utc_hour_cos", "dtype": "float64", "source_tier": "m15_bars",
     "source_columns": ("time_utc",), "stamp_kind": STAMP_BAR},
)

FEATURE_NAMES = tuple(entry["name"] for entry in FEATURE_SPEC)
_CATEGORICAL_NAMES = frozenset(
    entry["name"] for entry in FEATURE_SPEC if entry["dtype"] == "categorical"
)
_NUMERIC_NAMES = frozenset(
    entry["name"] for entry in FEATURE_SPEC if entry["dtype"] == "float64"
)

_REQUIRED_BARS = ("symbol", "time_utc", "open", "high", "low", "close", "spread")

_EXIT_COLS = ("exit_time", "exit_price", "exit_idx", "outcome")
_R_VARIANTS = ("r_gross", "r_raw", "r_net")

#: FORBIDDEN label-side post-decision columns (L3 static guard + the docstring
#: rule above). Never read as a feature source.
FORBIDDEN_LABEL_COLUMNS = (
    "entry_price",
    "rr",
    *_EXIT_COLS,
    *_R_VARIANTS,
)


def _validate_bars(bars: pd.DataFrame) -> None:
    """Per-symbol bars validation (mirrors replay._validate_bars): required
    columns, exactly one symbol, time_utc strictly increasing and unique."""
    missing = [c for c in _REQUIRED_BARS if c not in bars.columns]
    if missing:
        raise ValueError(
            f"build_feature_frame invariant violated: bars is missing required "
            f"columns {missing}"
        )
    if len(bars):
        symbols = bars["symbol"].astype(str).unique()
        if len(symbols) > 1:
            raise ValueError(
                "build_feature_frame invariant violated: bars must contain exactly "
                f"one symbol, got {sorted(symbols)}"
            )
        t = bars["time_utc"]
        if not t.is_monotonic_increasing or not t.is_unique:
            raise ValueError(
                "build_feature_frame invariant violated: bars time_utc must be "
                "strictly increasing and unique within the symbol"
            )


def _for_symbol(frame: pd.DataFrame | None, symbol: str) -> pd.DataFrame | None:
    if frame is None or "symbol" not in frame.columns:
        return frame
    return frame[frame["symbol"] == symbol]


def _bar_pos(times: pd.Series, ts: pd.Timestamp) -> int | None:
    """Positional index of the bar whose open time equals ``ts``, or None."""
    pos = times.searchsorted(pd.Timestamp(ts), side="left")
    if pos < len(times) and times.iloc[pos] == pd.Timestamp(ts):
        return int(pos)
    return None


def features_at_decision(state: CandidateState, label_row: pd.Series, cfg) -> dict:
    """Return the 18 FEATURE_SPEC features for the decision at the close of the
    last bar of ``state.m15_bars`` (the decision bar S).

    Pure function of the already-visibility-filtered ``CandidateState`` plus the
    label row's decision-time structural fields (direction, sl_price, tp_price,
    zone_id, event_id, symbol, timeframe). The decision close is the last row's
    close of ``state.m15_bars``. Never reads the label frame's post-decision
    columns (the L3 guard enforces this mechanically). ``cfg`` is accepted for
    signature stability (Phase 6 imports this exact signature); the rule is
    config-free.
    """
    del cfg  # signature fidelity; see docstring
    bars = state.m15_bars
    if bars is None or bars.empty:
        raise ValueError("features_at_decision invariant violated: empty m15_bars")

    bar_t = pd.Timestamp(bars["time_utc"].iloc[-1])
    decision_close = float(bars["close"].iloc[-1])
    decision_idx = len(bars) - 1
    direction = str(label_row["direction"])
    symbol = str(label_row["symbol"])
    timeframe = str(label_row["timeframe"])
    sl_price = float(label_row["sl_price"])
    tp_price = float(label_row["tp_price"])
    zone_id = label_row.get("zone_id")
    event_id = label_row.get("event_id")

    # ATR(14) over bars up to and including the decision bar (NaN warmup).
    atr_series = wilders_atr(bars)
    atr14 = float(atr_series.iloc[-1])

    # The subtle leak rule: recompute R:R at the decision close. sl/tp are
    # frozen detector outputs; using the label's fill-based ``rr`` is forbidden.
    rr_at_decision = compute_rr(direction, decision_close, sl_price, tp_price)

    if not math.isnan(atr14):
        sl_dist_atr = abs(decision_close - sl_price) / atr14
        tp_dist_atr = abs(decision_close - tp_price) / atr14
    else:
        sl_dist_atr = float("nan")
        tp_dist_atr = float("nan")

    # Payload row consumed as-is (D-15); missing when no row at the decision bar.
    payload_row = state.payload_row
    if payload_row is not None:
        bias_h1 = payload_row["bias_h1"]
        bias_h4 = payload_row["bias_h4"]
        htf_dist_h1 = float(payload_row["htf_dist_to_eq_atr_h1"])
        htf_dist_h4 = float(payload_row["htf_dist_to_eq_atr_h4"])
    else:
        bias_h1 = pd.NA
        bias_h4 = pd.NA
        htf_dist_h1 = float("nan")
        htf_dist_h4 = float("nan")

    # HTF bias agreement (D-02 semantics): count of H1/H4 leaning the trade.
    want = "bullish" if direction == "long" else "bearish"
    agreement = 0
    if not pd.isna(bias_h1) and bias_h1 == want:
        agreement += 1
    if not pd.isna(bias_h4) and bias_h4 == want:
        agreement += 1

    # Zone position within the tapped zone (visible zones15 slice).
    zone_position = float("nan")
    zone_row = None
    zones = state.zones15
    if zones is not None and not zones.empty and "zone_id" in zones.columns:
        matches = zones[zones["zone_id"] == zone_id]
        if len(matches):
            zone_row = matches.iloc[0]
            low = float(zone_row["range_low"])
            high = float(zone_row["range_high"])
            if high != low:
                zone_position = (decision_close - low) / (high - low)

    # Sweep recency: bars between the swept event's resolution and the decision.
    bars_since_sweep = float("nan")
    events = state.events15
    if events is not None and not events.empty and "event_id" in events.columns:
        matches = events[events["event_id"] == event_id]
        if len(matches):
            resolved_at = pd.Timestamp(matches.iloc[0]["resolved_at"])
            sweep_pos = _bar_pos(bars["time_utc"], resolved_at)
            if sweep_pos is not None:
                bars_since_sweep = float(decision_idx - sweep_pos)

    # Zone-creation recency: bars between the bar at/before created_at and the
    # decision (created_at is a close-time stamp).
    bars_since_zone_created = float("nan")
    if zone_row is not None:
        created_at = pd.Timestamp(zone_row["created_at"])
        pos = bars["time_utc"].searchsorted(created_at, side="right") - 1
        if pos >= 0:
            bars_since_zone_created = float(decision_idx - pos)

    spread_points = float(bars["spread"].iloc[-1])

    hour = int(bar_t.hour)
    utc_hour_sin = math.sin(2 * math.pi * hour / 24)
    utc_hour_cos = math.cos(2 * math.pi * hour / 24)

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "bias_h1": bias_h1,
        "bias_h4": bias_h4,
        "rr_at_decision": rr_at_decision,
        "sl_dist_atr": sl_dist_atr,
        "tp_dist_atr": tp_dist_atr,
        "atr14": atr14,
        "zone_position": zone_position,
        "bars_since_sweep": bars_since_sweep,
        "bars_since_zone_created": bars_since_zone_created,
        "htf_bias_agreement": agreement,
        "htf_dist_to_eq_atr_h1": htf_dist_h1,
        "htf_dist_to_eq_atr_h4": htf_dist_h4,
        "spread_points": spread_points,
        "utc_hour_sin": utc_hour_sin,
        "utc_hour_cos": utc_hour_cos,
    }


def build_feature_frame(
    labels: pd.DataFrame, chain: dict[str, pd.DataFrame], bars: pd.DataFrame
) -> pd.DataFrame:
    """Build the 20-column feature frame for ONE symbol's labels.

    For each label row the decision bar is the positional predecessor of the
    fill bar (``searchsorted`` on ``bars.time_utc`` for ``entry_time`` with
    ``side='left'``, minus one) — never a naive entry_time minus one timeframe,
    which lands on the wrong bar across session gaps. Each tier is sliced
    through ``visible_mask`` with the exact per-tier anchors ``replay_symbol``
    uses, then ``features_at_decision`` derives the row.

    Returns a frame whose deduplicated column set is exactly the 20 columns:
    the 18 FEATURE_SPEC feature columns (symbol/timeframe double as alignment
    identity columns) plus ``entry_time`` and ``decision_close_time``
    (``close_time_of`` of the decision bar's open time). Output row count and
    order match the input labels. Empty labels yield a schema-correct empty
    frame with pinned dtypes. Inputs never mutated.
    """
    _validate_bars(bars)
    if labels is None or labels.empty:
        return _empty_feature_frame()

    symbols = labels["symbol"].astype(str).unique()
    if len(symbols) > 1:
        raise ValueError(
            "build_feature_frame invariant violated: labels must contain exactly "
            f"one symbol, got {sorted(symbols)}"
        )
    symbol = str(symbols[0])

    events_all = _for_symbol(chain.get("events15"), symbol)
    zones_all = _for_symbol(chain.get("zones15"), symbol)
    pools_all = _for_symbol(chain.get("pools15"), symbol)
    swings_all = _for_symbol(chain.get("swings15"), symbol)
    payload_all = _for_symbol(chain.get("payload"), symbol)

    bars = bars.reset_index(drop=True)
    times = bars["time_utc"]

    rows: list[dict] = []
    for _, label_row in labels.iterrows():
        entry_time = pd.Timestamp(label_row["entry_time"])
        try:
            fill_pos = int(times.searchsorted(entry_time, side="left"))
        except TypeError as exc:
            raise ValueError(
                f"build_feature_frame invariant violated: invalid entry_time "
                f"{entry_time!r}"
            ) from exc
        if fill_pos == 0:
            raise ValueError(
                "build_feature_frame invariant violated: no decision bar for "
                f"entry_time {entry_time}"
            )
        decision_idx = fill_pos - 1
        bar_t = pd.Timestamp(times.iloc[decision_idx])
        close_t = close_time_of(bar_t, "M15")
        m15_slice = bars.iloc[: decision_idx + 1].reset_index(drop=True)

        payload_rows = (
            payload_all[payload_all["time_utc"] == bar_t]
            if payload_all is not None and not payload_all.empty
            else payload_all
        )
        state = CandidateState(
            m15_bars=m15_slice,
            events15=(
                events_all[visible_mask(events_all, "resolved_at", STAMP_BAR, bar_t, close_t)]
                if events_all is not None and not events_all.empty
                else events_all
            ),
            zones15=(
                zones_all[visible_mask(zones_all, "mitigated_at", STAMP_BAR, bar_t, close_t)]
                if zones_all is not None and not zones_all.empty
                else zones_all
            ),
            pools15=(
                pools_all[visible_mask(pools_all, "activated_at", STAMP_CLOSE, bar_t, close_t)]
                if pools_all is not None and not pools_all.empty
                else pools_all
            ),
            swings15=(
                swings_all[visible_mask(swings_all, "confirmed_at", STAMP_CLOSE, bar_t, close_t)]
                if swings_all is not None and not swings_all.empty
                else swings_all
            ),
            payload_row=payload_rows.iloc[0] if len(payload_rows) else None,
        )
        feats = features_at_decision(state, label_row, None)
        feats["entry_time"] = entry_time
        feats["decision_close_time"] = close_t
        rows.append(feats)

    frame = pd.DataFrame(rows)
    out_cols = list(FEATURE_NAMES) + ["entry_time", "decision_close_time"]
    frame = frame[out_cols]
    for name in _CATEGORICAL_NAMES:
        frame[name] = frame[name].astype("category")
    for name in _NUMERIC_NAMES:
        frame[name] = frame[name].astype("float64")
    frame["entry_time"] = frame["entry_time"].astype("datetime64[us]")
    frame["decision_close_time"] = frame["decision_close_time"].astype("datetime64[us]")
    return frame.reset_index(drop=True)


def _empty_feature_frame() -> pd.DataFrame:
    data: dict[str, pd.Series] = {}
    for entry in FEATURE_SPEC:
        if entry["dtype"] == "categorical":
            data[entry["name"]] = pd.Series(dtype="category")
        else:
            data[entry["name"]] = pd.Series(dtype="float64")
    data["entry_time"] = pd.Series(dtype="datetime64[us]")
    data["decision_close_time"] = pd.Series(dtype="datetime64[us]")
    out_cols = list(FEATURE_NAMES) + ["entry_time", "decision_close_time"]
    return pd.DataFrame(data)[out_cols]
