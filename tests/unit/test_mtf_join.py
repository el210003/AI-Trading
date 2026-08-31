"""Unit tests (SMC-06 + ROADMAP SC4 + D-15): the confirmation-time as-of MTF
join — strictly-before visibility (the #1 lookahead trap, pinned explicitly),
bias mapping, lean payload completeness, live-zone containment, DST anchor
continuity, and point-in-time stability. No adapter-tier (MetaTrader5)
imports anywhere.

HTF zone fixtures run the REAL chain (detect_swings -> build_zigzag ->
derive_zones) over sculpted H1 frames so joins exercise production outputs,
not hand-built stand-ins."""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest
from conftest import make_bars

from ai_trading.detectors.atr import wilders_atr
from ai_trading.detectors.mtf import PAYLOAD_COLUMNS, htf_context
from ai_trading.detectors.swings import detect_swings
from ai_trading.detectors.zigzag import build_zigzag
from ai_trading.detectors.zones import derive_zones

SYMBOL = "EURUSD"
M15 = "M15"
H1 = "H1"
H4 = "H4"
START = datetime(2026, 8, 20, 0, 0)  # shared server-wall grid origin
BASE = 1.10000
TR = 0.01000  # constant-TR M15 base -> ATR(14) is exactly TR after warmup

# (bar_index, side, price) sculpt specs on a flat 1.10 H1 base.
TWO_LEG = [(5, "low", 1.08000), (10, "high", 1.12000)]
THREE_LEG = [(5, "low", 1.08000), (10, "high", 1.12000), (15, "low", 1.07000)]
# Derived geometry: Z1 = 1.08-1.12 (eq 1.10, created at H1 close 13h);
# Z2 = 1.07-1.12 (eq 1.095, created at H1 close 16h). All START-relative.


def _m15_base(count: int) -> pd.DataFrame:
    """Constant-TR M15 frame: open=low=BASE, close=high=BASE+TR."""
    df = make_bars(SYMBOL, M15, START, count, offset_hours=3)
    df["open"] = BASE
    df["low"] = BASE
    df["close"] = BASE + TR
    df["high"] = BASE + TR
    return df


def _set_close(df: pd.DataFrame, idx: int, close: float) -> pd.DataFrame:
    """Sculpt one bar's close with sanity-preserving wick widening."""
    out = df.copy()
    out.iloc[idx, out.columns.get_indexer(["close"])] = close
    out.iloc[idx, out.columns.get_indexer(["high"])] = max(BASE, close) + 0.005
    out.iloc[idx, out.columns.get_indexer(["low"])] = min(BASE, close) - 0.005
    return out


def _h1_zones(spec, invalidate_below: float | None = None) -> pd.DataFrame:
    """Zones through the real chain on a sculpted H1 frame. Optional
    committed-close invalidation: H1 bar 20 closes at ``invalidate_below``
    (below every range low) — wick intact, close beyond (D-11)."""
    from _detector_fixtures import swing_spec_bars

    h1 = swing_spec_bars(SYMBOL, H1, START, 40, spec)
    if invalidate_below is not None:
        idx = 20
        h1.iloc[idx, h1.columns.get_indexer(["open"])] = invalidate_below + 0.02
        h1.iloc[idx, h1.columns.get_indexer(["high"])] = invalidate_below + 0.025
        h1.iloc[idx, h1.columns.get_indexer(["low"])] = invalidate_below - 0.005
        h1.iloc[idx, h1.columns.get_indexer(["close"])] = invalidate_below
    swings = detect_swings(h1.copy(), H1)
    zigzag = build_zigzag(swings.copy())
    return derive_zones(zigzag.copy(), h1.copy())


def _bar_at(bars: pd.DataFrame, t) -> int:
    """Index of the M15 bar whose time_utc equals ``t`` (fixture alignment)."""
    times = bars["time_utc"].reset_index(drop=True)
    hits = times[times == t]
    assert len(hits) == 1, f"M15 grid must contain {t} exactly once"
    return int(hits.index[0])


def _first_bar_after(bars: pd.DataFrame, t) -> int:
    times = bars["time_utc"].reset_index(drop=True)
    later = times[times > t]
    assert len(later) > 0, f"M15 grid has no bar after {t}"
    return int(later.index[0])


def _m15_with_bias_bars(count: int = 300) -> pd.DataFrame:
    """M15 frame whose bars just after Z1's confirmation close above / below /
    exactly at the equilibrium (1.10)."""
    zones = _h1_zones(TWO_LEG)
    created_at = zones.iloc[0]["created_at"]
    bars = _m15_base(count)
    created_idx = _bar_at(bars, created_at) if bars["time_utc"].max() >= created_at else None
    if created_idx is not None:
        bars = _set_close(bars, created_idx + 1, 1.10500)  # premium -> bearish
        bars = _set_close(bars, created_idx + 2, 1.09500)  # discount -> bullish
        bars = _set_close(bars, created_idx + 3, 1.10000)  # exact eq -> neutral
    return bars


# ---------------------------------------------------------------------------
# Strictly-before visibility (D-15)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_htf_confirmation_at_exact_bar_time_excluded():
    """An HTF zone confirmed at exactly an M15 bar's time_utc is INVISIBLE to
    that bar and visible to the next one (allow_exact_matches=False lock)."""
    zones = _h1_zones(TWO_LEG)
    created_at = zones.iloc[0]["created_at"]
    bars = _m15_base(300)
    exact_idx = _bar_at(bars, created_at)
    payload = htf_context(bars, zones, zones.iloc[:0].copy())
    row_exact = payload.iloc[exact_idx]
    assert pd.isna(row_exact["bias_h1"])
    assert pd.isna(row_exact["htf_range_high_h1"])
    assert row_exact["htf_zone_ids_h1"] == []
    row_next = payload.iloc[exact_idx + 1]
    assert pd.notna(row_next["bias_h1"])
    assert row_next["htf_range_high_h1"] == pytest.approx(1.12)


@pytest.mark.unit
def test_joined_rows_strictly_before_invariant():
    """Every payload row's fields equal the LATEST zone whose created_at is
    STRICTLY before the bar's time_utc and which is live as of T — the
    point-in-time invariant re-derived over the full frame (Pitfall 9)."""
    zones = _h1_zones(THREE_LEG)
    bars = _m15_with_bias_bars()
    payload = htf_context(bars, zones, zones.iloc[:0].copy())
    zlist = list(zones.itertuples(index=False))
    for i, (_, r) in enumerate(payload.iterrows()):
        t = r["time_utc"]
        close = bars.iloc[i]["close"]
        candidates = [
            z
            for z in zlist
            if z.created_at < t
            and (pd.isna(z.invalidated_at) or z.invalidated_at >= t)
        ]
        if not candidates:
            assert pd.isna(r["bias_h1"])
            assert r["htf_zone_ids_h1"] == []
            continue
        latest = max(candidates, key=lambda z: z.created_at)
        assert r["htf_range_high_h1"] == latest.range_high
        assert r["htf_range_low_h1"] == latest.range_low
        assert r["htf_equilibrium_h1"] == latest.equilibrium
        if close > latest.equilibrium:
            assert r["bias_h1"] == "bearish"
        elif close < latest.equilibrium:
            assert r["bias_h1"] == "bullish"
        else:
            assert r["bias_h1"] == "neutral"


# ---------------------------------------------------------------------------
# Bias mapping (D-13, A9)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_bias_premium_discount_neutral_mapping():
    """M15 closes above / below / exactly at the HTF equilibrium map to
    bearish / bullish / neutral."""
    zones = _h1_zones(TWO_LEG)
    bars = _m15_with_bias_bars()
    created_at = zones.iloc[0]["created_at"]
    created_idx = _bar_at(bars, created_at)
    payload = htf_context(bars, zones, zones.iloc[:0].copy())
    assert payload.iloc[created_idx + 1]["bias_h1"] == "bearish"  # premium
    assert payload.iloc[created_idx + 2]["bias_h1"] == "bullish"  # discount
    assert payload.iloc[created_idx + 3]["bias_h1"] == "neutral"  # exact eq


@pytest.mark.unit
def test_payload_field_completeness_and_pre_confirmation_na():
    """All 14 pinned columns present; before the first HTF confirmation the
    fields are NA/NaN/empty; no pool/sweep fields anywhere."""
    zones = _h1_zones(TWO_LEG)
    bars = _m15_base(300)
    payload = htf_context(bars, zones, zones.iloc[:0].copy())
    assert list(payload.columns) == PAYLOAD_COLUMNS
    created_at = zones.iloc[0]["created_at"]
    pre = payload[payload["time_utc"] < created_at]
    assert len(pre) > 0
    assert pre["bias_h1"].isna().all()
    assert pre["htf_range_high_h1"].isna().all()
    assert pre["htf_dist_to_eq_atr_h1"].isna().all()
    assert all(ids == [] for ids in pre["htf_zone_ids_h1"])
    assert not any("pool" in c or "sweep" in c for c in payload.columns)


# ---------------------------------------------------------------------------
# Containment (D-14, A2)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_zone_ids_containment_live_only_sorted():
    """zone_ids lists only LIVE zones whose range contains the close, sorted
    by (created_at, zone_id); a close outside every range yields an empty
    list while bias stays set from the latest zone."""
    zones = _h1_zones(THREE_LEG)
    z1, z2 = zones.iloc[0], zones.iloc[1]
    bars = _m15_base(300)
    idx_after_z1 = _bar_at(bars, z1["created_at"]) + 1
    idx_after_z2 = _first_bar_after(bars, z2["created_at"])
    bars = _set_close(bars, idx_after_z1, 1.10000)  # inside both ranges
    bars = _set_close(bars, idx_after_z2, 1.10000)
    payload = htf_context(bars, zones, zones.iloc[:0].copy())
    # Only Z1 exists strictly before the first bar (Z2 confirms later).
    assert payload.iloc[idx_after_z1]["htf_zone_ids_h1"] == [z1["zone_id"]]
    # Both zones live and containing -> both listed, creation order.
    assert payload.iloc[idx_after_z2]["htf_zone_ids_h1"] == [z1["zone_id"], z2["zone_id"]]
    # A close outside every range: empty containment, bias still set.
    bars_out = _set_close(bars, idx_after_z2, 1.14000)
    payload_out = htf_context(bars_out, zones, zones.iloc[:0].copy())
    assert payload_out.iloc[idx_after_z2]["htf_zone_ids_h1"] == []
    assert payload_out.iloc[idx_after_z2]["bias_h1"] == "bearish"


@pytest.mark.unit
def test_invalidation_boundary_and_na_payload():
    """D-11 x D-15 boundary semantics: a zone is still visible AT its
    invalidation timestamp (invalidation at exactly T is not yet visible)
    and excluded strictly after; once the invalidated zone was the latest,
    payload goes NA/NaN/empty until the next leg's zone confirms."""
    zones = _h1_zones(TWO_LEG, invalidate_below=1.07000)
    assert len(zones) == 2  # the close-below sculpt also completes a down leg
    z1, z2 = zones.iloc[0], zones.iloc[1]
    assert pd.notna(z1["invalidated_at"])
    assert pd.isna(z2["invalidated_at"])
    bars = _m15_base(400)
    bars = _set_close(bars, _bar_at(bars, z1["created_at"]) + 1, 1.10000)
    idx_inv = _bar_at(bars, z1["invalidated_at"])
    bars = _set_close(bars, idx_inv, 1.10000)
    bars = _set_close(bars, idx_inv + 1, 1.10000)
    payload = htf_context(bars, zones, zones.iloc[:0].copy())
    # AT the invalidation timestamp: Z1 still live and joined.
    row_at = payload.iloc[idx_inv]
    assert pd.notna(row_at["bias_h1"])
    assert row_at["htf_range_high_h1"] == z1["range_high"]
    assert z1["zone_id"] in row_at["htf_zone_ids_h1"]
    # Strictly after: Z1 dead, Z2 not yet confirmed -> NA/NaN/empty (planner pin).
    row_gap = payload.iloc[idx_inv + 1]
    assert pd.isna(row_gap["bias_h1"])
    assert pd.isna(row_gap["htf_range_high_h1"])
    assert pd.isna(row_gap["htf_dist_to_eq_atr_h1"])
    assert row_gap["htf_zone_ids_h1"] == []
    # After Z2's confirmation: payload resumes from the live zone; Z1 stays excluded.
    idx_z2 = _first_bar_after(bars, z2["created_at"])
    row_z2 = payload.iloc[idx_z2]
    assert row_z2["bias_h1"] == "bearish"  # close 1.11 > Z2 eq (1.0925)
    assert row_z2["htf_range_high_h1"] == z2["range_high"]
    assert row_z2["htf_zone_ids_h1"] == [z2["zone_id"]]


# ---------------------------------------------------------------------------
# Distance (D-14, A1)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_distance_to_equilibrium_signed_atr_units():
    """dist = (close - equilibrium) / M15 ATR(14) at the decision bar, signed;
    zero exactly at equilibrium."""
    zones = _h1_zones(TWO_LEG)
    bars = _m15_with_bias_bars()
    created_at = zones.iloc[0]["created_at"]
    eq = zones.iloc[0]["equilibrium"]
    created_idx = _bar_at(bars, created_at)
    payload = htf_context(bars, zones, zones.iloc[:0].copy())
    atr = wilders_atr(bars).reset_index(drop=True)
    for off, expected_sign in ((1, 1.0), (2, -1.0), (3, 0.0)):
        i = created_idx + off
        close = bars.iloc[i]["close"]
        got = payload.iloc[i]["htf_dist_to_eq_atr_h1"]
        expected = (close - eq) / atr.iloc[i]
        assert np.sign(got) == expected_sign or got == 0.0
        assert got == pytest.approx(expected)


# ---------------------------------------------------------------------------
# DST anchor continuity (Pitfall 8, SC4)
# ---------------------------------------------------------------------------

def _dst_frames():
    """M15 + H4 frames around a broker-offset flip +3 -> +2 (server-wall
    arrays per the test_timezone_dst pattern; H4 on the 4h server lattice).
    The HTF zone confirms BEFORE the flip so the join must stay continuous
    across it."""
    flip_wall = START + timedelta(hours=40)
    h4_count, m15_count = 40, 500

    h4_wall = [START + timedelta(hours=4 * i) for i in range(h4_count)]
    h4_offsets = [3 if t < flip_wall else 2 for t in h4_wall]
    h4 = pd.DataFrame(
        {
            "symbol": [SYMBOL] * h4_count,
            "time": h4_wall,
            "time_utc": pd.Series(
                [t - timedelta(hours=o) for t, o in zip(h4_wall, h4_offsets, strict=True)],
                dtype="datetime64[us]",
            ),
            "open": BASE,
            "high": BASE + TR,
            "low": BASE,
            "close": BASE + TR,
            "tick_volume": list(range(1, h4_count + 1)),
            "spread": list(range(h4_count)),
            "real_volume": [0] * h4_count,
        }
    )
    # Zone legs sculpted BEFORE the flip: low@2 (1.08), high@5 (1.12).
    h4.iloc[2, h4.columns.get_indexer(["low"])] = 1.08000
    h4.iloc[5, h4.columns.get_indexer(["high"])] = 1.12000

    m15_wall = [START + timedelta(minutes=15 * i) for i in range(m15_count)]
    m15_offsets = [3 if t < flip_wall else 2 for t in m15_wall]
    m15 = pd.DataFrame(
        {
            "symbol": [SYMBOL] * m15_count,
            "time": m15_wall,
            "time_utc": pd.Series(
                [t - timedelta(hours=o) for t, o in zip(m15_wall, m15_offsets, strict=True)],
                dtype="datetime64[us]",
            ),
            "open": BASE,
            "high": BASE + TR,
            "low": BASE,
            "close": BASE + TR,
            "tick_volume": list(range(1, m15_count + 1)),
            "spread": list(range(m15_count)),
            "real_volume": [0] * m15_count,
        }
    )
    return m15, h4


@pytest.mark.unit
def test_dst_offset_flip_h4_anchor_continuity():
    """H1/H4 context does not jump at a broker-offset +3 -> +2 transition:
    every M15 bar strictly after the zone's confirmation — on BOTH sides of
    the flip — carries a non-NA bias and complete range fields, with no
    coverage gap. The H1 payload column mirrors the H4-anchored zones frame
    passed in; H4 zones are empty here."""
    m15, h4 = _dst_frames()
    swings = detect_swings(h4.copy(), H4)
    zigzag = build_zigzag(swings.copy())
    zones = derive_zones(zigzag.copy(), h4.copy())
    assert len(zones) == 1
    created_at = zones.iloc[0]["created_at"]
    payload = htf_context(m15, zones, zones.iloc[:0].copy())
    after = payload[payload["time_utc"] > created_at]
    assert len(after) > 100  # the flip region is well covered
    assert after["bias_h1"].notna().all(), "no bias gap across the DST flip"
    assert after["htf_range_high_h1"].notna().all()
    assert (after["htf_range_high_h1"] == 1.12).all()  # same zone both sides
    assert after["time_utc"].is_monotonic_increasing  # no hour jump backwards


# ---------------------------------------------------------------------------
# Point-in-time stability + contracts
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_appended_bars_and_zones_leave_earlier_rows_unchanged():
    """Appending later M15 bars or adding later-confirmed HTF zones does not
    alter earlier rows' payloads (60-bar prefix vs full frame + THREE_LEG)."""
    zones_short = _h1_zones(TWO_LEG)
    bars_short = _m15_with_bias_bars(60)
    payload_short = htf_context(bars_short, zones_short, zones_short.iloc[:0].copy())

    bars_long = _m15_with_bias_bars(300)
    zones_long = _h1_zones(THREE_LEG)  # adds a later-confirmed zone
    payload_long = htf_context(bars_long, zones_long, zones_long.iloc[:0].copy())

    n = len(payload_short)
    pd.testing.assert_frame_equal(
        payload_short.reset_index(drop=True),
        payload_long.iloc[:n].reset_index(drop=True),
        check_exact=True,
    )


@pytest.mark.unit
def test_empty_frame_contracts():
    """Empty M15 -> empty payload with the full schema; empty HTF zones ->
    rows preserved with NA/NaN/empty payload columns."""
    bars = _m15_base(50)
    zones = _h1_zones(TWO_LEG)
    empty_zones = zones.iloc[:0].copy()
    payload = htf_context(bars.iloc[:0].copy(), zones, empty_zones)
    assert len(payload) == 0 and list(payload.columns) == PAYLOAD_COLUMNS
    payload_b = htf_context(bars.copy(), empty_zones, empty_zones)
    assert len(payload_b) == len(bars)
    assert payload_b["bias_h1"].isna().all() and payload_b["bias_h4"].isna().all()
    assert payload_b["htf_range_high_h1"].isna().all()
    assert all(ids == [] for ids in payload_b["htf_zone_ids_h1"])


@pytest.mark.unit
def test_input_frames_not_mutated():
    """m15 and zone frames are bit-identical before/after htf_context."""
    bars = _m15_with_bias_bars(200)
    zones = _h1_zones(TWO_LEG)
    bars_before = bars.copy(deep=True)
    zones_before = zones.copy(deep=True)
    htf_context(bars, zones, zones.iloc[:0].copy())
    pd.testing.assert_frame_equal(bars_before, bars)
    pd.testing.assert_frame_equal(zones_before, zones)
