# Phase 4: ML Scoring - Research

**Researched:** 2026-09-02
**Domain:** Point-in-time feature engineering from SMC detector state, LightGBM + scikit-learn probability calibration, walk-forward ML training/evaluation over the Phase 3 harness, versioned model artifacts (Python 3.12 / pandas 3.0.5)
**Confidence:** HIGH (stack + calibration mechanics verified by a runtime smoke in this session on the exact project environment; feature/purge design grounded in verified Phase 2/3 contracts; small-data conventions cited from official docs)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** The model predicts **binary P(WIN) among decided trades**: positive class = WIN (TP hit), negative = LOSS (SL hit). TIMEOUT rows are **excluded from training and from headline metrics** — consistent with the Phase 3 A4 win-rate denominator (wins/(wins+losses)). Dashboard semantics: "probability this setup hits TP before SL".
- **D-02:** **Score-and-flag for TIMEOUT**: the scorer emits a probability for every candidate row; in walk-forward eval artifacts TIMEOUT rows appear flagged `excluded` (with their scores) but are kept out of headline metrics (AUC, calibration curve, win-rate). No metric contamination, no information loss.
- **D-03:** **One pooled model** across all symbols and timeframes: symbol and timeframe enter as categorical features. A single versioned artifact; per-symbol model splits are explicitly NOT v1 (dataset too small to split three ways).
- **D-04:** **Probability only** — no expected-R regression head in v1 (agent discretion, resolved). AI-02 asks for a probability score; a regressor on the current tiny decided-trade set would be noise. Logged as a deferred idea.
- **D-05:** The M15 store holds ~9 days of history (Phase 3 research reality) — far below robust LightGBM training depth. The user did not lock a strategy in discussion. Research MUST evaluate: (a) deepening stored history via the Phase 1 collector's backfill path (DATA-04; requires the user's MT5 terminal running), vs (b) training tiny with the harness's small-window support (D-20), vs (c) pipeline-first + backfill as a data task. Roadmap plan 04-03's heuristic-score bootstrap for unlabeled periods exists precisely for thin-data periods. The Phase 3 UAT deferred real-data demo (history-depth decision) is a prerequisite data task for any real training run.

### the agent's Discretion
- Feature engineering details: exact features, encodings, transforms — grounded in the point-in-time constraint and the feature audit
- Feature audit implementation (how "nothing post-decision-bar" is proven — e.g., snapshot/recompute comparison tests)
- LightGBM hyperparameters, search policy, early stopping, class-imbalance handling
- Calibration method within CalibratedClassifierCV (isotonic vs Platt/sigmoid) and calibration fold strategy compatible with walk-forward (no shuffled splits)
- Train/test boundary purge mechanics — the obligation deferred from Phase 3 RESEARCH OQ5 (embargo/leakage handling at window boundaries)
- Model artifact format (e.g., joblib bundle) + versioning scheme + loader API shape for the scorer
- Heuristic-score bootstrap design for unlabeled periods (what the heuristic is, how it's flagged as non-ML)
- Retrain CLI design (follows the Phase 3 `backtest` runner CLI pattern) and scheduled-retrain config keys
- Eval report format (reliability data, per-window metrics) and on-disk layout under `data/`

### Deferred Ideas (OUT OF SCOPE)
- **Expected-R regression head** — surfaced in discussion, resolved out of v1 scope (D-04). Natural candidate after deep-history backfill makes decided-trade counts meaningful; versioned artifacts make it a non-breaking addition.
- **Per-symbol model split** — revisit trigger: after deep history exists, evaluate whether per-symbol models beat the pooled model on walk-forward evidence.
- **ENH-01 calibration reliability report in dashboard** — v2 display work; Phase 4 only records the reliability data.
- **Real-data demo run + history-depth backfill** — Phase 3 UAT deferred item; a data task requiring the user's MT5 terminal. Prerequisite for any real (non-synthetic) training run in this phase.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| AI-01 | ML features are assembled point-in-time from SMC state (no information after the decision bar) | Pattern 1 feature builder reuses `CandidateState` + `asof.visible_mask` anchors exactly; Pattern 2 three-layer audit (prefix-equivalence + provenance manifest + forbidden-column guard); Pitfall 1 (the fill-open `rr` leak) identified and neutralized by recomputing R:R at the decision close |
| AI-02 | Each candidate setup receives an ML probability score from a gradient-boosted model | LightGBM 4.7.0 verified on the exact env (runtime smoke); pooled model (D-03) with native pandas-categorical features (verified); scorer API pattern (load artifact → score feature frame → P(WIN) + contributors via `pred_contrib`, verified) |
| AI-03 | ML scores are calibrated (isotonic/Platt) so displayed probabilities are honest | CalibratedClassifierCV mechanics verified end-to-end (explicit chronological `cv` iterable, ensemble=True, sigmoid default per official small-sample guidance, reliability data via `calibration_curve`, FrozenEstimator prefit path); Pitfall 4 (isotonic overfit ≪1000 samples) and Pitfall 5 (imbalance flags distort probabilities) documented |
| AI-04 | ML training/evaluation follows a walk-forward protocol with no shuffled splits on time series | Phase 3 `walkforward.build_windows` is THE splitter of record (verified 03-VERIFICATION truth 12–14); calibration folds derive from the same windows; OQ5 purge mechanics specified (Pitfall 8 + Pattern 4); default StratifiedKFold inside CalibratedClassifierCV is a verified trap to avoid |
</phase_requirements>

## Project Constraints (from AGENTS.md)

No `./AGENTS.md`, `./CLAUDE.md`, or `.claude/CLAUDE.md` exists (verified this session, matching the project instructions). Binding constraints inherited from the planning corpus and project instructions:

- **One shared, look-ahead-safe code path for live analysis AND backtests (PROJECT.md, non-negotiable).** Phase 4's scorer and feature builder must be reusable by Phase 6 live analysis with zero backtest-only branches. The ML modules stay MT5-free, pure, side-effect-free until the runner tier (Phase 3 established pattern).
- **Hybrid AI separation (PROJECT.md):** ML owns probability; Phase 5 LLM only narrates. Phase 4 emits the score + contributors; no narrative work in this phase.
- Python 3.12, pandas>=3.0, pytest 9.x with `unit`/`mt5` markers (`addopts = '-m "not mt5"'`), ruff line-length 100, frozen-`Config` dataclass with fail-fast validation, atomic tmp+`os.replace` artifact writes. Zero new dependencies except the locked LightGBM + scikit-learn (locked at project-init research; CONTEXT.md line 96).
- **SC1/SC2/SC3/SC4 wording is binding:** (1) a feature audit must CONFIRM point-in-time assembly; (2) reliability data recorded via CalibratedClassifierCV — the artifact retains reliability data, not just the calibrated model; (3) the Phase 3 walk-forward harness is the only splitter, no shuffled splits anywhere INCLUDING inside calibration folds and hyperparameter search; (4) model + calibrator + feature metadata are versioned and loadable by the scorer.

## Summary

Phase 4 adds the first ML tier above the Phase 3 label store: a pure feature builder that re-derives decision-time SMC state for every labeled trade, a LightGBM P(WIN) classifier calibrated through `CalibratedClassifierCV`, walk-forward training/evaluation reusing `backtest/walkforward.py` unchanged, and a versioned artifact bundle that Phase 6 will load. The decisive verification of this research is a **runtime smoke on the project's exact environment** (Python 3.12.12, pandas 3.0.5, numpy 2.5.2): lightgbm 4.7.0 + scikit-learn 1.9.0 + joblib 1.6.0 install together, pandas `category` dtypes flow through `LGBMClassifier` under a calibrator wrapper, an explicit chronological fold iterable is accepted as `cv`, `calibration_curve` yields the reliability arrays SC2 wants, `pred_contrib=True` yields per-feature contributors without adding SHAP, and a retrain with `deterministic=True` + `force_row_wise=True` + `num_threads=1` + fixed seed reproduces **byte-identical probabilities**. The stack shape is proven, not assumed.

Two verified API findings shape the plan more than any hyperparameter. First, `CalibratedClassifierCV(ensemble=False)` is **unusable** for this project: it routes through `cross_val_predict`, which raised `ValueError: cross_val_predict only works for partitions` when folds did not tile the data — and a pure expanding-train chronology can never tile (the head of the series has no prior data to train on). `ensemble=True` with explicit expanding folds is the verified-correct shape. Second, `cv=None`/`cv=int` silently selects `StratifiedKFold` — a class-stratified round-robin that destroys time ordering — so the SC3 "no shuffled splits anywhere" rule must be enforced by *always passing explicit folds* (and a named test that would fail if the default path is ever used). On method choice: sklearn's own docs state isotonic "is not recommended when the number of calibration samples is too low (≪1000) since it then tends to overfit" — with the tiny decided-trade counts available now, **sigmoid (Platt) is the v1 default** behind a config knob.

The data reality resolves D-05: the M15 store holds 541/501/501 bars per symbol (7.2–9.6 days — re-verified on disk today), `data/labels/` does not exist yet (the Phase 3 real-data run is a pending human item), so real decided-trade counts today are plausibly single digits to ~20 across all symbols. That is below any trainable threshold — a single-class window is guaranteed, not a risk. The recommendation is **(c) pipeline-first**: prove the whole chain on synthetic fixtures + the harness's small-window support (b), and treat deep-history backfill (a) as the prerequisite human data task (Phase 3 UAT deferral) that unlocks real training. A label-count gate (config knob, D-21-style actionable refusal) prevents training on starvation data, and plan 04-03's heuristic-score bootstrap covers thin periods in the meantime. One subtle leak dominates the feature design: the label's `rr` column is computed at the **fill** (next-bar open, D-04/D-12) — using it as a feature would import post-decision-bar information; the feature set must recompute R:R at the decision close, and the audit's prefix-equivalence + forbidden-column tests exist precisely to catch this class of bug.

**Primary recommendation:** A new MT5-free `src/ai_trading/ml/` package — `features.py` (pure `features_at_decision(CandidateState)` + batch `build_feature_frame`), `audit.py` (three-layer point-in-time proof + audit artifact), `train.py` (LightGBM + `CalibratedClassifierCV` with folds derived from `build_windows`, purge applied), `artifact.py` (joblib bundle + manifest + loader validation), `scorer.py` (loadable score API with contributors), `heuristic.py` (flagged non-ML bootstrap), `evaluate.py` + `runner.py` (walk-forward eval reports + CLI following the Phase 3 runner pattern), extending the frozen `Config` with `ml_*` knobs. Add exactly two dependencies: `uv add lightgbm scikit-learn` (joblib arrives transitively with sklearn).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Feature assembly at decision bar (AI-01) | Domain (`ml/features.py`, pure) | Storage (`data/labels/`, chain output) | Reuses `CandidateState` + `asof.visible_mask`; pure function of already-visible slices; MT5-free |
| Feature audit proof (SC1) | Domain (`ml/audit.py`) + tests | Reports (audit artifact) | Prefix-equivalence reuses the Phase 2/3 repaint pattern; provenance manifest is data, not convention |
| Purge/embargo at window boundaries (OQ5) | Domain (`walkforward`-adjacent pure helper) | Config (`ml_embargo_bars`) | Operates on label `[entry_time, exit_time]` stamps persisted exactly for this purpose (03-VERIFICATION deferred item 1) |
| Walk-forward folds for training + calibration (SC3) | Domain (`walkforward.build_windows` — unchanged) | — | THE splitter of record; Phase 4 derives train/test/calibration folds from it, never invents splits |
| Gradient-boosted P(WIN) training (AI-02) | Domain (`ml/train.py`, pure given frames) | Config (hyperparams) | LightGBM sklearn API; deterministic params; no I/O in the training core |
| Probability calibration + reliability data (AI-03/SC2) | Domain (`ml/train.py`) | Reports (reliability artifact) | `CalibratedClassifierCV` with explicit chronological folds; `calibration_curve` arrays persisted |
| Model artifact versioning + loader (SC4) | Storage (`data/models/`, atomic writes) | Domain (`ml/artifact.py` schema) | tmp+`os.replace` discipline; manifest separate from pickle; loader validates schema/library versions |
| Scorer API for Phase 6 | Domain (`ml/scorer.py`, importable, MT5-free) | — | Load artifact → score feature frame → P(WIN) + contributors; the live-path reuse point (BT-01 spirit) |
| Walk-forward ML eval reports (per-window AUC/log-loss/Brier/reliability) | Domain (`ml/evaluate.py`, pure) | Reports (`data/reports/`) | Decided-only headline (A4-consistent), TIMEOUT scored-and-flagged (D-02) |
| Heuristic-score bootstrap for unlabeled periods | Domain (`ml/heuristic.py`, pure) | Reports | Deterministic non-ML score, flagged `score_source="heuristic"`; never enters ML headline metrics |
| Retrain CLI + scheduling keys | Service (`ml/runner.py`, `python -m ai_trading.ml`) | Config | Mirrors Phase 3 runner exit-code contract (2 config / 1 runtime / 0 success) |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| lightgbm | 4.7.0 (PyPI 2026-07-18) | Gradient-boosted binary classifier P(WIN) | Locked at project init; native categorical features (pandas category dtype auto-aligned train/predict — verified); native NaN handling; `deterministic` reproducibility param — all verified by runtime smoke on the exact env |
| scikit-learn | 1.9.0 (PyPI 2026-06-02) | `CalibratedClassifierCV`, `calibration_curve`, metrics (`roc_auc_score`, `log_loss`, `brier_score_loss`), `FrozenEstimator` | Locked at project init; 1.9 explicitly fixes pandas 3 StringDtype interactions (verified in v1.9 whats-new); active pandas 3 support |
| joblib | 1.6.0 (transitive of scikit-learn) | Artifact serialization | Ships with sklearn — **no new direct dependency**; roundtrip of a fitted calibrator verified in the smoke |
| pandas / numpy / pyarrow | 3.0.5 / 2.5.2 / 25.0.1 (installed) | Feature frames, parquet artifacts | Locked Phase 1 stack; no changes |

### Supporting (project-internal, no installs)
| Item | Location | Purpose | When to Use |
|------|----------|---------|-------------|
| `walkforward.build_windows` / `Window` | `src/ai_trading/backtest/walkforward.py` | THE fold source for training, calibration, and evaluation (SC3) | Always — never a new splitter |
| `asof.visible_mask` + `STAMP_CLOSE`/`STAMP_BAR` | `src/ai_trading/backtest/asof.py` | Point-in-time visibility anchors for every feature source | Always — the single choke point |
| `candidates.CandidateState` / `compute_rr` | `src/ai_trading/backtest/candidates.py` | Decision-time state container the feature builder consumes | Always — same state the replay used |
| `chain.run_chain` | `src/ai_trading/backtest/chain.py` | Re-derives detector tiers over the range for feature building | Always — BT-01: never re-implement detection |
| `LABEL_COLUMNS` label frame | `src/ai_trading/backtest/replay.py` | Training records (outcome, entry/exit stamps, evidence IDs, bias) | Always — the training table seed |
| `stats.canonical_stats` conventions | `src/ai_trading/backtest/stats.py` | A4 decided-only denominator analog for ML headline metrics | Always — consistency with dashboard panels |
| `reports` atomic writers / `bar_store` discipline | Phase 3 / Phase 1 | tmp+`os.replace` pattern for model/eval artifacts | Always |
| `make_bars` + `_backtest_fixtures.py` | tests | Deterministic synthetic fixtures for feature-audit and training tests | Extend via local helper, never mutate conftest |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| LightGBM | XGBoost / CatBoost | All three are legitimate GBDTs; LightGBM is the project-locked choice with native pandas-category support and `deterministic` mode; switching adds nothing here |
| CalibratedClassifierCV | Hand-rolled Platt/isotonic fit on OOF scores | Hand-rolling calibration re-implements cross-fitting, fold plumbing, and `method` switching — exactly what the class owns; SC2 names the class |
| joblib bundle | ONNX / PMML / native LightGBM `save_model` | Portable formats lose the calibrator wrapper and feature metadata; the consumer is this same repo (Phase 6 Python) — joblib + manifest is simplest and complete |
| SHAP values | LightGBM `pred_contrib=True` | SHAP is an extra (forbidden) dependency; `pred_contrib` returns TreeSHAP-equivalent per-row contributions natively (verified in smoke) |
| `ensemble=False` calibration | `ensemble=True` with explicit folds | ensemble=False verified-broken for this shape (cross_val_predict partition requirement); True is the sklearn-default path for non-frozen estimators |

**Installation:**
```bash
uv add lightgbm scikit-learn
# joblib arrives transitively with scikit-learn (verified 1.6.0 in the smoke env)
uv run python -c "import lightgbm, sklearn, joblib; print(lightgbm.__version__, sklearn.__version__, joblib.__version__)"
```

**Version verification (performed this session):** PyPI JSON API — lightgbm 4.7.0 published 2026-07-18 (requires-python >=3.10); scikit-learn 1.9.0 published 2026-06-02 (requires-python >=3.11, satisfied by 3.12). Runtime smoke on Python 3.12.12 + pandas 3.0.5 + numpy 2.5.2: import, fit, calibrate, dump/load all green.

## Package Legitimacy Audit

> Protocol executed: seam check + PyPI registry verification + official-repo confirmation + Context7 official docs + runtime smoke. The seam returned **SUS** for both packages with reasons `unknown-downloads, no-repository` — a PyPI-JSON metadata limitation (pypi.org does not expose weekly downloads or repo_url in the fields the seam reads), not a supply-chain signal. Both packages are also locked at project-init research (Phase 4 stack lock, project instructions).

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| lightgbm | PyPI | ~11 yrs (first release 2015); 4.7.0 pub 2026-07-18 | not exposed via PyPI JSON (seam: unknown) | github.com/lightgbm-org/LightGBM (official, from PyPI `project_urls`) + readthedocs | seam SUS → overridden by authoritative evidence | Approved — locked stack; human legitimacy checkpoint satisfied by the project-init lock (Phase 1 precedent: metatrader5 5.0.6147) |
| scikit-learn | PyPI | ~18 yrs; 1.9.0 pub 2026-06-02 | not exposed via PyPI JSON (seam: unknown) | github.com/scikit-learn/scikit-learn (official, from PyPI `project_urls`) + scikit-learn.org | seam SUS → overridden by authoritative evidence | Approved — locked stack; same lock-as-checkpoint treatment |
| joblib | PyPI | transitive dep of scikit-learn | n/a | github.com/joblib/joblib | OK (not directly installed) | Approved — no direct dependency declared |

**Packages removed due to [SLOP] verdict:** none (no hallucinated package candidates were considered — the stack was locked at project init).
**Packages flagged as suspicious [SUS]:** lightgbm, scikit-learn by the seam's metadata-blind check only. Evidence overriding the flag: (1) official repos on PyPI metadata; (2) official documentation via Context7 (`/websites/scikit-learn_stable`, `/websites/lightgbm_readthedocs_io_en_stable`); (3) successful install + training + calibration + persistence smoke in a throwaway env this session; (4) project-init stack lock. If strict protocol is preferred, the planner may add one `checkpoint:human-verify` before `uv add` — recommended to treat the existing project-init lock as that verification, consistent with Phase 1 practice.

## Architecture Patterns

### System Architecture Diagram

```
        config.toml (ml knobs: feature_list_version, calibration_method,
        ml_embargo_bars, ml_min_train_labels, lgbm params, retrain schedule)
                            │
                            ▼
 ┌──────────────────────────────────────────────────────────────────────┐
 │  Retrain CLI (python -m ai_trading.ml)  — Phase 3 runner pattern      │
 │  1. Load labels from data/labels/*.parquet (Phase 3 output)           │
 │  2. LABEL-COUNT GATE: decided rows >= ml_min_train_labels, both       │
 │     classes present — else refuse with actionable message (D-21 style)│
 └──────────────────────────────┬───────────────────────────────────────┘
                                ▼
 ┌──────────────────────────────────────────────────────────────────────┐
 │  Feature builder (AI-01, pure)                                        │
 │  for each label: decision bar = bar before entry_time                 │
 │    run_chain over bars → per-tier slices via asof.visible_mask        │
 │    (STAMP_CLOSE / STAMP_BAR anchors) + payload row AS-IS (D-15)       │
 │    → CandidateState → features_at_decision() → feature row            │
 │  RECOMPUTES rr at the DECISION close (never the label's fill-based rr)│
 └──────────────────────────────┬───────────────────────────────────────┘
                                ▼
 ┌─────────────────────────────┬────────────────────────────────────────┐
 │  Feature audit (SC1)        │  Walk-forward folds (SC3 — build_windows│
 │  L1 prefix-equivalence      │  reuse: expanding train / rolling test) │
 │  L2 provenance manifest     │  per window: PURGE train labels with    │
 │  L3 forbidden-column guard  │  exit_time >= test_start (OQ5); embargo │
 │  → data/reports/            │  knob drops pre-boundary exits          │
 │    feature_audit.json       │  decided rows only for training (D-01)  │
 └─────────────────────────────┴─────────────────┬──────────────────────┘
                                ▼
 ┌──────────────────────────────────────────────────────────────────────┐
 │  Per-window training (AI-02/03)                                       │
 │  preflight: >= ml_min_train_labels AND both classes → else SKIP+record│
 │  LGBMClassifier(objective=binary, deterministic=True,                 │
 │    force_row_wise=True, num_threads=1, seed fixed, tiny-capacity)     │
 │  CalibratedClassifierCV(method=sigmoid|isotonic, cv=<explicit         │
 │    expanding folds from build_windows over the TRAIN window>,         │
 │    ensemble=True)   ← never cv=None/int (StratifiedKFold trap)        │
 │  reliability data: calibration_curve(prob_true, prob_pred) per window │
 └──────────────────────────────┬───────────────────────────────────────┘
                                ▼
 ┌──────────────────────────────────────────────────────────────────────┐
 │  Scoring the test window (D-02)                                       │
 │  ALL candidate rows scored: decided → headline metrics                │
 │  (AUC/log-loss/Brier); TIMEOUT → flagged `excluded`, scores kept      │
 │  windows with no valid model → heuristic.py score, score_source=      │
 │  "heuristic" (flagged non-ML; never in ML headline metrics)           │
 └──────────────────────────────┬───────────────────────────────────────┘
                                ▼
 ┌────────────────────────────┬─────────────────────────────────────────┐
 │  Artifact bundle (SC4)     │  Eval reports (consistent w/ Phase 3)   │
 │  data/models/pooled/v{N}/  │  data/reports/ml_walkforward.parquet    │
 │   model.joblib (model +    │   per (window,symbol,tf) + aggregate    │
 │   calibrator + feature     │  data/reports/ml_reliability.parquet    │
 │   metadata; atomic write)  │   (window_id, bin, prob_pred, prob_true)│
 │   manifest.json + LATEST   │  data/reports/ml_scores.parquet (flagged)│
 └────────────────────────────┴──────────────────┬──────────────────────┘
                                                 ▼
                            Phase 5 consumes P(WIN) + contributors;
                            Phase 6 loads the artifact via ml.scorer
```

Primary use-case trace: `python -m ai_trading.ml --config config.toml --train` → labels loaded → gate → features built point-in-time → audit artifact written → per-window folds derived → purge applied → LightGBM trained → calibrated with chronological folds → reliability recorded → test window scored (decided headline + TIMEOUT flagged) → artifact bundle versioned → eval reports written. No MT5 call anywhere; the module tier is MT5-free.

### Recommended Project Structure

```
src/ai_trading/
├── ml/                            # NEW — MT5-free, pure until the runner tier
│   ├── __init__.py                # bare marker (mirror backtest/__init__.py)
│   ├── features.py                # FEATURE_SPEC + features_at_decision(CandidateState, cfg)
│   │                              #   + build_feature_frame(labels, chain, bars) — pure
│   ├── audit.py                   # 3-layer point-in-time audit + audit artifact
│   ├── purge.py                   # boundary purge/embargo over (entry_time, exit_time)
│   ├── folds.py                   # build_windows → calibration fold pairs (expanding)
│   ├── train.py                   # preflight gate, LGBM fit, CalibratedClassifierCV wrap,
│   │                              #   reliability extraction — pure given frames
│   ├── artifact.py                # ARTIFACT_SCHEMA_VERSION, save/load, manifest writers
│   ├── scorer.py                  # Scorer: load → score(frame) → p_win + contributors
│   ├── heuristic.py               # deterministic non-ML score (flagged)
│   ├── evaluate.py                # per-window metrics + reliability + scores artifacts
│   └── runner.py                  # CLI: argparse --config/--train/--eval/--write; exit codes
└── config.py                      # EXTEND frozen Config with ml_* knobs
tests/unit/
├── test_ml_features.py            # per-feature as-of correctness + NA policy
├── test_ml_feature_audit.py       # L1 prefix-equivalence + L2 spec coverage + L3 guards
├── test_ml_purge.py               # boundary purge (exit_time >= test_start), embargo knob
├── test_ml_folds.py               # folds chronological, no shuffle, expanding
├── test_ml_train.py               # preflight skip, determinism, calibration wiring
├── test_ml_artifact.py            # roundtrip, schema validation, atomic writes
├── test_ml_scorer.py              # score API, category restoration, contributors
├── test_ml_evaluate.py            # decided-only headline, TIMEOUT flagged, nan guards
└── test_ml_heuristic.py           # determinism, [0,1] range, flag semantics
```

### Pattern 1: Feature builder as a pure function of the replay's own decision state

**What:** Features are extracted from the SAME `CandidateState` the replay assembled at the decision bar (as-of slices already produced by `asof.visible_mask`), plus the D-14 payload row consumed as-is. The batch path re-derives that state per label: `decision_bar_time = entry_time − TIMEFRAME_MINUTES["M15"] minutes`, decision bar index via `searchsorted` on `time_utc`, `run_chain` over the loaded range (BT-01: same detector functions), slices through `visible_mask` with the per-tier anchors.

**Why it is sound:** Phase 2 verified tier-3 prefix stability (repaint tests, `check_exact=True`) and Phase 3 verified decision-path prefix stability — a decision at the close of bar S sees identical records whether the chain ran over `bars[:S+1]` or the full range. Features computed through the same anchors inherit the guarantee; the audit (Pattern 2) proves the inheritance holds for the actual feature code.

**The decision-time R:R rule (the subtle leak):** the label's `rr` column is computed at the **fill** — the next bar's open (D-04/D-12) — which is post-decision-bar information. Features must recompute `compute_rr(direction, decision_close, sl_price, tp_price)` using the decision bar's close as the entry proxy. Risk/reward distances are likewise normalized by `atr14` **at the decision bar** (from `wilders_atr` over bars ≤ S). Pin this with a named test (`test_rr_feature_uses_decision_close_not_fill_open`).

**When to use:** always — it is the only shape that satisfies AI-01 and keeps Phase 6 live scoring on the same code path.

### Pattern 2: Three-layer feature audit (SC1's "confirms")

**What:** The audit is three independent layers, each a named test plus a persisted artifact:

- **L1 — Prefix equivalence (runtime proof):** `build_feature_frame` over truncated bar histories vs the full range: feature rows for labels whose decision time ≤ prefix close must be `check_exact` equal. Extends `tests/unit/test_replay_repaint.py` and `assert_point_in_time_prefix_equality` — the established Phase 2/3 pattern. This catches ANY post-decision-bar access in the feature code, including third-party functions called with future data.
- **L2 — Provenance manifest (spec proof):** every feature in `FEATURE_SPEC` declares `(name, dtype, source_tier, source_columns, stamp_kind ∈ {close, bar, payload-as-is})`. A test asserts the spec covers every produced column and that every declared stamp_kind maps to a real `visible_mask` call site (or payload-as-is consumption). The spec is embedded in the model artifact (SC4 "feature metadata") and in `data/reports/feature_audit.json`.
- **L3 — Forbidden-column guard (static proof):** features must never read label-side post-decision values (`rr` fill-based, `exit_*`, `r_*`, `outcome`) nor bars beyond the decision index. A static test asserts the feature module's source contains no references to those label columns, and L1 catches runtime violations.

**Audit artifact:** `data/reports/feature_audit.json` — `{max_abs_diff: 0.0, n_labels_checked, feature_spec_hash, spec_table, suite: "test_ml_feature_audit"}`. SC1's "confirms" becomes a checkable artifact rather than prose.

**When to use:** L1/L2/L3 run in the unit suite on synthetic data every time features change; the artifact is written by the runner on every training run.

### Pattern 3: Calibration folds derived from the walk-forward harness (SC3 inside calibration)

**What:** `CalibratedClassifierCV(estimator=lgbm, method="sigmoid", cv=<folds>, ensemble=True)` where `<folds>` is an explicit list of `(train_indices, test_indices)` pairs derived from `walkforward.build_windows` over the training window's entry times (expanding train / sequential test blocks — zero overlap, strictly chronological, no shuffles). Purge applies at every fold boundary exactly as at the train/test boundary.

**Why `ensemble=True` (verified):** with `ensemble=False`, sklearn routes calibration through `cross_val_predict`, which requires the folds to PARTITION the data; the runtime smoke reproduced `ValueError: cross_val_predict only works for partitions` on expanding folds. A strictly expanding-train chronology can never partition (the head has no prior train data). `ensemble=True` fits one calibrated classifier per fold and averages probabilities — deterministic given fixed seeds/threads (verified byte-identical in the smoke).

**Why never `cv=None`/`cv=int` (verified from docs):** the default selects `StratifiedKFold` for binary y — class-stratified round-robin assignment that destroys time ordering. A named test must fail if any call site omits explicit folds.

**Method default — sigmoid:** sklearn docs: isotonic "is not recommended when the number of calibration samples is too low (≪1000) since it then tends to overfit"; also "for very uncalibrated classifiers on very imbalanced datasets, sigmoid calibration might be preferred because it fits an additional intercept parameter." Decided-trade counts here are far below 1000 → `method="sigmoid"` (Platt) default, `ml_calibration_method` config knob for later isotonic evaluation after deep backfill.

**Reliability data (SC2):** `sklearn.calibration.calibration_curve(y_decided, p, n_bins=..., strategy="quantile")` per window (+ pooled) → `data/reports/ml_reliability.parquet` with `(window_id, bin, prob_pred, prob_true, count)`. The calibrator's internal parameters (sigmoid a/b) are additionally recorded in the manifest for full reproducibility.

### Pattern 4: Boundary purge + embargo (the OQ5 obligation)

**What:** Phase 3's `train_mask` is `entry_time < test_start` (D-19 expanding) — it includes labels whose OUTCOME resolves inside the test window. Phase 4 must, per window k with test span `[b_k, b_k + test_days)`:

1. **Purge (mandatory):** drop train labels with `exit_time >= b_k`. A label's outcome window `[entry_time, exit_time]` then never overlaps the test span; its exit was fully determined by pre-test price action. Boundary semantics: `exit_time` is the exit bar's OPEN time, so a label with `exit_time == b_k` exits on the first test bar → purged; `exit_time == b_k − 15m` closes exactly at `b_k` → kept. Pin both sides with named tests (`test_purge_drops_exit_at_test_start`, `test_purge_keeps_exit_closing_at_test_start`).
2. **Embargo (optional knob `ml_embargo_bars`, default 0):** additionally drop train labels whose exit closes within the embargo buffer before `b_k` — a serial-correlation guard (AFML ch. 7's embargo, adapted: in a shuffled-k-fold framing embargo drops train rows adjacent to the test fold; in this strictly-chronological walk-forward the analog is pre-boundary proximity). Rationale to document: with a 96-bar barrier, purge already removes every overlapping label; embargo only guards regime continuity, costs train depth on a tiny store, and is worth revisiting after deep backfill.

Apply the identical rule at every calibration fold boundary. Also note the test side is safe as-is: labels are assigned to windows by ENTRY time (Phase 3 contract); a test-window label whose 24h barrier runs past `test_end` slightly dilutes window isolation but leaks nothing into training.

### Pattern 5: Tiny-window preflight contract (single-class / starvation windows)

**What:** Per walk-forward window, before any fit: `n_decided = (outcome ∈ {WIN, LOSS})` in the purged train slice; require `n_decided >= ml_min_train_labels` (config, suggested default 30) AND both classes present AND each calibration fold's test block contains both classes. On failure: skip the window, record `{window_id, status: "skipped", reason}` in the eval report — never raise, never fabricate a model. Windows that skip contribute NO ML scores; the heuristic bootstrap covers their test spans (Pattern 6). Mirrors the Phase 3 zero-label contract (empty = supported state, never an error).

**Why mandatory:** `sklearn` raises `ValueError` on single-class `y` and LightGBM cannot train binary on one class; with 7–10 days of M15 history this is the EXPECTED path, not an edge case. The same preflight guards `roc_auc_score`/`log_loss` on single-class test sets (record `nan`, skip metric — log_loss needs `labels=[0,1]` to avoid raising on one-class test sets).

### Pattern 6: Heuristic-score bootstrap for unlabeled periods (flagged non-ML)

**What:** A deterministic pure function `heuristic_score(features: dict) -> float` in `[0, 1]` over the same feature vector — e.g., a fixed logistic of hand-weighted, signed contributors: HTF bias agreement count (0/1/2), `rr_at_decision` (normalized), zone position (`zone_position` toward the favorable side), sweep recency (fresher = higher), inverse ATR regime term. Weights are code constants, documented, and versioned with `feature_list_version`. Rows scored by it carry `score_source="heuristic"` in `ml_scores.parquet`; ML-scored rows carry `score_source="ml"`. The heuristic NEVER enters ML headline metrics (AUC/log-loss/Brier/reliability) and is visually separable in Phase 5/6 evidence.

**When to use:** test spans of skipped windows, periods before the first trainable window, and any candidate row without a model artifact. This is what makes AI-02's "each candidate setup receives an ML probability score" deliverable on thin data — the score exists everywhere, the *source* is always labeled.

### Pattern 7: Versioned artifact bundle + loadable scorer (SC4)

**What:** One joblib bundle per artifact version under `data/models/pooled/v{N}/`:

- `model.joblib` — `{artifact_schema_version, feature_names (ordered), categorical_specs: {name: [categories]}, feature_list_version, model: fitted CalibratedClassifierCV, method, cv_fold_summary, seeds, config_hash, training_window: {start, end}, label_counts: {decided, wins, losses, timeouts_purged...}, sklearn_version, lightgbm_version, created_at}`
- `manifest.json` — same metadata, no pickle (human-readable, greppable), plus reliability summary
- `LATEST.json` at `data/models/` — pointer `{artifact_version, path, config_hash}` for Phase 6's loader convenience

**Loader contract:** `ml.scorer.load_scorer(path)` validates `artifact_schema_version` (raise on mismatch naming expected vs found), validates the installed `sklearn`/`lightgbm` versions against the recorded ones (warn-or-refuse per config; refuse on major mismatch), restores `pd.CategoricalDtype(categories=..., )` for every categorical column before `predict_proba` (verified necessity: category alignment is dtype-based — the smoke shows single-row scoring works only when categories are restored; unseen categories become missing values, which LightGBM handles), and returns a `Scorer` with:

```python
scorer.score(features: pd.DataFrame) -> pd.DataFrame  # p_win, score_source="ml"
scorer.contributors(features: pd.DataFrame) -> pd.DataFrame  # per-row per-feature
# contributors from booster.predict(X, pred_contrib=True): last column = bias,
# others map 1:1 to feature_names (verified in the runtime smoke)
```

**Determinism discipline deviation (documented):** Phase 3 pins byte-identical label/report artifacts. Model bundles are NOT held to byte-determinism (pickle framing may vary); determinism is pinned at the **probability level** — retraining with the same inputs/seeds reproduces identical `predict_proba` output (verified) — and at the **manifest level** (same config hash → same metadata). Eval reports remain byte-deterministic under the Phase 3 discipline.

### Anti-Patterns to Avoid

- **Using the label's `rr` (fill-based) as a feature:** it embeds the next bar's open (D-04) — a genuine post-decision-bar leak that survives casual review. Recompute at decision close; pin with a named test.
- **`CalibratedClassifierCV` with default `cv`:** silently `StratifiedKFold` on time-ordered rows — the exact "shuffled splits anywhere" violation SC3 forbids, and invisible in results.
- **`ensemble=False`:** verified to raise on expanding folds (`cross_val_predict only works for partitions`); even when forced into a partition it changes the model used at inference. Use `ensemble=True` with explicit folds.
- **`is_unbalance` / `scale_pos_weight`:** LightGBM docs (verified): these "will negatively affect the accuracy of individual class probability estimates" — the exact quantity this phase exists to produce. With R:R ≥ 1 decided trades, imbalance is mild; calibration handles the residual mapping. Keep the knobs out of v1 defaults.
- **Isotonic on tiny data:** overfits ≪1000 samples (official guidance); keep as a post-backfill option, not the default.
- **One-hot encoding symbol/direction:** LightGBM's native categorical splits are better and simpler; one-hot also breaks the "categorical features" wording of D-03.
- **Training on TIMEOUT rows or folding them into calibration:** D-01/D-02 — they are scored-and-flagged, never fit against.
- **Skipping the purge:** Phase 3 deliberately left `train_mask` un-purged with the obligation documented in `walkforward.py`'s module docstring — Phase 4 owns it now.
- **Storing artifacts non-atomically or with a second write path:** reuse the tmp + `os.replace` helpers pattern from `backtest/reports.py`.
- **Silent model/score drift between windows:** every eval row records `artifact_version` + `score_source`; a score without provenance is a bug.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Gradient-boosted trees | Custom boosting / logistic baseline "for now" | `lightgbm.LGBMClassifier` | AI-02 names a gradient-boosted model; native categoricals + NaN handling + determinism params; verified on env |
| Probability calibration | Manual Platt/isotonic on OOF scores | `sklearn.calibration.CalibratedClassifierCV` | Cross-fitting, fold plumbing, method switching, predict-time averaging are all owned by the class; SC2 names it |
| Reliability curves | Manual binning one-off | `sklearn.calibration.calibration_curve` | Verified edge handling (quantile strategy, dup edges); arrays are the SC2 artifact |
| Metrics | Hand-written AUC/log-loss/Brier | `sklearn.metrics.roc_auc_score / log_loss / brier_score_loss` | Standard implementations; `log_loss(labels=[0,1])` guards one-class test sets |
| Walk-forward splits | Any new splitter | `backtest.walkforward.build_windows` | Verified chronological/overlap/expanding invariants carry into ML (SC3); purge is a mask, not a splitter |
| Prefit-style calibration glue | Manual "fit here, calibrate there" bookkeeping | `sklearn.frozen.FrozenEstimator` (when a disjoint-slice calibration is chosen) | The supported API for calibrating an already-fitted model (verified); manual paths forget the disjointness invariant |
| Per-row feature attributions | SHAP package | LightGBM `booster.predict(X, pred_contrib=True)` | Native TreeSHAP-equivalent output (verified: shape (n, n_features+1), last col bias); zero new dependencies |
| Serialization | Custom pickle protocols / JSON model dumps | `joblib.dump/load` + JSON manifest | joblib ships with sklearn; verified roundtrip of the calibrator; manifest keeps humans in the loop (project core value) |

**Key insight:** everything ML-specific that is genuinely hard (cross-fitted calibration, deterministic GBDT, categorical handling, attribution) is already owned by the locked libraries — the phase's actual engineering weight is in the point-in-time feature discipline and the audit that proves it, which are Phase 2/3 patterns extended, not new machinery.

## Common Pitfalls

### Pitfall 1: The fill-open `rr` leak (feature-side D-04 trap)
**What goes wrong:** features read the label frame's `rr`, `entry_price`, or `sl/tp` context computed at the fill — importing bar S+1's open into a decision-time feature.
**Why it happens:** the label frame is the most convenient training table and looks decision-adjacent.
**How to avoid:** features recompute R:R and distances at the decision close (`compute_rr(direction, decision_close, sl, tp)`); the audit's L3 forbidden-column list includes `rr`, `entry_price`, `exit_*`, `r_*`, `outcome`; L1 prefix-equivalence would also catch it (truncated histories change the fill open).
**Warning signs:** feature-importance mass concentrating on `rr` vs the recomputed variant differing; audit `max_abs_diff` > 0.

### Pitfall 2: Silent `StratifiedKFold` inside calibration
**What goes wrong:** `CalibratedClassifierCV(..., cv=5)` or `cv=None` on time-ordered rows — class-stratified round-robin folds mix future into training of fold models.
**Why it happens:** it is the documented default and works without error.
**How to avoid:** ALWAYS pass an explicit `cv` iterable derived from `build_windows`; named test asserts the folds are chronologically expanding and that omitting them at the call site is impossible (wrap calibration in a project function that requires the folds argument).
**Warning signs:** calibration metrics look "too good"; fold summaries in the manifest show interleaved index ranges.

### Pitfall 3: `ensemble=False` partition failure
**What goes wrong:** choosing `ensemble=False` for simplicity raises `ValueError: cross_val_predict only works for partitions` on expanding folds (verified this session).
**Why it happens:** `ensemble=False` uses `cross_val_predict`, which demands every sample be in exactly one test fold — impossible under pure expanding-train chronology.
**How to avoid:** use `ensemble=True` (per-fold calibrated classifiers, averaged); document the constraint in `train.py`'s docstring.
**Warning signs:** the exact ValueError during fit.

### Pitfall 4: Isotonic on small calibration sets
**What goes wrong:** step-function calibration that memorizes noise → probability plateaus, degenerate 0/1 outputs.
**Why it happens:** official guidance — isotonic needs ≫ samples than available ("not recommended ≪1000").
**How to avoid:** `method="sigmoid"` default; `ml_calibration_method` knob; revisit isotonic only after deep backfill with documented evidence.
**Warning signs:** reliability curve is a staircase with huge empty bins; test-window log loss spikes.

### Pitfall 5: Imbalance flags distorting probabilities
**What goes wrong:** `is_unbalance=True` or `scale_pos_weight=n_neg/n_pos` shifts the model's output distribution; predicted probabilities are no longer meaningful before (and only partly after) calibration.
**Why it happens:** the flags reweight gradients to favor the minority class — LightGBM's own docs warn they damage probability estimates.
**How to avoid:** leave both unset in v1; imbalance among decided trades at R:R ≥ 1 is mild; calibration handles residual mapping; keep knobs in config for later experimentation with recorded evidence.
**Warning signs:** raw model probabilities clustered near the base rate BEFORE calibration but far after; sensitivity of P(WIN) to the flag value.

### Pitfall 6: Single-class / starvation window crash
**What goes wrong:** `ValueError` from sklearn (one class in `y`) or LightGBM on a train window; `roc_auc_score`/`log_loss` raising on one-class test sets.
**Why it happens:** 7–10 days of M15 history cannot populate every window with both classes — this is the expected regime today.
**How to avoid:** Pattern 5 preflight (skip + record), `log_loss(..., labels=[0,1])`, `nan`-with-reason for skipped metrics — mirroring `stats.py`'s nan-propagation contract.
**Warning signs:** training CLI exits 1 with a traceback instead of a recorded skip.

### Pitfall 7: Category dtype lost at the scorer boundary
**What goes wrong:** Phase 6 builds a features frame with `symbol` as plain `StringDtype`/object; LightGBM then treats the column differently than in training (or errors), silently changing scores.
**Why it happens:** LightGBM aligns categories via pandas categorical dtypes; a fresh frame doesn't know the training categories.
**How to avoid:** `categorical_specs` (name → ordered categories) stored in the artifact; `scorer` restores `pd.CategoricalDtype` before `predict_proba` (verified necessary in the smoke); unseen categories become missing (documented LightGBM behavior) — log when it happens.
**Warning signs:** scorer scores differ between identical feature dicts built by different callers.

### Pitfall 8: Purge omission at window boundaries (OQ5)
**What goes wrong:** train labels whose outcome resolves inside the test window leak test-period price information into training — optimistic in-window metrics.
**Why it happens:** Phase 3's `train_mask` (`entry_time < test_start`) is deliberately un-purged; the obligation lives in the module docstring.
**How to avoid:** Pattern 4 purge (`exit_time >= test_start` dropped) applied to train masks AND calibration fold trains; boundary tests pinned both sides of `exit_time == test_start`.
**Warning signs:** first-window train count unchanged after purge wiring; in-window AUC dramatically above adjacent windows.

### Pitfall 9: pandas 3 dtype interactions with sklearn
**What goes wrong:** older sklearn silently accepts pandas 3 StringDtype numeric-looking columns (the 1.9 whats-new fix) or CoW surprises mutate frames mid-pipeline.
**Why it happens:** pandas 3 changed string columns to StringDtype; pre-1.9 sklearn validation has known gaps.
**How to avoid:** pin `scikit-learn>=1.9` in pyproject; feature builder never mutates inputs (project convention) and pins dtypes like Phase 2/3 frames do.
**Warning signs:** `check_array` accepting string columns in tests; dtype drift between build and score paths.

### Pitfall 10: Artifact/schema drift between training and scoring
**What goes wrong:** Phase 6 loads a model trained under `feature_list_version=1` with a feature builder emitting v2 columns — silent garbage or KeyError.
**Why it happens:** features evolve; artifacts persist.
**How to avoid:** `artifact_schema_version` + `feature_list_version` in the bundle; loader validates against the importing module's current constants and refuses mismatches with actionable messages (Phase 3 gate-message style).
**Warning signs:** loader tests pass only when versions align; no negative-path test exists.

### Pitfall 11: Non-deterministic training breaking reproducibility evidence
**What goes wrong:** retraining produces different probabilities → walk-forward evidence irreproducible, A/B comparisons meaningless.
**Why it happens:** multi-thread histogram nondeterminism; unfixed seeds; dart boosting.
**How to avoid:** `deterministic=True`, `force_row_wise=True`, `num_threads=1`, fixed `random_state`, `boosting=gbdt` (verified byte-identical retrain in the smoke); record all seeds in the manifest.
**Warning signs:** two identical CLI runs producing different `predict_proba` on the same artifact inputs.

### Pitfall 12: TIMEOUT contamination of headline metrics
**What goes wrong:** AUC/Brier/reliability computed over all rows (TIMEOUTs included) — metric semantics drift from D-01's decided-trade dashboard meaning.
**Why it happens:** TIMEOUT rows carry scores (D-02) and sit in the same frame.
**How to avoid:** headline metrics computed on `outcome ∈ {WIN, LOSS}` only; TIMEOUT rows emitted flagged `excluded` with their scores in `ml_scores.parquet`; named test pins the split.
**Warning signs:** eval report lacks an `n_timeout_flagged` column; win-rate analog disagrees with Phase 3 stats on the same labels.

## Code Examples

Verified patterns (runtime smoke this session unless otherwise noted):

### 1. Deterministic LightGBM fit with native categoricals
```python
# Source: LightGBM stable docs (Parameters: deterministic/force_row_wise/seed)
# [CITED: lightgbm.readthedocs.io/en/stable/Parameters.html]; runtime-verified
params = dict(
    objective="binary", n_estimators=200, num_leaves=7, min_data_in_leaf=5,
    learning_rate=0.1, random_state=42,
    deterministic=True, force_row_wise=True, num_threads=1, verbose=-1,
)
model = lgb.LGBMClassifier(**params)
model.fit(X_train, y_train)  # X: pandas DataFrame; symbol/timeframe/direction
                             # columns are pd.category dtype (auto-detected)
```

### 2. Chronological calibration folds from the Phase 3 harness
```python
# Source: backtest/walkforward.build_windows (verified splitter of record) +
# sklearn docs: cv accepts "an iterable yielding (train, test) splits"
# [CITED: scikit-learn.org/stable CalibratedClassifierCV]
from ai_trading.backtest.walkforward import build_windows

def calibration_folds(entry_times: pd.Series, test_days: int, train_days: int,
                      purge: "PurgeSpec") -> list[tuple[list[int], list[int]]]:
    """Expanding-train / sequential-test folds over the TRAINING window,
    purge applied at every boundary. ensemble=True (never False)."""
    windows = build_windows(entry_times, test_days=test_days, train_days=train_days)
    folds = []
    for w in windows:
        train_idx = purge.apply(w.train_mask)   # drop exit_time >= w.test_start (+embargo)
        test_idx = w.test_mask.to_numpy().nonzero()[0]
        if len(train_idx) and len(test_idx):
            folds.append((train_idx.tolist(), test_idx.tolist()))
    return folds

calibrated = sklearn.calibration.CalibratedClassifierCV(
    estimator=lgb.LGBMClassifier(**params),
    method="sigmoid",        # Platt — isotonic overfits <~1000 calibration samples
    cv=calibration_folds(train_entries, cfg.ml_cal_test_days, cfg.ml_cal_train_days, purge),
    ensemble=True,           # False raises: cross_val_predict requires partitions
).fit(X_train_decided, y_train_decided)  # decided rows only (D-01)
```

### 3. Reliability data retention (SC2)
```python
# Source: scikit-learn calibration module docs — calibration_curve returns the
# per-bin fraction of positives and mean predicted probability
# [CITED: scikit-learn.org/stable/modules/calibration.html]; runtime-verified
p = calibrated.predict_proba(X_decided)[:, 1]
prob_true, prob_pred = sklearn.calibration.calibration_curve(
    y_decided, p, n_bins=5, strategy="quantile"
)
reliability = pd.DataFrame({"bin": range(len(prob_true)),
                            "prob_pred": prob_pred, "prob_true": prob_true,
                            "n": bin_counts})
# → data/reports/ml_reliability.parquet (atomic write) + manifest summary
```

### 4. Artifact bundle save/load with schema validation
```python
# Source: project pattern (reports._atomic_* discipline) + sklearn FrozenEstimator
# docs for prefit-style calibration [CITED: scikit-learn.org/stable]
bundle = {
    "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,   # e.g. 1
    "feature_list_version": cfg.ml_feature_list_version,
    "feature_names": list(FEATURE_SPEC.names),
    "categorical_specs": {name: list(categories) for categoricals},
    "model": calibrated,          # fitted CalibratedClassifierCV (joblib-picklable)
    "method": "sigmoid", "seeds": params["random_state"],
    "config_hash": cfg_hash, "sklearn_version": sklearn.__version__,
    "lightgbm_version": lgb.__version__, "created_at_utc": now_iso,
}
# write: tmp + os.replace under data/models/pooled/v{N}/model.joblib (+ manifest.json, LATEST.json)

scorer = load_scorer(path)   # validates schema + library versions, restores categories
scores = scorer.score(features_frame)        # p_win per row, score_source="ml"
contrib = scorer.contributors(features_frame)  # booster.predict(X, pred_contrib=True)
                                               # columns = feature_names + [bias]
```

### 5. Per-window evaluation with decided-only headline + flagged TIMEOUTs
```python
# Source: D-01/D-02 semantics over the Phase 3 window contract; metric guards per
# sklearn docs (log_loss labels param) [CITED: scikit-learn.org/stable]
decided = test_rows[test_rows["outcome"].isin(["WIN", "LOSS"])]
timeout = test_rows[test_rows["outcome"] == "TIMEOUT"]           # scored, flagged
p_dec = calibrated.predict_proba(X_dec)[:, 1]
row = {
    "window_id": w.window_id, "n_decided": len(decided),
    "n_timeout_flagged": len(timeout),
    "auc": roc_auc_score(y_dec, p_dec) if y_dec.nunique() == 2 else float("nan"),
    "log_loss": log_loss(y_dec, p_dec, labels=[0, 1]),
    "brier": brier_score_loss(y_dec, p_dec),
    "calibration_status": "ok",
}
# skipped windows record {status: "skipped", reason}; heuristic covers their spans
```

### 6. Feature audit L1 (prefix equivalence, the repaint pattern extended)
```python
# Source: tests/unit/test_replay_repaint.py + assert_point_in_time_prefix_equality
# pattern (Phase 2/3 verified convention)
full = build_feature_frame(labels, chain_full, bars_full)
for k in prefix_points:                       # 1-by-1 and chunked appends
    part = build_feature_frame(labels, chain_prefix(k), bars_full.iloc[:k])
    closed = full[full["decision_close_time"] <= prefix_close_time(k)]
    pd.testing.assert_frame_equal(part.sort_index(), closed.sort_index(),
                                  check_exact=True)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `CalibratedClassifierCV(cv="prefit")` | `CalibratedClassifierCV(FrozenEstimator(model))` | prefit deprecated 1.6, removed later | Any prefit-style calibration must use `FrozenEstimator` (verified import `sklearn.frozen.FrozenEstimator`); the old string raises |
| `ensemble=True/False` implicit | `ensemble="auto"` default (False only for frozen estimators) | sklearn 1.6 | Explicit `ensemble=True` + explicit folds is the deterministic chronological shape |
| Isotonic default assumption for "better calibration" | Method chosen by sample count: sigmoid ≪1000 samples | Long-standing official guidance | v1 = sigmoid; isotonic reserved for post-backfill |
| `temperature` scaling absent | `method="temperature"` available | sklearn 1.8 | Not applicable (binary, tiny data) — noted for completeness |
| sklearn/pandas 3 friction | sklearn 1.9 ships pandas 3 StringDtype fixes | 1.9.0 (2026-06-02) | Pin `scikit-learn>=1.9` |
| LightGBM nondeterministic histograms | `deterministic=true` + `force_row_wise/col_wise` + fixed threads | LightGBM 4.x | Byte-identical retrain verified |
| SHAP dependency for contributors | LightGBM native `pred_contrib=True` | available ≥ 3.x, verified on 4.7.0 | Per-row contributors with zero new dependencies |

**Deprecated/outdated:**
- `cv="prefit"`: removed — use `FrozenEstimator`.
- One-hot encoding for GBDT categoricals: native categorical splits are the supported path.
- `is_unbalance`/`scale_pos_weight` for probability models: documented probability distortion.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Embargo default of 0 (purge-only) is acceptable; embargo knob semantics = drop train labels whose exit closes within N bars before `test_start` | Pattern 4, config | Serial-correlation leakage slightly inflates in-window metrics; mitigatable by raising the knob — convention choice, reversible via config |
| A2 | Decided-trade counts on the current store are plausibly single digits to ~20 total (estimate from 7–10 days × candidate frequency), NOT a measured count — no labels exist on disk yet | Summary, Environment | If actually higher, the label-count gate thresholds would still hold (gate is config-driven); if lower, pipeline-first is even more clearly the right path |
| A3 | `ml_min_train_labels` suggested default 30 decided labels (per training window) is a reasonable gate | Pattern 5 | Too high delays first real training after backfill; too low admits noise — planner/user should confirm the number |
| A4 | Heuristic score design (logistic of hand-weighted feature contributors) is acceptable for the bootstrap; exact weights are planner discretion | Pattern 6 | A poorly-shaped heuristic could mislead Phase 5/6 displays; mitigated by `score_source` flagging and determinism/tests |
| A5 | Artifact versioning scheme (`data/models/pooled/v{N}/` + `LATEST.json` + schema/version validation) matches Phase 6 loader expectations | Pattern 7 | Phase 6 would need a loader shim; low risk since the same repo owns both |
| A6 | Contributors from `pred_contrib` (raw-model logit space) are acceptable as "ML score contributors" for the evidence object, with the calibrated P(WIN) as headline | Pattern 7 | Attribution/probability scale mismatch could confuse evidence consumers; documented in the artifact manifest |
| A7 | Session/time-of-day features keyed on `time_utc` (UTC hour) — not broker-local time — are the right session encoding | Pattern 1 feature list | If sessions matter via broker-local hours, feature utility drops; DST caveat noted; feature list is versioned so changeable without breaking artifacts |
| A8 | `sklearn.calibration.calibration_curve` remains the reliability-data API in the pinned 1.9 line (verified in smoke); `CalibrationDisplay` is plot-only | Pattern 3 | Trivial rename/migration risk; would surface immediately in tests |

## Open Questions (RESOLVED)

1. **When can a REAL training run happen?**
   - What we know: pipeline can be fully proven on synthetic data now; `data/labels/` doesn't exist; M15 store is 7–10 days; Phase 3 UAT deferral makes backfill a human data task (MT5 terminal required).
   - What's unclear: whether the user will backfill (and to what depth) before, during, or after Phase 4 execution.
   - Recommendation: plan 04-02/04-03 gate real training behind the label-count gate and document the backfill command path; the phase succeeds on synthetic + harness evidence regardless (matches SC wording and the deferred-items framing).
   - **RESOLVED:** Adopted — the preflight skip-with-reason contract lives in 04-02 Task 2 (starvation never fabricates a model), and the label-count gate with the actionable backtest-plus-backfill remedy plus the synthetic-first end-to-end CLI proof live in 04-03 Task 3; the phase succeeds on synthetic + harness evidence.

2. **Calibration fold sizing on thin data (post-backfill tuning)?**
   - What we know: folds derive from `build_windows` (day-based, e.g., 2d test blocks on tiny stores); sigmoid needs both classes per fold.
   - What's unclear: optimal fold granularity once real history exists (bars vs days vs count-based blocks).
   - Recommendation: keep day-based (harness-native) with config knobs; revisit with real data; document the constraint that folds must remain expanding + purged.
   - **RESOLVED:** Adopted — 04-02 Task 1 (`calibration_folds`) derives folds exclusively from `build_windows` with day-based config knobs (`ml_cal_train_days`/`ml_cal_test_days`/`ml_embargo_bars`), expanding + purged; granularity is revisited only after deep backfill.

3. **Heuristic acceptance criteria?**
   - What we know: deterministic, [0,1], flagged; weighted contributors mirror feature semantics.
   - What's unclear: how "good" it must be to be useful downstream (Phase 5 agreement flags will consume it).
   - Recommendation: pin determinism + range + flag tests now; defer quality criteria to Phase 5/6 feedback; record `score_source` everywhere so impact is auditable.
   - **RESOLVED:** Adopted — 04-03 Task 1 pins determinism, [0,1] range, missing-safety, and spec-keyed tests; quality criteria deferred to Phase 5/6 feedback with `score_source`/`provenance` recorded on every score row (04-03 Task 2).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| uv | dependency add + test runs | ✓ | 0.11.28 (Phase 3 verified) | — |
| Python 3.12 | runtime | ✓ | 3.12.12 | — |
| pandas 3.0.5 / numpy 2.5.2 / pyarrow 25.0.1 | features/artifacts | ✓ (verified on disk this session) | as listed | — |
| lightgbm | training | ✗ (not installed yet — install is a Wave 0 task) | 4.7.0 verified installable | none — blocks AI-02 |
| scikit-learn | calibration/metrics | ✗ (not installed yet — same task) | 1.9.0 verified installable | none — blocks AI-03 |
| MT5 terminal (running, logged in) | history backfill for real training (DATA-04 path) | human data task (Phase 3 UAT deferral) | — | pipeline-first on synthetic; heuristic bootstrap covers unlabeled spans |
| Disk I/O for artifacts | data/models/, data/reports/ | ✓ | trivial size | — |

**Missing dependencies with no fallback:** none blocking (lightgbm/scikit-learn install is a normal `uv add` task; network was exercised successfully this session via the throwaway smoke).
**Missing dependencies with fallback:** MT5 terminal for real-data training — the fallback IS the research recommendation (pipeline-first + label gate + heuristic bootstrap).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.x (dev group, installed), markers `unit` (default) / `mt5` (deselected by addopts) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (testpaths=tests, `-m "not mt5"`) |
| Quick run command | `uv run pytest tests/unit -q` (358 currently green; must stay green) |
| Full suite command | `uv run pytest -q` (+ ruff `uv run ruff check .`) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| AI-01 | Features point-in-time; audit confirms | unit | `uv run pytest tests/unit/test_ml_feature_audit.py tests/unit/test_ml_features.py -q` | ❌ Wave 0 |
| AI-02 | Every candidate row scored (ML or flagged heuristic) | unit | `uv run pytest tests/unit/test_ml_scorer.py tests/unit/test_ml_heuristic.py -q` | ❌ Wave 0 |
| AI-03 | Calibrated probabilities + reliability recorded | unit | `uv run pytest tests/unit/test_ml_train.py -q` | ❌ Wave 0 |
| AI-04 | Walk-forward only; purge; no shuffled CV anywhere (incl. calibration) | unit | `uv run pytest tests/unit/test_ml_folds.py tests/unit/test_ml_purge.py tests/unit/test_ml_evaluate.py -q` | ❌ Wave 0 |
| SC4 | Artifact versioned + loadable | unit | `uv run pytest tests/unit/test_ml_artifact.py -q` | ❌ Wave 0 |
| (all) | Suite-wide regression guard | unit | `uv run pytest tests/unit -q` | ✅ |

All ML unit tests are MT5-free and run on synthetic fixtures (`make_bars` → replay → labels, or hand-built label frames via `_backtest_fixtures` helpers). Tiny training runs (n≈100 rows, 40 trees) keep each module well under the 30s sampling budget — verified equivalent workloads complete in ~2s in the smoke.

### Sampling Rate
- **Per task commit:** `uv run pytest tests/unit -q` (new ML modules included)
- **Per wave merge:** `uv run pytest -q && uv run ruff check .`
- **Phase gate:** full suite green before `/gsd-verify-work`; vendor-purity extension (no MetaTrader5 import under `src/ai_trading/ml/`) mirrors the Phase 2/3 assertion.

### Wave 0 Gaps
- [ ] `uv add lightgbm scikit-learn` (+ verify `import lightgbm, sklearn, joblib` prints 4.7.0 / 1.9.0 / 1.6.x)
- [ ] `tests/unit/test_ml_features.py`, `test_ml_feature_audit.py`, `test_ml_purge.py`, `test_ml_folds.py`, `test_ml_train.py`, `test_ml_artifact.py`, `test_ml_scorer.py`, `test_ml_evaluate.py`, `test_ml_heuristic.py` — per the map above
- [ ] `tests/unit/_ml_fixtures.py` (local helper, direct-import convention): synthetic labels frame builder + tiny feature frame builder over `make_bars` world
- [ ] Config keys section in `config.toml` + frozen `Config` extension with fail-fast validation (`ml_feature_list_version`, `ml_calibration_method`, `ml_embargo_bars`, `ml_min_train_labels`, `ml_cal_train_days`, `ml_cal_test_days`, lgbm hyperparams incl. `ml_random_state`, `ml_n_estimators`, `ml_num_leaves`, `ml_min_data_in_leaf`, `ml_learning_rate`, retrain-schedule keys)

## Security Domain

### Applicable ASVS Categories (Level 1, enforcement enabled)

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | No auth surface — local batch/CLI phase; Phase 6 dashboard handles access |
| V3 Session Management | no | No sessions in this phase |
| V4 Access Control | no | No multi-user surface; artifacts under project `data/` |
| V5 Input Validation | **yes** | All inputs are config + internal artifacts: frozen `Config` fail-fast validation (established pattern) extended to `ml_*` keys; label/feature frames validated by schema-checking entry points (missing-column refusals naming the columns, `walkforward`/`stats` precedent); loader validates artifact schema/library versions before unpickling |
| V6 Cryptography | no | No secrets, keys, or crypto in this phase |
| V7 Errors/Logging | **yes** | Refusals carry actionable messages without leaking config contents (Config never repr'd — credential hygiene rule carries forward); no PII in artifacts |
| V8 Data Protection | **yes** (light) | Model artifacts are self-generated pickle bundles — never accept third-party joblib files (documented loader contract; version validation is the integrity gate); artifacts written atomically to project-controlled paths |
| V14 Configuration | **yes** | `ml_*` keys validated fail-fast at load (typo → refusal); scheduled-retrain keys validated (positive ints, method in {sigmoid, isotonic}) |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Pickle-deserialization of untrusted model artifacts | Tampering/Elevation | Loader validates `artifact_schema_version` + library versions; project contract: artifacts only from this repo's own training runs (documented in `artifact.py` docstring) |
| Lookahead leakage corrupting evidence (the project's core trust risk) | Repudiation (evidence integrity) | Three-layer feature audit (SC1) + purge tests + no-shuffle fold tests; audit artifact persisted per training run |
| Silent metric contamination (TIMEOUT in headline) | Repudiation | D-01/D-02 decided-only headline + flagged scores; named tests |
| Config typo silently changing training semantics | Tampering | Frozen Config fail-fast (`_REQUIRED_KEYS` extension + `_validate` rules) |
| Non-deterministic training faking reproducibility | Repudiation | Determinism params pinned + retrain-identical test + seeds in manifest |

## Sources

### Primary (HIGH confidence)
- Runtime smoke this session (throwaway uv env on Python 3.12.12 / pandas 3.0.5 / numpy 2.5.2): lightgbm 4.7.0 + scikit-learn 1.9.0 install, chronological-fold calibration (`ensemble=True`), `ensemble=False` partition ValueError, `FrozenEstimator` prefit path, `calibration_curve` reliability arrays, category-dtype alignment + single-row scoring, determinism (byte-identical retrain), joblib roundtrip, `pred_contrib` attribution shape
- Context7 `/websites/scikit-learn_stable` — CalibratedClassifierCV API (cv iterable, ensemble, method guidance incl. isotonic ≪1000 warning, temperature in 1.8), FrozenEstimator pattern
- Context7 `/websites/lightgbm_readthedocs_io_en_stable` — determinism/force_row_wise/seed guidance; `is_unbalance` probability-distortion warning; pandas-category categorical handling; unseen categories → missing
- In-repo verified code: `backtest/{asof,candidates,replay,walkforward,stats,barriers}.py`, `detectors/mtf.py`, `config.py` — contracts read directly this session

### Secondary (MEDIUM confidence)
- scikit-learn.org v1.9 whats-new — pandas 3 StringDtype `check_array` fix (fetched and read)
- scikit-learn.org calibration module — `calibration_curve`/`CalibrationDisplay` semantics (fetched)
- PyPI JSON API — lightgbm 4.7.0 (2026-07-18), scikit-learn 1.9.0 (2026-06-02) versions/dates/requires-python/project_urls
- SearXNG corroboration of purge/embargo semantics (AFML ch. 7 adaptations; eslazarev/purged-cross-validation description matches the adapted semantics used here)

### Tertiary (LOW confidence)
- Decided-trade count estimate on current store (A2) — inference from bar counts, not a measured replay run
- Embargo-default and gate-threshold conventions (A1/A3) — standard-practice reasoning, user-confirmable knobs

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versions verified against PyPI + runtime smoke on the exact project environment; pandas 3 compat confirmed by sklearn 1.9 whats-new and by the smoke itself
- Architecture: HIGH — every integration point grounded in read source (asof/candidates/walkforward/replay/stats contracts verified this session); calibration mechanics verified by execution
- Pitfalls: HIGH for API traps (2, 3, 5, 6, 7 — verified by smoke/docs), MEDIUM for data-dependent severities (1, 8 depend on real label counts)

**Research date:** 2026-09-02
**Valid until:** ~2026-10-02 (stable, pinned stack; re-verify PyPI pins if >30 days elapse)
