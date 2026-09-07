# Phase 3: Backtesting & Labeling - Pattern Map

**Mapped:** 2026-09-01
**Files analyzed:** 24 (13 source/config + 11 test)
**Analogs found:** 24 / 24 (every file has an in-repo analog; quality varies — see Match Quality)

> **Read-first note:** Phase 3 is the FIRST code that *consumes* Phase 2 detector output as a service. All analogs below are real, in-repo source files. Copy-from sources are marked **[COPY]** (planner cites the excerpt as-is); **ADAPT** means the analog shapes the structure but the new logic differs (rule body comes from 03-RESEARCH.md Code Examples, lines 437-515). No greenfield gaps like Phase 1: worst case is a role-match, and every role match has an established pattern-of-record in `pools.py` / `zones.py` / `history_report.py` / `bar_store.py`.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/ai_trading/backtest/__init__.py` | package marker | n/a | `src/ai_trading/detectors/__init__.py` | exact |
| `src/ai_trading/backtest/asof.py` | utility (point-in-time visibility) | transform | `src/ai_trading/detectors/mtf.py` (`_is_live`, `_payload_for_tf` as-of loop) | role-match |
| `src/ai_trading/backtest/chain.py` | domain (chain runner) | transform/batch | `tests/unit/test_detector_integration.py::run_chain` (L118-145) | role-match |
| `src/ai_trading/backtest/candidates.py` | domain (pure entry rules) | event-driven | `src/ai_trading/detectors/pools.py` (`_detect_for_symbol` event-emission style) | role-match |
| `src/ai_trading/backtest/costs.py` | utility (pure arithmetic) | transform | `src/ai_trading/detectors/atr.py` (validate-then-compute pure fn) | role-match |
| `src/ai_trading/backtest/barriers.py` | domain (pure bar walk) | event-driven | `src/ai_trading/detectors/zones.py` (`_zones_for_symbol` per-bar walk L116-177) | role-match |
| `src/ai_trading/backtest/replay.py` | service/domain (state machine) | event-driven | `src/ai_trading/detectors/pools.py` (`_detect_for_symbol` L174-284) | role-match |
| `src/ai_trading/backtest/stats.py` | utility (pure pandas stat fns) | batch/transform | `src/ai_trading/history_report.py::compute_gaps/classify_gap` (pure fn + edge guards) | role-match |
| `src/ai_trading/backtest/walkforward.py` | utility (window derivation) | batch/transform | `src/ai_trading/history_report.py::compute_gaps` (grid/iterator over timestamps) | role-match |
| `src/ai_trading/backtest/reports.py` | storage (artifact writers) | file-I/O | `src/ai_trading/stores/bar_store.py::merge_and_write` (atomic write) | exact (write path) |
| `src/ai_trading/backtest/runner.py` | service + CLI | batch | `src/ai_trading/history_report.py::main` (L406-467) | exact |
| `src/ai_trading/config.py` (MODIFY) | config (frozen dataclass + validation) | transform | itself — extend `_REQUIRED_KEYS`/`_validate` in place | exact |
| `config.toml` (MODIFY) | config (runtime knobs) | n/a | itself — append keys in existing comment style | exact |
| `tests/unit/_backtest_fixtures.py` | test fixture helper | transform/factory | `tests/unit/_detector_fixtures.py` (L17-65: `flat_bars`, `sculpt_*`) | exact |
| `tests/unit/test_asof.py` | test (unit) | transform | `tests/unit/test_mtf_join.py` (as-of visibility tests) + `_detector_fixtures.prefix_close_time` | role-match |
| `tests/unit/test_candidates.py` | test (unit) | event-driven | `tests/unit/test_sweeps.py` / `test_zones.py` (sculpted sequences, hand-derivable math) | role-match |
| `tests/unit/test_costs.py` | test (unit) | transform | `tests/unit/test_normalize_and_config.py` (pure-math unit style) | role-match |
| `tests/unit/test_barriers.py` | test (unit) | event-driven | `tests/unit/test_lifecycle.py` (state-machine per-bar assertions) + `test_sweeps.py` | role-match |
| `tests/unit/test_replay.py` | test (unit) | event-driven | `tests/unit/test_pools.py` (loop state + one-at-a-time suppression tests) | role-match |
| `tests/unit/test_replay_repaint.py` | test (unit, anti-lookahead) | event-driven | `tests/unit/test_repaint.py` (L83-105 T1 prefix equality) + `assert_point_in_time_prefix_equality` | exact |
| `tests/unit/test_stats.py` | test (unit) | batch | `tests/unit/test_history_report.py` (report-dict assertion style) | role-match |
| `tests/unit/test_walkforward.py` | test (unit) | batch | `tests/unit/test_history_report.py` + `_detector_fixtures` loop style | role-match |
| `tests/unit/test_reports.py` | test (unit) | file-I/O | `tests/unit/test_idempotent_store.py` (atomic write, no `.tmp` residue) | exact |
| `tests/unit/test_backtest_config.py` | test (unit) | transform | `tests/unit/test_normalize_and_config.py` (L48-52 `_write_config`, L55-77 `_base_values`, parametrized rejection matrix) | exact |

**Provenance:** RESEARCH.md "Recommended Project Structure" (L203-236) defines the source layout; RESEARCH.md "Phase Requirements → Test Map" (L603-612) names the 9 test modules; RESEARCH.md "Wave 0 Gaps" (L619-624) names `_backtest_fixtures.py` (a NEW local helper, NOT a conftest mutation), the `backtest/__init__.py` marker, and the `config.py` extension.

## Pattern Assignments

### `src/ai_trading/backtest/__init__.py` (package marker)

**Analog:** `src/ai_trading/detectors/__init__.py` **[COPY]** (L1-9; 9 lines total)

Copy the bare-marker docstring style verbatim — package contract statement, no imports, no exports:
```python
"""Pure SMC detector transforms: no adapter-tier vendor-package imports, no
file I/O, no state. ... Import submodules directly — this file stays a
bare marker for the whole of Phase 2.
"""
```
Re-write for Phase 3: "Pure backtest transforms (asof, chain, candidates, costs, barriers, replay, stats, walkforward, reports, runner): MT5-free, imports submodules directly." Zero imports, zero code. Not `__all__`, not re-export.

---

### `src/ai_trading/backtest/asof.py` (utility, point-in-time visibility)

**Analog:** `src/ai_trading/detectors/mtf.py` **[ADAPT]** — the `_is_live` helper (L115-118) and the as-of row loop in `_payload_for_tf` (L165-200) are the closest existing point-in-time discipline; 03-RESEARCH.md Pattern 1 (L238-268) gives the heterogeneous-stamp contract.

**Copy these excerpts:**

Signature/behavior to mirror — `_is_live` (mtf.py L115-118):
```python
def _is_live(invalidated_at, t) -> bool:
    """A zone is live as of T when its invalidation is NA or stamped at/after
    T (an invalidation at exactly T is not yet visible)."""
    return pd.isna(invalidated_at) or invalidated_at >= t
```

As-of filtering shape (mtf.py L165-170 — per-row visibility gate):
```python
for i, row in joined.iterrows():
    t = row["time_utc"]
    if pd.isna(row["created_at"]):
        continue  # no HTF confirmation strictly before T yet
    if not _is_live(row["invalidated_at"], t):
        continue  # planner pin: no stale bias from a broken range
```

**Core signature to establish** (from RESEARCH Pattern 1, L262-268 — the only piece not in-repo):
```python
def visible_mask(df: pd.DataFrame, col: str, stamp_kind: str,
                 bar_t: pd.Timestamp, close_t: pd.Timestamp) -> pd.Series:
    """`stamp_kind`: 'close' (confirmed_at/created_at/activated_at) or
    'bar' (resolved_at/pierced_at/mitigated_at/invalidated_at)."""
    anchor = close_t if stamp_kind == "close" else bar_t
    return df[col].notna() & (df[col] <= anchor)  # NaT stamps excluded
```

**Must not forget:** the heterogeneous stamp table from RESEARCH.md L246-253 — close-time stamps (`swings.confirmed_at`, `zigzag.confirmed_at`, `zones.created_at`, `pools.activated_at`) use `close_t = t_S + TF`; bar-time stamps (`pools.pierced_at`/`resolved_at`, `zones.mitigated_at`/`invalidated_at`) use `t_S`; MTF payload rows are consumed as-is, never re-anchored. One helper, two anchors.

---

### `src/ai_trading/backtest/chain.py` (domain, single-pass chain runner)

**Analog:** `tests/unit/test_detector_integration.py::run_chain` (L118-145) **[ADAPT]** — this is the *exact* production chain composition already written in test form; promote the same call order into `src/`.

**Composition to copy** (test_detector_integration.py L118-145):
```python
def run_chain(m15: pd.DataFrame, h1: pd.DataFrame, h4: pd.DataFrame) -> dict[str, pd.DataFrame]:
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
    return {"swings15": swings15, ...}
```
`chain.py` wraps this same order (plus HTF warmup lead-in loading) and returns the same dict-of-frames. Import style to copy: direct submodule imports (pools.py L47-48 convention): `from ai_trading.detectors.pools import detect_pools`, `from ai_trading.detectors.zones import derive_zones`, `from ai_trading.detectors.mtf import htf_context`.

**BT-01 guard:** the chain MUST call the same exported functions — never re-implement. Extend `test_no_vendor_imports_in_detector_sources` (test_detector_integration.py L380-390) to also scan `src/ai_trading/backtest/*.py` (`"import MetaTrader5" not in text`, `"from MetaTrader5" not in text`).

---

### `src/ai_trading/backtest/candidates.py` (domain, pure entry rules — D-01…D-04, D-08…D-13)

**Analog:** `src/ai_trading/detectors/pools.py::_detect_for_symbol` (L174-284) **[ADAPT]** — same "pure function over frames returning list-of-dict records" shape. No exact in-repo analog exists for the rule itself; the rule body comes from 03-RESEARCH.md Pattern 2/3 + CONTEXT D-01…D-13 (called from Phase 6 later, so the signature must accept the full as-of state — RESEARCH Open Question 4, L562-565).

**Structure to copy** (pools.py L196-244 — record creation, ID generation, loop-local state):
```python
all_pools: list[dict] = []  # every candidate ever opened, creation order
...
target["pool_id"] = f"{swing.symbol}-{tf}-P{activation_counter:04d}"
...
cand = {
    "open": True, "state": "forming", "pool_id": None,
    "symbol": swing.symbol, "timeframe": tf, "side": side,
    "level": float(swing.price), "touch_count": 1,
    "first_touch_at": close_time, "activated_at": pd.NaT, "resolved_at": pd.NaT,
}
```

**Validation style to copy** (pools.py L114-148 — `_validate_bars`/`_validate_swings`): missing-column check raises `ValueError(f"<fn> invariant violated: ...")`; per-symbol monotonic-unique check on `time_utc`; never validate multi-symbol frames globally.

**Output record shape to establish** (per label spec, pinned like `POOL_COLUMNS` pools.py L50-61): candidate = `(direction, sl_price, tp_price, rr, evidence ids, entry_bar_idx)` or `None`; label record carries `entry_time`, `exit_time`, `outcome`, `R_raw`, `R_net` (RESEARCH Pattern 7, L334 — Phase 4 purge contract).

---

### `src/ai_trading/backtest/costs.py` (utility, pure arithmetic)

**Analog:** `src/ai_trading/detectors/atr.py` **[ADAPT]** (L23-50) — the project's smallest pure-fn module: docstring with hard rules, `_REQUIRED_COLUMNS` check, `ValueError` with `"<fn> invariant violated"` message, validate-then-compute, zero imports beyond pandas.

**Structure to copy** (atr.py L23-41):
```python
def wilders_atr(bars: pd.DataFrame, period: int = 14) -> pd.Series:
    missing = [c for c in _REQUIRED_COLUMNS if c not in bars.columns]
    if missing:
        raise ValueError(f"wilders_atr invariant violated: bars is missing required columns {missing}")
    for col in _REQUIRED_COLUMNS:
        if not bars[col].notna().all() or not pd.api.types.is_numeric_dtype(bars[col]):
            raise ValueError(f"wilders_atr invariant violated: column '{col}' must be finite numeric")
```

**Rule body** (from RESEARCH Pattern 4, L297-312 + Code Example 2, L469-483): pip_size per symbol (EURUSD/GBPUSD 0.0001, USDJPY 0.01), point = pip/10, `spread_points > 0 else cfg.default_spread_points` fallback (D-15), `slip = cfg.slippage_pips * pip_size` (D-14), direction-aware fills: long entry = `bid_open + spread_px + slip`, short entry = `bid_open - slip`, long exit = `level - slip`, short exit = `level + spread_px + slip`. Keep units explicit in docstrings (Pitfall 2 — spread is POINTS, never pips/price).

---

### `src/ai_trading/backtest/barriers.py` (domain, triple-barrier walk — D-10/D-11/D-17/D-18)

**Analog:** `src/ai_trading/detectors/zones.py::_zones_for_symbol` (L159-176) **[ADAPT]** — the per-bar sequential walk with first-event stamping and monotone state. This is precisely the loop shape the barrier walk needs.

**Per-bar walk to copy** (zones.py L159-175):
```python
times = sym_bars["time_utc"].reset_index(drop=True)
for i in range(len(sym_bars)):
    bar = sym_bars.iloc[i]
    t = times.iloc[i]
    for zone in zones:
        if zone["state"] == "invalidated" or t < zone["created_at"]:
            continue
        if zone["state"] == "unmitigated" and (
            bar["low"] < zone["range_high"] and bar["high"] > zone["range_low"]
        ):
            zone["state"] = "mitigated"
            zone["mitigated_at"] = t
```

**Rule body** (from RESEARCH Code Example 1, L440-467 — structure written to mirror pools.py/zones.py style): iterate `range(entry_idx, min(entry_idx + time_barrier_bars, len(bars)))`; per bar (1) gap check on `bar["open"]` → exit at open (D-11), (2) `low <= sl` → LOSS before `high >= tp` → WIN (D-10 SL-first, entry bar included), (3) after E+95 → TIMEOUT at final bar close (D-17). Window is *inclusive*, 96 bars = `bars[E : E+96]` — pin with test (Pitfall 6).

---

### `src/ai_trading/backtest/replay.py` (service/domain, forward-pass state machine)

**Analog:** `src/ai_trading/detectors/pools.py::_detect_for_symbol` (L174-284) **[COPY into ADAPT]** — the established event-sparse sequential-loop precedent RESEARCH Pattern 2 names explicitly ("`pools.py`/`zones.py` precedent, deliberately not vectorized").

**Loop skeleton to copy** (pools.py L201-244 — due-events map, loop-local state, warmup skip):
```python
for i in range(len(sym_bars)):
    close_time = times.iloc[i] + tf_delta
    bar = sym_bars.iloc[i]
    # -- 1) cluster-confirm due at this bar's close (Pitfall 6: first) --
    for swing in due.get(close_time, []):
        atr_val = atr.iloc[i]
        if pd.isna(atr_val):
            continue  # Pitfall 7: warmup — no pool activity yet
```
Replay-specific discipline: (a) decision at close of bar S, entry at bar `S+1` open (D-04); (b) `if position_open: skip generation` (D-05 one-at-a-time, loop-local state — never a store); (c) `i < warmup_bars → skip silently` (D-07 warmup, `continue` not `raise`); (d) counter-IDs and dict records exactly as pools.py.

---

### `src/ai_trading/backtest/stats.py` (utility, pure canonical stats — BT-04)

**Analog:** `src/ai_trading/history_report.py::compute_gaps/classify_gap` (L144-202) **[ADAPT]** — the precedent for "pure pandas function with explicit edge guards / never-crash behavior".

**Edge-guard style to copy** (history_report.py L161-201): empty-input short-circuit returning a clean default; never raise on input edge (report, don't crash):
```python
def classify_gap(gap_start, gap_end) -> str:
    try:
        ...
    except Exception:  # reporting-only heuristic: never crash on odd input
        return "review"
```

**Stats formulas** (from RESEARCH Code Example 3, L485-500 — R-units; computed raw AND net per D-16): win_rate `wins/(wins+losses)` with TIMEOUT excluded from denominator (A4), `profit_factor` zero-loss → `inf` guard, `expectancy`/`avg_r` = mean signed R INCLUDING timeouts, `max_dd` from R-curve `(eq/eq.cummax()-1).min()`, empty-series → `nan`/`0.0` guards.

---

### `src/ai_trading/backtest/walkforward.py` (utility, window derivation — D-19/D-20/D-22)

**Analog:** `src/ai_trading/history_report.py::compute_gaps` (L144-178) **[ADAPT]** — the existing pattern for deriving contiguous timestamp windows over a sorted grid, which is exactly window derivation.

**Window iteration to copy** (compute_gaps L164-178 — grid + merge-adjacent loop; mirrors the generated output structure but walkforward yields windows instead):
```python
step = TIMEFRAME_MINUTES[timeframe]
times = pd.DatetimeIndex(df["time_utc"])
grid = pd.date_range(start=times.min(), end=times.max(), freq=f"{step}min")
...
i = 0
while i < len(missing):
    j = i
    while j + 1 < len(missing) and missing[j + 1] - missing[j] == step_delta:
        j += 1
    gaps.append((missing[i], missing[j] + step_delta))
    i = j + 1
```

**Rule body** (from RESEARCH Code Example 4, L502-515): strictly chronological, expanding train (`train = [b for b in boundaries if b < test_start]`), rolling fixed-length test, zero overlap (`idx += test_len`), `train_len/test_len` accept days OR bar counts (D-20 small-window support required); labels assigned by entry time, exactly one window each; yield `(train, test_window)`.

---

### `src/ai_trading/backtest/reports.py` (storage, artifact writers)

**Analog:** `src/ai_trading/stores/bar_store.py::merge_and_write` (L50-75) **[COPY]** — the atomic-write pattern of record; plus `history_report.py::print_report` (L344-398) for text rendering.

**Atomic write to copy verbatim** (bar_store.py L67-75):
```python
path.parent.mkdir(parents=True, exist_ok=True)
tmp = path.with_name(path.name + ".tmp")
try:
    df.to_parquet(tmp, engine="pyarrow", compression="zstd", index=False)
    os.replace(tmp, path)  # atomic on the same NTFS volume (Windows included)
except Exception:
    if tmp.exists():
        tmp.unlink(missing_ok=True)
    raise
```

**Rules:** labels Parquet keyed by `(symbol, entry_time)` (determinism, idempotent overwrite — RESEARCH Pitfall 11, L432-435); run metadata (run id, config hash, range) in a SEPARATE JSON manifest so label bytes stay identical across re-runs; never bake timestamps/run-ids into label files. JSON canon + per-window Parquet under `data/labels/` and `data/reports/`.

---

### `src/ai_trading/backtest/runner.py` (service + CLI)

**Analog:** `src/ai_trading/history_report.py::main` (L406-467) **[COPY]** — the CLI pattern of record (argparse + exit codes).

**CLI skeleton to copy** (history_report.py L414-467):
```python
parser = argparse.ArgumentParser(prog="ai_trading.backtest", description="...")
parser.add_argument("--config", default="config.toml", help="path to config.toml (default: %(default)s)")
...
args = parser.parse_args(argv)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
try:
    cfg = load_config(Path(args.config))
except ValueError as exc:
    log.error("invalid configuration: %s", exc)
    return 2
try:
    ...  # runtime work
except RuntimeError as exc:   # or a phase-specific error type
    log.error("%s", exc)
    return 1
return 0
```
**Exit code contract:** 2 = config error, 1 = runtime error (history gate refusal D-21, range validation, mixed-offset detection), 0 = success. Runner flow per RESEARCH diagram (L148-199): gate check → load M15 + HTF lead-in → run_chain → as-of slice per M15 close → replay loop → stats → reports. Gate refusal message must be actionable (Pitfall 3, L384-387: "only X days stored for SYMBOL TF; extend collection ... or pass --min-history-days override") — never a silent 0-trade report.

---

### `src/ai_trading/config.py` (MODIFY — add backtest knobs)

**Analog:** itself **[COPY]** — extend in place; do NOT create a second config module. Pattern: frozen dataclass + `_REQUIRED_KEYS` tuple + `_validate` with `ValueError(f"{name} must be ...")`.

**Extension points** (config.py L29-45, 48-64, 109-160):
```python
_REQUIRED_KEYS = (
    "symbols", ..., "initial_backfill_days",
    # ADD: slippage_pips, default_spread_points, pip_size (per-symbol dict),
    #      min_rr, time_barrier_bars, wf_train_days, wf_test_days,
    #      min_history_days, warmup_bars (or -1 = auto)
)

@dataclass(frozen=True)
class Config:
    ...
    slippage_pips: float
    default_spread_points: int
    pip_size: dict[str, float]     # or default_pips with pip_size derivation
    min_rr: float
    time_barrier_bars: int
    wf_train_days: int
    wf_test_days: int
    min_history_days: int
```
Validation style to copy (config.py L145-151):
```python
for name, value in (("min_maxbars", cfg.min_maxbars), ("lookback_bars", cfg.lookback_bars)):
    if not _is_int(value) or value <= 0:
        raise ValueError(f"{name} must be a positive integer, got {value!r}")
```
Plus `_is_int` (L109-111: True-int, not bool), positive-float checks for `slippage_pips`/`min_rr` (slippage >= 0, min_rr > 0), `default_spread_points >= 0`, `time_barrier_bars` positive int, `wf_train_days/wf_test_days` positive ints, and a config-consistency rule (e.g. `wf_test_days <= wf_train_days` allowed). Add per-symbol `pip_size`/`default_spread_points` overrides validated per symbol in `cfg.symbols`.

---

### `config.toml` (MODIFY)

**Analog:** itself **[COPY]** — append a `[backtest]`-style commented section following the existing layout (config.toml L1-28: comment header, `symbols = [...]`, snake_case keys, `#` comments documenting defaults):
```toml
# Backtest / labeling knobs (Phase 3)
slippage_pips = 0.5
default_spread_points = 20
min_rr = 1.0
time_barrier_bars = 96
wf_train_days = 180
wf_test_days = 30
min_history_days = 30
```
Rules: no secrets (V14); if per-symbol maps are used, they are keyed by symbol and validated against `symbols` in `_validate`.

---

### `tests/unit/_backtest_fixtures.py` (test fixture helper)

**Analog:** `tests/unit/_detector_fixtures.py` **[COPY]** — new local helper built over `conftest.make_bars`; DO NOT mutate `tests/conftest.py` (Phase 1 contract, RESEARCH L621).

**Structure to copy** (_detector_fixtures.py L17-31, L89-93):
```python
def flat_bars(symbol, timeframe, start, count, price=1.10000, offset_hours=3) -> pd.DataFrame:
    from conftest import make_bars
    df = make_bars(symbol, timeframe, start, count, offset_hours=offset_hours)
    for col in ("open", "high", "low", "close"):
        df[col] = price
    return df
```
**Additions needed (RESEARCH L621):** spread-rich bar sculptors — `make_bars` emits `spread=list(range(count))` (zeros at bar 0) and label tests need controllable spread values (e.g. `set_spreads(df, values)` returning a new frame). Also a `prefix_close_time` copy (L89-93) if imported, and a candidate-rule fixture builder (sweep+zone+bias sculpted world, mirroring `test_detector_integration.build_world` L94-115).

---

### Test modules (9 new)

**Analog group:** Phase 1/2 test conventions = `pytest.mark.unit` on every test, `from conftest import make_bars` / `from _detector_fixtures import ...` direct imports, frames built with `tmp_path` + `make_cfg` fixture.

**Per-module sources:**
- `test_asof.py` → `tests/unit/test_mtf_join.py` (as-of visibility per-tier tests) + `_detector_fixtures.prefix_close_time` (L89-93) as the horizon helper.
- `test_candidates.py` → `tests/unit/test_sweeps.py` + `test_zones.py` (sculpted bar sequences with hand-derivable expected values; assert candidate or None per scenario.)
- `test_costs.py` → `tests/unit/test_normalize_and_config.py` pure-math style (no fixtures, direct function calls with literal expected floats; parametrize directions/fallback branches per Pitfall 2/8).
- `test_barriers.py` → `tests/unit/test_lifecycle.py` (per-bar state transition assertions; the named SL-first test, gap=open both directions, 96-bar off-by-one pin, per Pitfall 1/6).
- `test_replay.py` → `tests/unit/test_pools.py` (loop + suppression; warmup skip, one-at-a-time D-05, min-R:R discard D-12).
- `test_replay_repaint.py` → **[COPY]** `tests/unit/test_repaint.py` L83-105 + `_detector_fixtures.assert_point_in_time_prefix_equality` (L96-109):
  ```python
  full = runner(bars.copy())
  for k in range(min_prefix, len(bars)):
      prefix = runner(bars.iloc[:k].copy())
      visible = full[full["confirmed_at"] <= prefix_close_time(bars, k)].reset_index(drop=True)
      pd.testing.assert_frame_equal(prefix, visible, check_exact=True)
  ```
  Adapt: `replay(bars[:S+1])` trades == visible subset of `replay(full)` trades with entry time ≤ close(S), `check_exact=True`, 1-by-1 AND chunked (test_repaint.py L94-105).
- `test_stats.py` → `tests/unit/test_history_report.py` (report-dict assertions L155-201) + parametrized edge cases (empty/all-win/all-loss/zero-loss PF).
- `test_walkforward.py` → `tests/unit/test_history_report.py` (data-seeded flows) + pure window math tests (no overlap, chronological, expanding train, small windows, exactly-one-window assignment).
- `test_reports.py` → `tests/unit/test_idempotent_store.py` **[COPY]** — atomic write + `test_no_tmp_file_remains_after_successful_merge` (L85) + determinism (same inputs ⇒ identical label parquet bytes).
- `test_backtest_config.py` → `tests/unit/test_normalize_and_config.py` **[COPY]** — `_write_config` (L48-52), `_base_values` (L55-77), `pytest.mark.parametrize` rejection matrices (L159-164), `pytest.raises(ValueError, match="<key>")`.

## Shared Patterns

Cross-cutting patterns applying to multiple new files. Each named source below is the *existing* implementation to reuse — do not re-invent.

### 1. Point-in-time visibility (the anti-lookahead choke point)
**Source:** `src/ai_trading/detectors/mtf.py` L115-118 (`_is_live`), L152-160 (`merge_asof` strictly-before D-15), L165-200 (per-row as-of loop); verified contracts in 02-VERIFICATION.
**Apply to:** `backtest/asof.py` (owns it), `backtest/chain.py`, `backtest/replay.py`, `backtest/candidates.py`, `tests/unit/test_replay_repaint.py`.
Two anchors: close-time stamps → `close_t = t_S + TF`; bar-time stamps → `t_S`. Never one filter for all tiers (Pitfall 4). MTF payload rows consumed as-is, never re-anchored.

### 2. Atomic write + idempotent artifact persistence
**Source:** `src/ai_trading/stores/bar_store.py` L67-75 (tmp + `os.replace`, cleanup on exception, zstd) **[COPY verbatim]**.
**Apply to:** `backtest/reports.py` (labels + canon JSON + per-window Parquet), `backtest/runner.py`; pattern re-quoted in every plan that writes an artifact. Never delete-then-write, never bake run-id/timestamps into data files (Pitfall 11).

### 3. Fail-fast config validation (frozen dataclass)
**Source:** `src/ai_trading/config.py` L29-45 (`_REQUIRED_KEYS`), L48-64 (frozen `Config`), L109-160 (`_is_int` + `_validate` raising `ValueError(f"{name} must be ...")`).
**Apply to:** `config.py` modification, `config.toml` modification, `backtest/runner.py` (exit 2 on config error), `tests/unit/test_backtest_config.py`. New keys get positive/bounds checks; never `print(cfg)` (credential hygiene V7).

### 4. Pure-function discipline + schema pinning
**Source:** `src/ai_trading/detectors/pools.py` L81-111 (`_empty_pools_frame`), L114-148 (invariant `ValueError` validators), L324-339 (dtype pinning: `pd.StringDtype()` + `"datetime64[us]"` for `check_exact=True` repaint stability); `detectors/swings.py` L42-53 (empty frame + dtypes); `detectors/__init__.py` (headed docstring, no imports).
**Apply to:** ALL `backtest/*.py` source modules + their tests. Every output schema pinned as a `*_COLUMNS` list; empty input → schema-correct empty frame; input frames never mutated; zero adapter-tier (MetaTrader5) imports — extended by the file-content assertion (test_detector_integration.py L380-390).

### 5. Sequential event-sparse loop (state machine)
**Source:** `src/ai_trading/detectors/pools.py::_detect_for_symbol` L174-284 (due-map, loop-local dict state, warmup `continue`, counter IDs); `detectors/zones.py::_zones_for_symbol` L159-176 (per-bar first-event stamping, monotone state).
**Apply to:** `backtest/replay.py` (one-position slot), `backtest/barriers.py` (96-bar walk), `backtest/candidates.py` (record emission). "Deliberately not vectorized" is the project precedent; vectorize only stats (Pattern 6).

### 6. CLI + exit-code contract
**Source:** `src/ai_trading/history_report.py::main` L406-467 (argparse `--config`, `logging.basicConfig`, config error → 2, runtime error → 1, `finally: conn.close()`).
**Apply to:** `backtest/runner.py`, `tests/unit/test_reports.py`/history-report-style CLI tests.

### 7. Test layering & fixtures
**Source:** `tests/conftest.py` L26-60 (`make_bars` — note `spread=list(range(count))` includes zeros), L63-84 (`_make_cfg`/`make_cfg` fixture), L247-251 (`fake_mt5` fixture); `tests/unit/_detector_fixtures.py` (L17-31, L89-109); `pyproject.toml` markers `unit`/`mt5` (`-m "not mt5"` default — backtester is unit-only, no mt5 tests).
**Apply to:** ALL new test modules + `_backtest_fixtures.py`. `@pytest.mark.unit` on every test; consume `conftest`/`_detector_fixtures`, never extend them.

## No Analog Found

None. All 24 files have at least a role-match analog; the weakest matches (candidates.py, costs.py, stats.py, walkforward.py) are named in the table above with the structure source to copy plus the RESEARCH.md pattern/code-example (L238-515) to take the rule body from.

## Metadata

**Analog search scope:** `src/ai_trading/**` (16 files), `tests/**` (20 files), `config.toml`, `pyproject.toml`; phase artifacts 03-CONTEXT/03-RESEARCH, 01-PATTERNS, 02-VERIFICATION references.
**Files read for pattern extraction:** 16 source files (config.py, normalize.py, history_report.py, bar_store.py, meta_store.py, mt5_client.py, collector.py, detectors/{__init__,swings,zigzag,pools,zones,mtf,atr}.py) + 7 test files (conftest.py, _detector_fixtures.py, test_repaint.py, test_detector_integration.py, test_normalize_and_config.py, test_history_report.py partial, test_pools/lifecycle/sweeps/zones/mtf_join/idempotent_store via shared conventions).
**Pattern extraction date:** 2026-09-01
**Key finding:** Phase 3 is NOT greenfield. `pools.py`/`zones.py` provide the sequential-loop precedent; `history_report.py` provides the CLI/report pattern; `bar_store.py` provides atomic writes; `mtf.py` provides as-of discipline; `_detector_fixtures.py` + `test_repaint.py` provide the prefix-equality machinery. Only the rule bodies (entry candidates, cost formulas, barrier logic, stats formulas) are new — those come from 03-RESEARCH.md Code Examples 1-4 (L437-515), not from inventing.
