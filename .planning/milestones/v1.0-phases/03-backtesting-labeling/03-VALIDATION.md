---
phase: 3
slug: backtesting-labeling
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-09-01
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x |
| **Config file** | pyproject.toml (`[tool.pytest.ini_options]`) |
| **Quick run command** | `uv run pytest -q -m "not mt5" tests/unit` |
| **Full suite command** | `uv run pytest -m "not mt5"` |
| **Estimated runtime** | ~60 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest -q -m "not mt5" tests/unit`
- **After every plan wave:** Run `uv run pytest -m "not mt5"`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 120 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 03-01-T1 | 01 | 1 | BT-01 | T-03-01, T-03-04 | Config knobs fail-fast (12 new keys); conftest/_detector_fixtures untouched | unit | `pytest tests/unit/test_backtest_config.py tests/unit/test_normalize_and_config.py` | ⬜ W0 | ⬜ pending |
| 03-01-T2 | 01 | 1 | BT-01, BT-02 | T-03-01, T-03-02 | Same detector chain via run_chain (no re-implementation); as-of visibility per tier; spread points->price + fallback + direction-aware fills | unit | `pytest tests/unit/test_asof.py tests/unit/test_costs.py tests/unit/test_detector_integration.py` | ⬜ W0 | ⬜ pending |
| 03-01-T3 | 01 | 1 | BT-01, BT-02 | T-03-01, T-03-03 | Entry candidates (D-01..D-13 incl. swing TP); one-at-a-time state machine; prefix-equivalence look-ahead proof | unit | `pytest tests/unit/test_candidates.py tests/unit/test_replay.py tests/unit/test_replay_repaint.py` | ⬜ W0 | ⬜ pending |
| 03-02-T1 | 02 | 2 | BT-03 | T-03-01 | SL-first tie incl. entry bar, gap=open both directions, 96-bar inclusive window, TIMEOUT at final bar close | unit | `pytest tests/unit/test_barriers.py` | ⬜ W0 | ⬜ pending |
| 03-02-T2 | 02 | 2 | BT-04 | T-03-02 | Win rate / PF guards / expectancy / max DD / avg R / counts, TIMEOUT denominator policy, raw+net delta | unit | `pytest tests/unit/test_stats.py` | ⬜ W0 | ⬜ pending |
| 03-02-T3 | 02 | 2 | BT-03, BT-04 | T-03-03 | Atomic (tmp+os.replace) deterministic label/canon artifact writes; manifest separation | unit | `pytest tests/unit/test_reports.py` | ⬜ W0 | ⬜ pending |
| 03-03-T1 | 03 | 3 | BT-05 | T-03-01 | Walk-forward chronological/zero-overlap/expanding-train; small windows; exactly-one-window assignment | unit | `pytest tests/unit/test_walkforward.py` | ⬜ W0 | ⬜ pending |
| 03-03-T2 | 03 | 3 | BT-05 | T-03-03 | walkforward.parquet byte-determinism; window manifest separation; no .tmp residue | unit | `pytest tests/unit/test_reports.py` | ⬜ W0 | ⬜ pending |
| 03-03-T3 | 03 | 3 | BT-05 | T-03-02, T-03-04 | Runner exit codes 2/1/0; D-21 gate refusal + --min-history-days override; offset uniformity; MT5-free | unit | `pytest tests/unit/test_runner.py` | ⬜ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/test_backtest_config.py` — stubs for BT-01/config knobs
- [ ] `tests/unit/test_asof.py` — stubs for BT-01 (as-of visibility)
- [ ] `tests/unit/test_costs.py` — stubs for BT-02
- [ ] `tests/unit/test_candidates.py` — stubs for BT-01 (entry rules D-01..D-13)
- [ ] `tests/unit/test_replay.py` — stubs for BT-01/BT-02 (state machine)
- [ ] `tests/unit/test_replay_repaint.py` — stubs for BT-01 (anti-lookahead)
- [ ] `tests/unit/test_barriers.py` — stubs for BT-03
- [ ] `tests/unit/test_stats.py` — stubs for BT-04
- [ ] `tests/unit/test_reports.py` — stubs for BT-03/BT-04/BT-05 (artifact writers)
- [ ] `tests/unit/test_walkforward.py` — stubs for BT-05
- [ ] `tests/unit/test_runner.py` — stubs for BT-05 (CLI)
- [ ] `tests/unit/_backtest_fixtures.py` — NEW local helper (set_spreads / bt_cfg / write_bars_parquet); `tests/conftest.py` stays UNTOUCHED per Phase 1 contract (make_bars/_make_cfg reused via direct import)

*If none: "Existing infrastructure covers all phase requirements."*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Cost asymmetry convention (long spread at entry / short at exit) | BT-02 | Assumption A1 flagged in RESEARCH.md; needs human confirmation | Review A1 in RESEARCH.md, confirm or override convention |

*If none: "All phase behaviors have automated verification."*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 120s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
