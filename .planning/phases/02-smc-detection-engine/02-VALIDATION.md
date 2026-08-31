---
phase: 2
slug: smc-detection-engine
status: ready
nyquist_compliant: true
wave_0_complete: false
created: 2026-08-30
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.1 (uv dev dependency, verified in Phase 1) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` — markers `unit`/`mt5`, `addopts = '-m "not mt5"'` |
| **Quick run command** | `uv run pytest -q` (unit only, MT5-free) |
| **Full suite command** | `uv run pytest -q -m "unit or mt5"` (Phase 2 adds no mt5-marked tests; live tests unchanged from Phase 1) |
| **Estimated runtime** | ~2–10 seconds (Phase 1 suite ran 0.37 s; detector suites are pure-frame and event-sparse) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest -q` (plus the task's own test file for fast targeting)
- **After every plan wave:** Run `uv run pytest -q -m "unit or mt5"`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | SMC-01 | T-2-01/02/04 | Strict 2/2 fractal with confirmation stamping; V5 guards + empty-frame contracts; non-mutation | unit | `uv run pytest tests/unit/test_swings.py tests/unit/test_repaint.py -q` | ❌ W0 | ⬜ pending |
| 02-01-02 | 01 | 1 | SMC-01 | T-2-02/03/04 | SMC-01 behaviors locked: strictness, confirmed_at, schema, empty/short contracts, ATR warmup | unit | `uv run pytest tests/unit/test_swings.py -q` | ❌ W0 | ⬜ pending |
| 02-01-03 | 01 | 1 | SMC-01 (SC1) | T-2-01 | Repaint T1/T2: appended bars never alter confirmed swings; zigzag tail-only mutability | unit | `uv run pytest tests/unit/test_repaint.py -q` | ❌ W0 | ⬜ pending |
| 02-02-01 | 02 | 2 | SMC-02, SMC-05 | T-2-01/02 | As-of ATR tolerance (no full-frame stats); 2-touch activation; guards + empty contracts | unit | `uv run pytest tests/unit/test_pools.py tests/unit/test_sweeps.py -q` | ❌ W0 | ⬜ pending |
| 02-02-02 | 02 | 2 | SMC-02, SMC-05 (SC1 T3) | T-2-01/03/04 | Pool tier-3 repaint immutability + standalone-vs-in-frame consistency | unit | `uv run pytest tests/unit/test_pools.py -q` | ❌ W0 | ⬜ pending |
| 02-02-03 | 02 | 2 | SMC-03 | T-2-01 | Sweep vs breakout per pinned 2-bar inclusive window; one-and-done terminal states | unit | `uv run pytest tests/unit/test_sweeps.py -q` | ❌ W0 | ⬜ pending |
| 02-03-01 | 03 | 2 | SMC-04, SMC-05 | T-2-01/02 | Per-leg zones + wick-touch/committed-close lifecycle; guards + empty contracts | unit | `uv run pytest tests/unit/test_zones.py tests/unit/test_lifecycle.py -q` | ❌ W0 | ⬜ pending |
| 02-03-02 | 03 | 2 | SMC-04 (SC1 T3) | T-2-01/03/04 | Zone tier-3 repaint immutability for completed legs | unit | `uv run pytest tests/unit/test_zones.py -q` | ❌ W0 | ⬜ pending |
| 02-03-03 | 03 | 2 | SMC-05 | T-2-01 | Monotone first-event lifecycles; wick-poke does not invalidate; same-bar double-stamp order | unit | `uv run pytest tests/unit/test_lifecycle.py -q` | ❌ W0 | ⬜ pending |
| 02-04-01 | 04 | 3 | SMC-06 | T-2-01/02 | Strictly-before confirmation join (allow_exact_matches=False); lean payload guards | unit | `uv run pytest tests/unit/test_mtf_join.py -q` | ❌ W0 | ⬜ pending |
| 02-04-02 | 04 | 3 | SMC-06 (SC4) | T-2-01/05 | D-15 exact-match exclusion; bias mapping; DST +3→+2 H4-anchor continuity | unit | `uv run pytest tests/unit/test_mtf_join.py -q` | ❌ W0 | ⬜ pending |
| 02-04-03 | 04 | 3 | SMC-06 (SC4/SC5) | T-2-01/03/04/05 | Full-chain purity (no vendor imports, inputs unmutated), determinism, schema locks | unit | `uv run pytest tests/unit/test_detector_integration.py -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `src/ai_trading/detectors/` package (02-01 creates the package + atr/swings/zigzag; 02-02 adds pools.py; 02-03 adds zones.py; 02-04 adds mtf.py — each with pinned output schemas + empty-frame contracts) — enables schema-asserting tests to be written first
- [ ] `tests/unit/_detector_fixtures.py` (02-01) — swing/prefix-equality sculptor helpers over `make_bars`; plans 02-02/02-03/02-04 add module-local helpers and never extend root `conftest.py`
- [ ] `tests/unit/test_swings.py` + `tests/unit/test_repaint.py` (02-01) — SMC-01/SC1 repaint suite FIRST as the executable spec
- [ ] `tests/unit/test_pools.py`, `tests/unit/test_sweeps.py` (02-02) — SMC-02/03 + pool tier-3 repaint
- [ ] `tests/unit/test_zones.py`, `tests/unit/test_lifecycle.py` (02-03) — SMC-04/05 + zone tier-3 repaint
- [ ] `tests/unit/test_mtf_join.py`, `tests/unit/test_detector_integration.py` (02-04) — SMC-06 + SC4/SC5
- [ ] Config extension: **planner decision — none.** Detector params stay as function defaults with locked D-values (fractal width 2, atr_period=14, tolerance 0.1, sweep_window_bars=2); no `config.py` change, no conftest `_make_cfg` changes.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| *(none)* | | All Phase 2 behaviors are pure and unit-testable — detectors need no MT5 terminal; the mt5 marker remains Phase 1 live-integration only | |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (detector package per plan + 8 test modules + fixture helpers, mapped above)
- [x] No watch-mode flags
- [x] Feedback latency < 10 s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-08-31 (planning fill — all 12 tasks carry automated verify commands; `wave_0_complete` flips to true when plan 02-01 lands the package + repaint suite)
