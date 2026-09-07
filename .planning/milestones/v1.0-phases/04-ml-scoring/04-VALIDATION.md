---
phase: 4
slug: ml-scoring
status: ready
nyquist_compliant: true
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

Regenerated from the final plans (04-01/02/03, 3 tasks each) and the RESEARCH.md Validation Architecture.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 1 | AI-01 (W0 enabler) | T-04-04, T-04-SC | Pinned stack verified (lightgbm 4.7.0 / sklearn 1.9.0 / joblib 1.6.x); thirteen ml_* keys fail-fast validated in frozen Config; Phase 4 fixture module created | unit | `uv run python -c "import lightgbm, sklearn, joblib; print(lightgbm.__version__, sklearn.__version__, joblib.__version__)" && uv run pytest tests/unit -q` | ✅ (test_backtest_config.py extended in W0) | ⬜ pending |
| 04-01-02 | 01 | 1 | AI-01 | T-04-02 | Point-in-time feature builder through visible_mask anchors; decision-close R:R never the fill-based column; session-gap-robust decision-bar location | unit | `uv run pytest tests/unit/test_ml_features.py -q` | ⬜ W0 | ⬜ pending |
| 04-01-03 | 01 | 1 | AI-01 / SC1 | T-04-02 | Three-layer audit falsifiable (L1 prefix-equivalence mutation test, L2 spec manifest, L3 forbidden-column + ml/-wide vendor purity) + atomic feature_audit.json | unit | `uv run pytest tests/unit/test_ml_feature_audit.py tests/unit/test_ml_features.py -q` | ⬜ W0 | ⬜ pending |
| 04-02-01 | 02 | 2 | AI-04 (OQ5/SC3) | T-04-02 | Boundary purge pinned both sides; embargo knob moves boundary by whole bars; folds derive exclusively from build_windows (no second splitter) | unit | `uv run pytest tests/unit/test_ml_purge.py tests/unit/test_ml_folds.py -q` | ⬜ W0 | ⬜ pending |
| 04-02-02 | 02 | 2 | AI-02/AI-03 | T-04-05, T-04-08, T-04-09 | Deterministic decided-only LightGBM (no imbalance flags); CalibratedClassifierCV with structurally-required explicit folds (ensemble=True); preflight stable prefixes; reliability helper | unit | `uv run pytest tests/unit/test_ml_train.py -q` | ⬜ W0 | ⬜ pending |
| 04-02-03 | 02 | 2 | AI-02/AI-03 / SC4 | T-04-01 | Versioned bundle + manifest (incl. reliability summary) + LATEST pointer, atomic writes; loader validates schema/feature-list/library majors; scorer restores categories | unit | `uv run pytest tests/unit/test_ml_artifact.py tests/unit/test_ml_scorer.py -q` | ⬜ W0 | ⬜ pending |
| 04-03-01 | 03 | 3 | AI-02 | T-04-10 | Deterministic [0,1] heuristic keyed to FEATURE_SPEC and versioned; flagged non-ML; missing-safe | unit | `uv run pytest tests/unit/test_ml_heuristic.py -q` | ⬜ W0 | ⬜ pending |
| 04-03-02 | 03 | 3 | AI-04/AI-02 (D-01/D-02) | T-04-03, T-04-02, T-04-10 | Decided-only headline metrics; TIMEOUT scored-and-flagged excluded; skip-and-record starvation; score_source + provenance on every score row | unit | `uv run pytest tests/unit/test_ml_evaluate.py -q` | ⬜ W0 | ⬜ pending |
| 04-03-03 | 03 | 3 | AI-04/AI-02 (D-05) | T-04-06, T-04-04 | Label-count gate refusal names counts/threshold/remedy; {2,1,0} exit-code contract; end-to-end synthetic train run writes bundle + reports | unit | `uv run pytest tests/unit/test_ml_runner.py -q && uv run pytest tests/unit -q` | ⬜ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `uv add lightgbm scikit-learn` — the only Wave-0 install (versions verified by research smoke: lightgbm 4.7.0, scikit-learn 1.9.0, joblib 1.6.0)
- [ ] Create `tests/unit/_ml_fixtures.py` — NEW Phase 4 local helper following the direct-import convention: imports from `_backtest_fixtures.py` / `conftest.py`, NEVER modifies either file (04-01 Task 1 provides ml_cfg / make_labels / sculpted_label_world; 04-01 Task 2 appends synthetic_feature_frame once FEATURE_SPEC exists)
- [ ] Extend `tests/unit/test_backtest_config.py` (existing Phase 3 config-test home) with the thirteen ml_* key validation cases — extend the module, never fork
- [ ] Test modules are created test-first by their owning task (no separate stub pass): 04-01 → `test_ml_features.py`, `test_ml_feature_audit.py`; 04-02 → `test_ml_purge.py`, `test_ml_folds.py`, `test_ml_train.py`, `test_ml_artifact.py`, `test_ml_scorer.py`; 04-03 → `test_ml_heuristic.py`, `test_ml_evaluate.py`, `test_ml_runner.py`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Deep-history backfill via MT5 terminal | D-05 data depth | Requires the user's running, logged-in MT5 terminal | Run collector backfill (DATA-04 path) for M15/H1/H4; re-check history depth per symbol/TF |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 180s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** ready
