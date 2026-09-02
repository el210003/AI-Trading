"""End-to-end detector-chain integration tests (ROADMAP SC4 + SC5 + BT-01 —
Phase 3's backtester replays these exact functions bar-by-bar).

The full chain detect_swings -> build_zigzag -> detect_pools -> derive_zones
-> htf_context runs over synthetic multi-TF, multi-symbol frames and is
proven pure (no vendor imports, no input mutation), deterministic,
schema-locked, sorted, and lookahead-safe. No adapter-tier (MetaTrader5)
imports anywhere — enforced against the detector sources by file-content
assertion (test_no_vendor_imports_in_detector_sources).

World design: EURUSD is fully sculpted (H1 + H4 legs at 1.08/1.12; an M15
equal-high pool at 1.115 pierced and reclaimed at bars 30/31; bias bars at
1.105/1.095/1.100 just after the H1 confirmation), GBPUSD carries minimal
flat 1.32 bars proving per-symbol join isolation and empty-tier schemas."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest
from _detector_fixtures import flat_bars, sculpt_high, sculpt_low, swing_spec_bars
from conftest import make_bars

from ai_trading.detectors.mtf import PAYLOAD_COLUMNS, htf_context
from ai_trading.detectors.pools import (
    EVENT_COLUMNS,
    POOL_COLUMNS,
    detect_pools,
)
from ai_trading.detectors.swings import SWING_COLUMNS, detect_swings
from ai_trading.detectors.zigzag import ZIGZAG_COLUMNS, build_zigzag
from ai_trading.detectors.zones import ZONE_COLUMNS, derive_zones

SYM_A = "EURUSD"
SYM_B = "GBPUSD"
M15 = "M15"
H1 = "H1"
H4 = "H4"
START = datetime(2026, 8, 20, 0, 0)
BASE = 1.10000
TR = 0.01000
P = BASE + 1.5 * TR  # 1.115 — equal-high pool touch price
LEG_SPEC = [(5, "low", 1.08000), (10, "high", 1.12000)]  # zone 1.08-1.12, eq 1.10


def _sculpt_swing_high_tr(df: pd.DataFrame, idx: int, price: float) -> pd.DataFrame:
    """TR-preserving swing-high sculpt (test_sweeps pattern): high=price,
    open=low=close=price-TR."""
    out = df.copy()
    out.iloc[idx, out.columns.get_indexer(["open", "low", "close"])] = price - TR
    out.iloc[idx, out.columns.get_indexer(["high"])] = price
    return out


def _m15_base_a(count: int = 300) -> pd.DataFrame:
    """Plain constant-TR EURUSD M15 base (no sculpts) — every close is
    BASE+TR, uniformly above the 1.10 equilibrium."""
    df = make_bars(SYM_A, M15, START, count, offset_hours=3)
    df["open"] = BASE
    df["low"] = BASE
    df["close"] = BASE + TR
    df["high"] = BASE + TR
    return df


def _m15_bars_a(count: int = 300) -> pd.DataFrame:
    """EURUSD M15 decision bars: constant-TR base, equal-high pool at bars
    20/24 (level P), pierce pair 30/31 with immediate reclaim, bias bars just
    after the H1 zone confirmation."""
    df = make_bars(SYM_A, M15, START, count, offset_hours=3)
    df["open"] = BASE
    df["low"] = BASE
    df["close"] = BASE + TR
    df["high"] = BASE + TR
    df = _sculpt_swing_high_tr(df, 20, P)
    df = _sculpt_swing_high_tr(df, 24, P)
    for idx, close in ((30, P - 0.0005), (31, P + 0.0002)):
        df.iloc[idx, df.columns.get_indexer(["open"])] = P + 0.0004
        df.iloc[idx, df.columns.get_indexer(["high"])] = P + 0.0005
        df.iloc[idx, df.columns.get_indexer(["low"])] = close - 0.0001
        df.iloc[idx, df.columns.get_indexer(["close"])] = close
    # H1 zone confirms at START + 10h = M15 bar 52 (13h of grid at -3h offset).
    created_idx = 52
    for off, close in ((1, 1.10500), (2, 1.09500), (3, 1.10000)):
        i = created_idx + off
        df.iloc[i, df.columns.get_indexer(["close"])] = close
        df.iloc[i, df.columns.get_indexer(["high"])] = max(BASE, close) + 0.005
        df.iloc[i, df.columns.get_indexer(["low"])] = min(BASE, close) - 0.005
    return df


def build_world() -> dict[str, pd.DataFrame]:
    """Combined multi-symbol multi-TF world: EURUSD fully sculpted, GBPUSD
    flat 1.32 (no swings, no zones). Frames sorted by (symbol, time_utc)."""
    m15_a = _m15_bars_a()
    m15_b = flat_bars(SYM_B, M15, START, 300, price=1.32)
    h1_a = swing_spec_bars(SYM_A, H1, START, 40, LEG_SPEC)
    h1_b = flat_bars(SYM_B, H1, START, 40, price=1.32)
    h4_a = swing_spec_bars(SYM_A, H4, START, 40, LEG_SPEC)
    h4_b = flat_bars(SYM_B, H4, START, 40, price=1.32)

    def combine(a: pd.DataFrame, b: pd.DataFrame) -> pd.DataFrame:
        return (
            pd.concat([a, b], ignore_index=True)
            .sort_values(["symbol", "time_utc"], kind="mergesort")
            .reset_index(drop=True)
        )

    return {
        "m15": combine(m15_a, m15_b),
        "h1": combine(h1_a, h1_b),
        "h4": combine(h4_a, h4_b),
    }


def run_chain(
    m15: pd.DataFrame, h1: pd.DataFrame, h4: pd.DataFrame
) -> dict[str, pd.DataFrame]:
    """The production chain, passing the caller's frames straight through —
    non-mutation is proven by test_all_inputs_unmutated_through_chain."""
    swings15 = detect_swings(m15, M15)
    zigzag15 = build_zigzag(swings15)
    pools15, events15 = detect_pools(m15, swings15)
    swings_h1 = detect_swings(h1, H1)
    zigzag_h1 = build_zigzag(swings_h1)
    zones_h1 = derive_zones(zigzag_h1, h1)
    swings_h4 = detect_swings(h4, H4)
    zigzag_h4 = build_zigzag(swings_h4)
    zones_h4 = derive_zones(zigzag_h4, h4)
    payload = htf_context(m15, zones_h1, zones_h4)
    return {
        "swings15": swings15,
        "zigzag15": zigzag15,
        "pools15": pools15,
        "events15": events15,
        "swings_h1": swings_h1,
        "zigzag_h1": zigzag_h1,
        "zones_h1": zones_h1,
        "swings_h4": swings_h4,
        "zigzag_h4": zigzag_h4,
        "zones_h4": zones_h4,
        "payload": payload,
    }


# ---------------------------------------------------------------------------
# End-to-end composition (SC5)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_full_chain_end_to_end_over_multi_tf_frames():
    """swings -> zigzag -> pools -> zones -> MTF composes over the combined
    multi-TF world; every tier yields schema-correct non-empty artifacts and
    the payload joins both HTFs for the sculpted symbol."""
    world = build_world()
    out = run_chain(world["m15"], world["h1"], world["h4"])
    assert len(out["swings15"]) > 0
    assert len(out["zigzag15"]) > 0
    assert len(out["pools15"]) > 0
    assert len(out["events15"]) > 0
    assert len(out["zones_h1"]) == 1
    assert len(out["zones_h4"]) == 1
    assert list(out["payload"].columns) == PAYLOAD_COLUMNS
    assert len(out["payload"]) == len(world["m15"])
    # The sculpted sweep resolved as a sweep (not a breakout).
    assert out["events15"].iloc[0]["event_type"] == "sweep"
    # EURUSD rows after the H1 confirmation join the 1.08-1.12 zone.
    z1 = out["zones_h1"].iloc[0]
    after = out["payload"][
        (out["payload"]["symbol"] == SYM_A)
        & (out["payload"]["time_utc"] > z1["created_at"])
    ]
    assert len(after) > 0
    assert (after["htf_range_high_h1"] == z1["range_high"]).all()
    assert after["bias_h1"].notna().all()
    # The bias sculpt bars map premium/discount/exact-equilibrium; every
    # later base bar (close 1.11 > eq 1.10) is bearish.
    rows = out["payload"][
        (out["payload"]["symbol"] == SYM_A) & (out["payload"]["time_utc"] > z1["created_at"])
    ].reset_index(drop=True)
    assert rows.iloc[0]["bias_h1"] == "bearish"  # close 1.105
    assert rows.iloc[1]["bias_h1"] == "bullish"  # close 1.095
    assert rows.iloc[2]["bias_h1"] == "neutral"  # close 1.100
    assert (rows.iloc[3:]["bias_h1"] == "bearish").all()
    # Flat GBPUSD carries no HTF context at all.
    b_rows = out["payload"][out["payload"]["symbol"] == SYM_B]
    assert b_rows["bias_h1"].isna().all() and b_rows["bias_h4"].isna().all()


@pytest.mark.unit
def test_no_zone_before_leg_completion():
    """Every zone's created_at is exactly its completing leg's second point
    confirmation — no zone exists before leg completion (D-09)."""
    world = build_world()
    out = run_chain(world["m15"], world["h1"], world["h4"])
    for tf in ("h1", "h4"):
        zigzag = out[f"zigzag_{tf}"].sort_values("confirmed_at").reset_index(drop=True)
        zones = out[f"zones_{tf}"].sort_values("created_at").reset_index(drop=True)
        completing = zigzag.iloc[1:]["confirmed_at"].reset_index(drop=True)
        assert zones["created_at"].tolist() == completing.tolist()


@pytest.mark.unit
def test_no_payload_before_first_htf_confirmation():
    """No payload row before the first HTF confirmation of a timeframe carries
    non-NA bias for that timeframe."""
    world = build_world()
    out = run_chain(world["m15"], world["h1"], world["h4"])
    payload = out["payload"]
    first_h1 = out["zones_h1"]["created_at"].min()
    first_h4 = out["zones_h4"]["created_at"].min()
    pre_h1 = payload[payload["time_utc"] < first_h1]
    assert len(pre_h1) > 0
    assert pre_h1["bias_h1"].isna().all()
    pre_h4 = payload[payload["time_utc"] < first_h4]
    assert len(pre_h4) > 0
    assert pre_h4["bias_h4"].isna().all()
    # Sanity: context does arrive after the confirmations.
    assert payload[payload["time_utc"] > first_h1]["bias_h1"].notna().any()
    assert payload[payload["time_utc"] > first_h4]["bias_h4"].notna().any()


@pytest.mark.unit
def test_payload_strictly_before_invariant_full_chain():
    """Every payload row's per-HTF fields equal the LATEST live zone whose
    created_at is STRICTLY before the bar's time_utc — re-derived over the
    full multi-symbol chain output."""
    world = build_world()
    out = run_chain(world["m15"], world["h1"], world["h4"])
    close_map = {
        (r.symbol, r.time_utc): r.close for r in world["m15"].itertuples(index=False)
    }
    zones_by_tf = {
        "h1": list(out["zones_h1"].itertuples(index=False)),
        "h4": list(out["zones_h4"].itertuples(index=False)),
    }
    for _, r in out["payload"].iterrows():
        for tf in ("h1", "h4"):
            t = r["time_utc"]
            close = close_map[(r["symbol"], t)]
            cands = [
                z
                for z in zones_by_tf[tf]
                if z.symbol == r["symbol"]
                and z.created_at < t
                and (pd.isna(z.invalidated_at) or z.invalidated_at >= t)
            ]
            bias = r[f"bias_{tf}"]
            if not cands:
                assert pd.isna(bias)
                continue
            latest = max(cands, key=lambda z: z.created_at)
            assert r[f"htf_range_high_{tf}"] == latest.range_high
            assert r[f"htf_equilibrium_{tf}"] == latest.equilibrium
            if close > latest.equilibrium:
                assert bias == "bearish"
            elif close < latest.equilibrium:
                assert bias == "bullish"
            else:
                assert bias == "neutral"


# ---------------------------------------------------------------------------
# Determinism + purity (SC5)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_chain_deterministic_on_rerun():
    """Running the whole chain twice on identical inputs produces
    byte-identical outputs at every tier."""
    world = build_world()
    first = run_chain(world["m15"].copy(), world["h1"].copy(), world["h4"].copy())
    second = run_chain(world["m15"].copy(), world["h1"].copy(), world["h4"].copy())
    for key in first:
        pd.testing.assert_frame_equal(first[key], second[key], check_exact=True)


@pytest.mark.unit
def test_all_inputs_unmutated_through_chain():
    """Every input frame (M15/H1/H4 bars and the intermediate swings frames)
    is bit-identical before/after each detector call in the chain."""
    world = build_world()
    snapshots = {k: v.copy(deep=True) for k, v in world.items()}
    out = run_chain(world["m15"], world["h1"], world["h4"])
    for key, snap in snapshots.items():
        pd.testing.assert_frame_equal(snap, world[key], check_exact=True)
    # The swings frames fed to zigzag/pools/derive_zones were not mutated either.
    swings_snapshots = {
        "swings15": out["swings15"].copy(deep=True),
        "swings_h1": out["swings_h1"].copy(deep=True),
        "swings_h4": out["swings_h4"].copy(deep=True),
    }
    run_chain(world["m15"], world["h1"], world["h4"])
    for name, snap in swings_snapshots.items():
        pd.testing.assert_frame_equal(snap, out[name], check_exact=True)


# ---------------------------------------------------------------------------
# Schema + sortedness locks (SC5)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_output_schemas_pinned_including_empty_frames():
    """Each tier's output matches its pinned columns exactly — for populated
    frames AND for the empty frames a flat (no-swing) world produces."""
    pinned = {
        "swings15": SWING_COLUMNS,
        "zigzag15": ZIGZAG_COLUMNS,
        "pools15": POOL_COLUMNS,
        "events15": EVENT_COLUMNS,
        "zones_h1": ZONE_COLUMNS,
        "zones_h4": ZONE_COLUMNS,
        "payload": PAYLOAD_COLUMNS,
    }
    world = build_world()
    out = run_chain(world["m15"], world["h1"], world["h4"])
    for key, cols in pinned.items():
        assert list(out[key].columns) == cols, f"{key} schema drifted"

    flat_m15 = pd.concat(
        [
            flat_bars(SYM_A, M15, START, 60),
            flat_bars(SYM_B, M15, START, 60, price=1.32),
        ],
        ignore_index=True,
    ).sort_values(["symbol", "time_utc"], kind="mergesort").reset_index(drop=True)
    flat_h1 = pd.concat(
        [
            flat_bars(SYM_A, H1, START, 40),
            flat_bars(SYM_B, H1, START, 40, price=1.32),
        ],
        ignore_index=True,
    ).sort_values(["symbol", "time_utc"], kind="mergesort").reset_index(drop=True)
    flat_h4 = pd.concat(
        [
            flat_bars(SYM_A, H4, START, 40),
            flat_bars(SYM_B, H4, START, 40, price=1.32),
        ],
        ignore_index=True,
    ).sort_values(["symbol", "time_utc"], kind="mergesort").reset_index(drop=True)
    empty = run_chain(flat_m15, flat_h1, flat_h4)
    for key, cols in pinned.items():
        assert list(empty[key].columns) == cols, f"empty {key} schema drifted"
    assert len(empty["swings15"]) == 0
    assert len(empty["zigzag15"]) == 0
    assert len(empty["pools15"]) == 0
    assert len(empty["events15"]) == 0
    assert len(empty["zones_h1"]) == 0
    assert len(empty["payload"]) == len(flat_m15)
    assert empty["payload"]["bias_h1"].isna().all()


@pytest.mark.unit
def test_sortedness_invariants_on_all_outputs():
    """swings and zigzag are confirmed_at-monotonic within each symbol; zones
    are sorted by (symbol, created_at); the payload by (symbol, time_utc)."""
    world = build_world()
    out = run_chain(world["m15"], world["h1"], world["h4"])
    for key in ("swings15", "zigzag15", "swings_h1", "zigzag_h4"):
        for _, g in out[key].groupby("symbol", sort=False):
            assert g["confirmed_at"].is_monotonic_increasing, f"{key} unsorted"
    for tf in ("h1", "h4"):
        zones = out[f"zones_{tf}"]
        expected = zones.sort_values(
            ["symbol", "created_at"], kind="mergesort"
        ).reset_index(drop=True)
        pd.testing.assert_frame_equal(zones.reset_index(drop=True), expected, check_exact=True)
    payload = out["payload"]
    expected = payload.sort_values(["symbol", "time_utc"], kind="mergesort").reset_index(drop=True)
    pd.testing.assert_frame_equal(payload.reset_index(drop=True), expected, check_exact=True)


# ---------------------------------------------------------------------------
# Purity by source (SC5)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_no_vendor_imports_in_detector_sources():
    """No module under src/ai_trading/detectors/ or src/ai_trading/backtest/
    contains an adapter-tier vendor-package import statement (file-content
    assertion; prose docstring mentions are allowed, imports are not)."""
    src = Path(__file__).resolve().parents[2] / "src" / "ai_trading"
    sources = sorted((src / "detectors").glob("*.py"))
    sources.extend(sorted((src / "backtest").glob("*.py")))
    assert len(sources) >= 6
    for path in sources:
        text = path.read_text(encoding="utf-8")
        assert "import MetaTrader5" not in text, f"vendor import in {path.name}"
        assert "from MetaTrader5" not in text, f"vendor import in {path.name}"
        if path.parent.name == "detectors":
            assert "floor_to_timeframe" not in text, f"grid re-flooring in {path.name}"


# ---------------------------------------------------------------------------
# Cross-symbol isolation (T-2-05)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_mtf_join_isolated_per_symbol():
    """Symbol A's payload never incorporates symbol B's HTF zones: both
    symbols carry their own H1 zones at disjoint price levels, and every row
    joins only its own symbol's zone."""
    h1_a = swing_spec_bars(SYM_A, H1, START, 40, LEG_SPEC)  # zone 1.08-1.12
    h1_b = flat_bars(SYM_B, H1, START, 40, price=1.32)
    h1_b = sculpt_low(h1_b, 5, 1.30000)
    h1_b = sculpt_high(h1_b, 10, 1.34000)  # zone 1.30-1.34, eq 1.32
    h1 = (
        pd.concat([h1_a, h1_b], ignore_index=True)
        .sort_values(["symbol", "time_utc"], kind="mergesort")
        .reset_index(drop=True)
    )
    m15 = (
        pd.concat(
            [_m15_base_a(), flat_bars(SYM_B, M15, START, 300, price=1.32)],
            ignore_index=True,
        )
        .sort_values(["symbol", "time_utc"], kind="mergesort")
        .reset_index(drop=True)
    )
    swings = detect_swings(h1.copy(), H1)
    zones = derive_zones(build_zigzag(swings.copy()), h1.copy())
    assert len(zones) == 2
    payload = htf_context(m15, zones, zones.iloc[:0].copy())

    a = payload[(payload["symbol"] == SYM_A) & payload["bias_h1"].notna()]
    b = payload[(payload["symbol"] == SYM_B) & payload["bias_h1"].notna()]
    assert len(a) > 0 and len(b) > 0
    # A joins only A's zone geometry; B only B's.
    assert (a["htf_range_high_h1"] == 1.12).all()
    assert (a["bias_h1"] == "bearish").all()  # close 1.11 > eq 1.10
    assert all("GBPUSD" not in i for ids in a["htf_zone_ids_h1"] for i in ids)
    assert (b["htf_range_high_h1"] == 1.34).all()
    assert (b["bias_h1"] == "neutral").all()  # close 1.32 == eq 1.32
    assert all("EURUSD" not in i for ids in b["htf_zone_ids_h1"] for i in ids)
    # IDs embed the symbol — containment lists never cross.
    assert all(i.startswith("EURUSD-") for ids in a["htf_zone_ids_h1"] for i in ids)
    assert all(i.startswith("GBPUSD-") for ids in b["htf_zone_ids_h1"] for i in ids)
