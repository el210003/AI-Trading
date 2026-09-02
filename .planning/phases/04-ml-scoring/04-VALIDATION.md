---
phase: 4
slug: ml-scoring
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-09-02
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x |
| **Config file** | pyproject.toml (`[tool.pytest.ini_options]`) |
| **Quick run command** | `uv run pytest -q -m "not mt5" tests/unit` |
| **Full suite command** | `uv run pytest -m "not mt5"` |
| **Estimated runtime** | ~90 seconds (LightGBM training tests are slower) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest -q -m "not mt5" tests/unit`
- **After every plan wave:** Run `uv run pytest -m "not mt5"`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 180 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 1 | AI-01 | — | Features point-in-time only; three-layer audit (prefix-equivalence, provenance manifest, forbidden-column guard) | unit | `pytest tests/unit/test_features.py tests/unit/test_feature_audit.py` | ⬜ W0 | ⬜ pending |
| 04-02-01 | 02 | 1 | AI-02 | — | LightGBM P(WIN) binary target, pooled model, deterministic training | unit | `pytest tests/unit/test_train.py` | ⬜ W0 | ⬜ pending |
| 04-02-02 | 02 | 1 | AI-03 | — | Calibration via CalibratedClassifierCV with explicit chronological folds; no shuffled CV | unit | `pytest tests/unit/test_calibrate.py` | ⬜ W0 | ⬜ pending |
| 04-02-03 | 02 | 1 | AI-02/03 | — | Versioned artifacts (model + calibrator + feature metadata) loadable by scorer | unit | `pytest tests/unit/test_artifacts.py` | ⬜ W0 | ⬜ pending |
| 04-03-01 | 03 | 1 | AI-04 | — | Walk-forward reuse, OQ5 purge (exit_time >= test_start dropped), no shuffled splits | unit | `pytest tests/unit/test_walkforward_eval.py` | ⬜ W0 | ⬜ pending |
| 04-03-02 | 03 | 1 | AI-02 | — | Heuristic bootstrap flagged score_source="heuristic"; label-count gate refusal | unit | `pytest tests/unit/test_bootstrap.py` | ⬜ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `uv add lightgbm scikit-learn` — the only Wave-0 install (versions verified by research smoke: lightgbm 4.7.0, scikit-learn 1.9.0, joblib 1.6.0)
- [ ] `tests/unit/test_features.py` — stubs for AI-01
- [ ] `tests/unit/test_feature_audit.py` — stubs for AI-01 audit
- [ ] `tests/unit/test_train.py`, `test_calibrate.py`, `test_artifacts.py` — stubs for AI-02/03
- [ ] `tests/unit/test_walkforward_eval.py`, `test_bootstrap.py` — stubs for AI-04
- [ ] Extend `tests/unit/_backtest_fixtures.py` with labeled-frame fixtures (reuse, do not fork)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Deep-history backfill via MT5 terminal | D-05 data depth | Requires the user's running, logged-in MT5 terminal | Run collector backfill (DATA-04 path) for M15/H1/H4; re-check history depth per symbol/TF |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 180s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
