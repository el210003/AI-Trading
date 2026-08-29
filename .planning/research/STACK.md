# Stack Research

**Domain:** AI-assisted forex trading system (SMC detection, hybrid ML + LLM scoring, MT5 data feed, signals-only v1)
**Researched:** 2026-08-29
**Confidence:** HIGH for core stack (versions verified live from PyPI/official vendor docs on research date); MEDIUM for backtesting-approach and dashboard tradeoffs (domain judgment, not vendor-verifiable)

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.12.x | Runtime | Verified sweet spot: `metatrader5` ships cp36–cp314 win_amd64 wheels (cp312 confirmed), LightGBM/sklearn/pandas all fully mature on 3.12. Use 3.12, not 3.14 — newest CPython still has wheel gaps in the data ecosystem. 64-bit required (MetaTrader5 has no 32-bit wheel). |
| MetaTrader5 (`metatrader5`) | 5.0.6147 | MT5 terminal data feed | Official MetaQuotes package (MIT, released Aug 27 2026, actively updated ~monthly). Windows-only win_amd64 — matches the project's Windows constraint. Talks IPC directly to the local terminal; `initialize()` / `copy_rates_from_pos()` / `copy_rates_range()` are the data path. |
| pandas | 2.3.3 | SMC detection core + dataframes | `copy_rates_*` already returns a numpy structured array (`time, open, high, low, close, tick_volume, spread, real_volume`) → zero-copy into pandas. Swing points, equal-high/low clustering, premium/discount zones and sweeps are all expressible as vectorized rolling/groupby ops. Pure pandas/numpy gives full control over confirmation-shifted (non-repainting) logic — critical for ML features and honest backtests. |
| numpy | 2.2.6 | Array math (under pandas) | Same reason; current 2.x line is supported by every recommended lib below. |
| LightGBM | 4.7.0 | ML setup-probability scorer | Best default GBM for tabular financial features: fastest training on modest data (3 symbols × 3 TFs of M15 bars ≈ small tables), native NaN handling, `scale_pos_weight` for imbalanced setup labels, sklearn API (`LGBMClassifier.predict_proba`), `lgb.early_stopping()` callback verified current. CPU-only is plenty; no CUDA build needed on Windows. |
| scikit-learn | 1.7.2 | Calibration, metrics, pipelines | `CalibratedClassifierCV` (isotonic/Platt) to turn raw boosting scores into honest probabilities for the dashboard; PR-AUC/Brier metrics; `Pipeline` for train/serve parity. |
| Anthropic SDK (`anthropic`) | 1.2.0 | LLM narrative reasoning (recommended provider) | Structured JSON via tool-use with strict schemas; strong long-context reasoning over annotated multi-timeframe market context. Wrap behind a thin provider interface so ML and LLM stay independently testable (project constraint). |
| OpenAI SDK (`openai`) | 3.6.0 | Alternative LLM provider | `client.chat.completions.parse()` with Pydantic models (verified current pattern) gives schema-enforced structured output. Keep both SDKs behind one interface; pick per cost/quality at runtime. |
| Streamlit | 1.62.0 | Web dashboard (v1) | Single-user, localhost, read-only presentation of setups (direction, entry, SL, TP, probability, rationale + plotly charts). Fastest path to a trustworthy tool; no separate frontend codebase to maintain while the real risk lives in detection/ML/backtest. Native `st.plotly_chart`, auto-refresh for new setups. |
| APScheduler | 3.11.3 | Task scheduling | Cron-style triggers aligned to M15 bar closes (e.g. every 15 min at +20s) inside one long-running Python "engine" process; `misfire_grace_time`/`coalesce` handle laptop sleep. Pin `<4` — APScheduler 4.x is still pre-release. |
| SQLite (stdlib) + SQLAlchemy | 2.0.52 | Setups/signals/narratives store | Relational, queryable history of setups with ML score, LLM rationale, and outcome labels (needed later as ML training data). Zero-ops, single-file, perfect for one local user. |
| Parquet via pyarrow | 25.0.1 | OHLC bar store | Immutable, partitioned files (e.g. `data/ohlcv/{symbol}/{timeframe}.parquet`) — columnar, compressed, fast bulk reads for backtests and ML training. Bars are append-only; Parquet's write-once model fits exactly and avoids SQLite row-bloat for wide date-range scans. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| DuckDB | 1.5.5 | SQL over Parquet | Optional but cheap: query/aggregate the Parquet bar store with SQL in research notebooks and backtests without loading all of pandas first. |
| Pydantic | 2.13.5 | Setup/feature contracts | One `Setup` model shared by SMC detector, ML scorer, LLM (structured-output schema), and dashboard — enforces the "separable components" constraint at the type level. |
| plotly | 7.0.0 | Candlestick + zone overlays | Chart setups with swing levels, swept liquidity, PD zones in Streamlit. |
| joblib | 1.5.3 | Model persistence | Save LightGBM + calibrator + feature metadata as one artifact. |
| loguru | 0.7.3 | Logging | Rotating file logs for the unattended scheduled engine; cleaner than stdlib logging config. |
| tenacity | 9.1.4 | Retries | Exponential backoff on MT5 IPC hiccups (terminal restarts, weekend disconnects) and LLM API calls. |
| pytest | latest | Testing | SMC detectors and the backtester are pure functions over DataFrames — ideal pytest targets. Non-negotiable for lookahead-bias tests. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| uv | Env + dependency management | Fast venv/lock on Windows; `uv pip install -r requirements.txt` or `uv sync` with `pyproject.toml`. |
| ruff | Lint + format | Single fast tool replacing flake8/black/isort. |
| MT5 terminal (local, logged in) | Data source process | Must run and stay logged in. Raise **Tools → Options → Charts → "Max. bars in chart"** — `copy_rates_*` only returns bars within this chart-history limit (verified in official docs). Enable Algo Trading not needed for data; symbol must be visible in MarketWatch (`symbol_select(sym, True)`). |
| VS Code | IDE | Python + Jupyter extensions for research notebooks. |

## Installation

```bash
# Core
pip install "pandas==2.3.3" "numpy==2.2.6" "metatrader5==5.0.6147"
pip install "lightgbm==4.7.0" "scikit-learn==1.7.2" "joblib==1.5.3"

# LLM layer (both providers behind one interface)
pip install "anthropic==1.2.0" "openai==3.6.0" "pydantic==2.13.5"

# Storage
pip install "pyarrow==25.0.1" "sqlalchemy==2.0.52" "duckdb==1.5.5"

# Dashboard + scheduling + ops
pip install "streamlit==1.62.0" "plotly==7.0.0" "apscheduler==3.11.3,<4"
pip install "loguru==0.7.3" "tenacity==9.1.4"

# Dev
pip install -D pytest ruff uv
```

(`-D` via uv/pip-tools convention; with plain pip use `pip install pytest ruff` in a dev requirements file.)

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| Own pandas/numpy SMC implementation | `smartmoneyconcepts` 0.0.27 (PyPI) | Only as a **cross-check/reference** for your detectors. It covers FVG, swings, BOS/CHoCH, order blocks, liquidity (with swept index), sessions — but it's a 0.0.x project with "Planning" dev-status classifier and an educational disclaimer, and its swing function uses a centered window (`swing_length` bars *before and after*), i.e. it repaints/leaks future bars. Never feed its output into ML features or backtests unshifted. |
| LightGBM | XGBoost 3.2.0 | Near-parity for this tabular problem. Choose XGBoost if you later ensemble or want its hist-tree quirks; LightGBM wins on training speed and NaN defaults here. |
| Custom bar-by-bar backtester (own ~few-hundred-line pandas/numpy engine) | vectorbt 1.0.0 | Use vectorbt (free) only for bulk vectorized sanity screens of simple entry/exit signals (`from_signals` with `sl_stop`/`tp_stop`). SMC setups are *conditional pending-limit orders at zones with fixed SL/TP* — semantics vectorized engines don't express honestly (intrabar SL-vs-TP ambiguity, zone-touch fills, multi-timeframe context). Custom loop gives exact, auditable fill rules. |
| Custom bar-by-bar backtester | backtesting.py 0.6.6 | Not recommended at all for this project: single-instrument, single-timeframe, market-order-next-bar-open semantics — the opposite of zone-limit-order SMC logic; development is largely stale. |
| Streamlit dashboard | FastAPI 0.141.1 + React (Vite/TS) | Migrate at the **execution milestone** (order buttons, auth, remote/multi-device access, WebSockets for live updates). FastAPI would also serve the pipeline as an API today — adopt then, not now. |
| SQLite + Parquet | PostgreSQL (+ TimescaleDB) | Only when data outgrows one machine or becomes multi-user/remote. Zero benefit for single-user local v1. |
| APScheduler in-process | Windows Task Scheduler | Acceptable for simple daily backfill scripts; APScheduler is better because the whole engine is one process with shared state, and it survives pattern like "run 15s after every M15 close" cleanly. |
| Anthropic/OpenAI API | Ollama (local models) | Use Ollama during development to zero out LLM cost, or if API cost becomes a concern for high-frequency rescoring. Quality of narrative reasoning is notably better on hosted frontier models. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| MetaTrader5 package on non-Windows or in CI | Wheels are win_amd64-only; Wine bridges (mt5linux) are fragile and add a moving part to your most critical dependency | Keep ingestion on the Windows box with the terminal; everything downstream (backtests, dashboard) consumes Parquet and runs anywhere |
| `smartmoneyconcepts` as the production detector | 0.0.x maturity, centered-window swing detection repaints (future leak), educational-only disclaimer | Own confirmation-shifted implementation; use the lib only in tests to cross-check swing/liquidity logic |
| Using **bar 0** from `copy_rates_from_pos` in features or signals | Bar 0 is the still-forming candle — its close/high/low mutate until bar close; a classic silent leak | Start at `start_pos=1` (or drop the last bar after `copy_rates_range`) and schedule jobs just after bar close |
| Assuming MT5 timestamps are UTC | Bar `time` is **broker server time** (often UTC+2/+3 with DST) — daily/session boundaries and "equal highs" clustering shift accordingly | Normalize once at ingestion: store UTC-converted timestamps plus raw server time; make the broker offset a config value |
| backtesting.py for this system | Market-order, next-bar-open semantics can't express zone limit entries + fixed SL/TP; single symbol/timeframe | Custom bar-by-bar engine with explicit fill rules (limit fills only if price trades through; conservative SL-first on same-bar SL/TP) |
| TA-Lib / pandas-ta for the SMC layer | C-build friction on Windows (TA-Lib) and indicator-style functions, not structure/stateful-zone logic | pandas/numpy own implementation (structure logic is stateful: zones persist until mitigated — that's your code, not an indicator) |
| Fixed-horizon return labels + random KFold for the ML model | Overlapping samples + temporal autocorrelation → optimistic CV scores, model that dies live | Triple-barrier labels aligned to the setup's SL/TP geometry + walk-forward (or purged, embargoed CV) — Lopez de Prado AFML standard |
| Presenting raw LightGBM scores as "probability" | Boosting probabilities are miscalibrated; a "0.8" is not an 80% win rate | `CalibratedClassifierCV` inside the walk-forward loop; show calibrated probability + Brier/reliability stats |
| Airflow / Prefect / Dagster | Orchestration frameworks for multi-machine DAG fleets — heavy ops tax for one scheduled loop on one PC | APScheduler 3.x in the engine process |
| Docker/Postgres in v1 | Docker Desktop on Windows adds friction right next to a terminal-local data dependency; no multi-user need | Direct Windows processes + SQLite/Parquet; revisit at the execution milestone |
| Auto-trading crates/SDKs (e.g. unofficial MT5 REST bridges) in v1 | v1 is signals-only; third-party bridges add risk without value yet | Official MetaTrader5 package now; official `order_send` when execution milestone arrives |

## Stack Patterns by Variant

**If LLM cost/latency becomes an issue:**
- Cache narratives keyed by a hash of (setup content + bar window); regenerate only on material change.
- Swap the provider interface's backend to Ollama for dev runs; keep Anthropic/OpenAI for final signals.

**If the dashboard needs auth, remote access, or order execution:**
- Introduce FastAPI (0.141.x + uvicorn) as the engine's API layer and a React (Vite + TypeScript) frontend; Streamlit has served its purpose as the v1 accelerator.

**If backtest iteration speed becomes the bottleneck:**
- Query bars via DuckDB over the Parquet store; reserve vectorbt for fast vectorized screening of thousands of parameter combos, then re-verify finalists in the custom engine.

**If the MT5 terminal must run unattended (VPS/headless):**
- Keep the terminal as an always-on Windows process; connect with `mt5.initialize(path=r"...\terminal64.exe", login=..., password=..., server=...)` and retry via tenacity on `initialize() == False` with `mt5.last_error()` diagnostics.

**If you later add more symbols/timeframes:**
- The stack scales unchanged: Parquet per symbol/TF, same pipeline; only the LightGBM training set grows (consider per-symbol models vs pooled model with symbol features).

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| metatrader5 5.0.6147 | Python 3.6–3.14, **Windows x86-64 only** | Verified wheel matrix on PyPI; 64-bit Python mandatory. Terminal must be running and logged in. |
| lightgbm 4.7.0 | Python ≥3.10; numpy 2.x ok | `lightgbm[scikit-learn]` extra for full sklearn interop; VC runtime needed on Windows only if building from source (wheels bundle the lib). |
| scikit-learn 1.7.2 | numpy 2.x, pandas 2.3.x ok | CalibratedClassifierCV + LGBMClassifier compose cleanly. |
| pandas 2.3.3 / numpy 2.2.6 | py3.12 ok | pandas 2.x copy-on-write default — fine for this codebase style. |
| apscheduler 3.11.3 | pin `<4` | 4.x is a ground-up rewrite, still pre-release. |
| openai 3.6.0 / anthropic 1.2.0 | pydantic 2.x | `chat.completions.parse(PydanticModel)` (OpenAI) and tool-use strict schemas (Anthropic) both verified as current documented patterns. |
| streamlit 1.62.0 | plotly 7.0.0 | `st.plotly_chart` native. |
| sqlalchemy 2.0.52 | SQLite stdlib driver | No extra driver needed; use `sqlite:///path.db` URL. |

## Sources

- PyPI `metatrader5` project page — version 5.0.6147, wheel matrix (win_amd64, cp36–cp314), MIT, Aug 2026 release. (HIGH — official PyPI, live-fetched)
- MQL5 official Python integration docs (`mql5.com/en/docs/integration/python_metatrader5` + `mt5copyratesfrompos_py`) — function set, numpy structured-array return columns, bar-0 = forming bar, None-on-error + `last_error()`, "Max bars in chart" history cap. (HIGH — vendor docs, live-fetched)
- PyPI `smartmoneyconcepts` project page — 0.0.27, Apr 2026, dev-status "Planning", API surface incl. centered-window swing definition. (HIGH for facts; library-quality judgment MEDIUM)
- PyPI live version checks via pip index (2026-08-29): pandas 2.3.3, numpy 2.2.6, scikit-learn 1.7.2, lightgbm 4.7.0, vectorbt 1.0.0, backtesting 0.6.6, openai 3.6.0, anthropic 1.2.0, fastapi 0.141.1, streamlit 1.62.0, duckdb 1.5.5, apscheduler 3.11.3, xgboost 3.2.0, pydantic 2.13.5, plotly 7.0.0, pyarrow 25.0.1, sqlalchemy 2.0.52. (HIGH — live PyPI)
- Context7 `/openai/openai-python` — structured outputs via `chat.completions.parse()` with Pydantic models. (MEDIUM per seam; cross-consistent with official helpers docs)
- Context7 `/websites/lightgbm_readthedocs_io_en_stable` — `lgb.early_stopping()` callback, `LGBMClassifier.predict_proba`, best-iteration model saving. (MEDIUM per seam)
- Domain-methodology findings (SMC repaint/lookahead, walk-forward + triple-barrier/meta-labeling, LLM-narrative constraints, backtest fill realism, probability calibration) — synthesized from established quant-ML practice (Lopez de Prado, *Advances in Financial Machine Learning*) and community consensus; stored in research cache. (MEDIUM — practitioner consensus, not vendor-verifiable)

---
*Stack research for: AI Forex SMC Trading System (hybrid ML + LLM, MT5 feed)*
*Researched: 2026-08-29*
