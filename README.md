# AI Forex SMC Trading System

A Python-based AI trading assistant that ingests OHLC forex data from a local MetaTrader 5 terminal, detects Smart Money Concepts (liquidity sweeps of equal highs/lows and premium/discount zones), and produces high-probability trade setups through hybrid AI: a calibrated ML model scores each setup's P(WIN) while an LLM adds evidence-grounded confirmation reasoning. Setups are presented in a Streamlit dashboard with full evidence traces, history, performance stats, and pipeline health.

**v1 is signals-only** — no order placement, no broker order APIs. The goal is transparent, reasoned evidence you can trust and verify before trusting automation.

## Pipeline

```
MT5 terminal (Windows, logged in)
  │  closed-bar collection (M15/H1/H4, UTC-normalized)
  ▼
data/bars ──► SMC detector chain (swings → zigzag → pools → sweeps → zones → MTF bias)
  │                  │ point-in-time, look-ahead-safe — the SAME chain for live & backtest
  ▼                  ▼
setup engine ◄── backtest replay ──► triple-barrier labels ──► ML scorer (LightGBM,
  │  after each                (walk-forward stats)      (calibrated P(WIN), leak-audited)
  │  M15 close                                                     │
  ▼                                                                ▼
data/setups ◄── LLM narrative (confirm/refute over structured evidence only)
  │
  ▼
Streamlit dashboard (Setups / History / Performance / Health)
```

## Requirements

- **Windows** — the official `MetaTrader5` Python package requires it
- **uv** (installs Python 3.12 automatically) — `winget install astral-sh.uv`
- A **running, logged-in MetaTrader 5 terminal** for any collector work
- An **OpenAI-compatible LLM endpoint** for narratives (cloud e.g. MiniMax, or a local vLLM) — optional; the system degrades to ML-only scoring when disabled/unavailable

## Install

```bash
git clone https://github.com/el210003/AI-Trading.git
cd AI-Trading
uv sync                # recreates the exact locked environment from uv.lock
uv run pytest -q       # 569 passed = environment verified
```

Then create your machine-local config (never committed):

```bash
Copy-Item config.local.template.toml config.local.toml   # fill in the <FILL-IN>s
```

Fill in: MT5 `terminal_path` + `expected_server`, the empirically validated `broker_offset_hours` (+ `validated_at`), and the LLM block (`llm_base_url` / `llm_model` / `llm_api_key`). Verify it loads:

```bash
uv run python -c "from pathlib import Path; from ai_trading.config import load_config; load_config(Path('config.toml')); print('config OK')"
```

**Data store**: `data/` is gitignored runtime state. Either copy it from an existing machine, or regenerate from scratch:

```bash
uv run python -m ai_trading.collector --once      # connects, validates offset, backfills history
uv run python -m ai_trading.backtest --write      # replay + triple-barrier labels + walk-forward reports
uv run python -m ai_trading.ml --eval --train --write   # ML scorer: label gate -> features -> walk-forward -> artifact
```

## Usage

| Command | What it does |
|---|---|
| `uv run python -m ai_trading.collector` | Continuous closed-bar collection: connects to MT5, polls after each M15 close, stores UTC-normalized bars (add `--once` for a single poll) |
| `uv run python -m ai_trading.backtest --write` | Backtest/labeling run over stored bars: detector-chain replay, cost model (spread + slippage), triple-barrier labels, canonical + walk-forward reports |
| `uv run python -m ai_trading.ml --eval --train --write` | ML pipeline: label-count gate, leak-audited point-in-time features, calibrated LightGBM P(WIN), walk-forward evaluation, versioned artifact |
| `uv run python -m ai_trading.setup --once` | One setup-engine pass: assemble evidenced setups at the last closed M15 bar, resolve lifecycles (pending → active → tp_hit/sl_hit/expired/invalidated) |
| `uv run python -m ai_trading.setup --monitor` | The engine loop: re-runs after each M15 close |
| `uv run streamlit run src/ai_trading/dashboard/app.py` | The dashboard (http://localhost:8501) |

Typical live operation: keep the **collector** and the **engine monitor** running; open the **dashboard** whenever.

### Dashboard

- **Setups** — filterable/sortable setup table (symbol, status, direction, min P(WIN), date range); selecting a row renders the candlestick with entry/SL/TP lines, sweep marker, and premium/discount-zone bands, plus the full 6-section evidence trace (bias, zone, sweep, ML contributors, LLM narrative)
- **History** — lifecycle outcome for every emitted setup, newest-first
- **Performance** — Win Rate / Profit Factor / Expectancy (R) KPIs, cumulative-R equity curve (reuses the exact backtest stats functions; a caption notes live-vs-backtest comparability)
- **Health** — per-feed last-bar freshness, MT5/collector heartbeat, recent data-quality errors

## Configuration

- `config.toml` — committed defaults: symbols, timeframes, backtest/ML/LLM/setup knobs. Documents every key.
- `config.local.toml` — gitignored machine-local overrides (wins key-by-key): terminal path, validated broker offset, API keys. See `config.local.template.toml`.
- Notable knobs:
  - `symbols` — collected universe; `setup_symbols` — the subset the setup engine works on (absent = all). A collected-but-not-setup symbol is a collect-only data feed (BTCUSD ships this way as a weekend/debug feed — crypto trades 7x24 while forex closes over the weekend)
  - `setup_min_p_win` — engine-side qualification floor on ML P(WIN) (0.0 = persist every detector-passing candidate)
  - `llm_enabled` / `llm_base_url` / `llm_model` — narrative provider; `llm_api_key` lives only in `config.local.toml`
  - `ml_feature_list_version` — bump when the feature schema changes so stale artifacts refuse to load

## Data layout

```
data/
  bars/      # <SYMBOL>_<TF>.parquet — UTC-normalized closed bars (raw server time kept)
  meta/      # meta.sqlite — collector heartbeats, history bounds, data-gap records
  labels/    # triple-barrier outcome labels per symbol (backtest output)
  reports/   # walk-forward + ML evaluation artifacts
  models/    # versioned ML scorer bundles + LATEST.json
  setups/    # setups.parquet — the setup store (atomic, dedup on setup_id)
```

## Testing

```bash
uv run pytest -q                # full suite (offline; 569 tests)
uv run pytest tests/unit -q     # unit slice
```

Integration tests that require a live MT5 terminal or LLM endpoint live under `tests/integration/` and are deselected by default.

## Scope notes

- **v1 signals-only** — order execution is the next milestone
- **Forex majors** EURUSD / GBPUSD / USDJPY on M15/H1/H4 — BTCUSD is collected as a weekend data feed only and is excluded from setups
- MT5 is the sole data source; non-forex instruments and mobile are out of scope for v1
- `.planning/` holds the development methodology docs (roadmap, phase plans, decisions) generated with GSD
