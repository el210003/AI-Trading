# Phase 1: Data Foundation - Research

**Researched:** 2026-08-30 (session date 2026-08-29/30)
**Domain:** MT5 Python API ingestion, UTC/broker-time normalization, Parquet/SQLite local data stores (Python 3.12, Windows)
**Confidence:** HIGH (core API and time semantics verified from official MetaQuotes docs; broker-offset specifics empirically validated during execution by design)

## Summary

Phase 1 builds the first code in this repo: a uv-managed Python 3.12 project with a closed-bar OHLC collector that pulls EURUSD/GBPUSD/USDJPY M15/H1/H4 bars from the local MT5 terminal via the official `MetaTrader5` package, normalizes timestamps to UTC, stores bars in Parquet and collection state in SQLite, backfills gaps idempotently on restart, and persists a history-availability report. Every claim about the MT5 Python API below was verified directly against the official MetaQuotes documentation on mql5.com this session (search engines were largely unavailable; official docs were fetched via direct HTTP instead — this *increases* source quality).

The three decisive research findings: **(1) MT5 `time` values are epoch seconds that decode to broker server *wall-clock* time, not true UTC** — the official docs' "UTC (without the shift)" phrasing means no shift is applied to server time, so a validated broker-offset config is mandatory (exactly what DATA-03 locked). **(2) The terminal caps returned bars at the "Max. bars in chart" setting** (`terminal_info().maxbars`, default 5000 in the official example) — history depth and backfill volume are bounded by this terminal setting, and it must be a first-class health-check item. **(3) History download is lazy and partial** — the official CopyRates notes state a first request initiates download and returns only what is ready, with the same request later returning more; retry-until-count-stabilizes is the officially sanctioned backfill loop, and out-of-range/over-cap requests return `None` with error `-4`.

This is a **greenfield phase — no Runtime State Inventory is required** (repo contains only `.planning/`). The machine has **two MT5 terminals installed** (IC Markets Global v5.0.5833 and "MetaTrader 5-01" v5.0.4410), neither at the default install path and **neither currently running** — terminal path must be explicit config, and a `checkpoint:human-verify` is needed to confirm which terminal/account is the intended feed.

**Primary recommendation:** Thin MT5 adapter (module-level wrapper over `MetaTrader5` for testability) + poll-after-M15-close collector storing one Parquet file per (symbol, timeframe) rewritten atomically (temp + `os.replace`), SQLite WAL meta DB holding last-bar checkpoints and history bounds, UTC normalization as `time` (raw server wall time, preserved) + `time_utc` (server − validated offset), with startup health checks mapping `last_error()` codes to actionable messages.

<user_constraints>
## User Constraints (from STATE.md / PROJECT.md — locked decisions)

No CONTEXT.md exists for this phase; per orchestrator instructions the accumulated decisions in STATE.md/PROJECT.md are treated as user-locked:

### Locked Decisions
- Stack locked per init research: **Python 3.12, metatrader5 5.0.6147, pandas, SQLite+Parquet stores, uv for env management, ruff+pytest** (STATE.md Accumulated Context; PROJECT.md Constraints)
- **Broker server timezone offset must be validated empirically against the user's MT5 terminal during Phase 1** (STATE.md Blockers/Concerns)
- **MT5 terminal must be running and logged in for any collector work** (STATE.md Blockers/Concerns)
- Data source: **MT5 OHLC only — no third-party data vendors in v1** (PROJECT.md Constraints)
- Instruments: **EURUSD, GBPUSD, USDJPY on M15/H1/H4** (PROJECT.md Constraints)
- v1 is signals-only (no order placement) — constrains MT5 usage to market-data calls this phase (PROJECT.md Key Decisions)
- One shared, look-ahead-safe code path for live analysis AND backtests (non-negotiable) — for Phase 1 this means: store closed bars only, document bar open-time semantics unambiguously, and make the store layer reusable read-side for later phases (STATE.md)

### the agent's Discretion
- Internal module layout, config file format details, Parquet file granularity, SQLite schema specifics, polling loop implementation, test fixture strategy (roadmap plans 01-01..01-03 give intent, not implementation)

### Deferred Ideas (OUT OF SCOPE)
- Tick data collection, tick streaming (REQUIREMENTS Out of Scope)
- Any SMC detection, ML, LLM, dashboard, or execution concerns (Phases 2–6)
- Multi-broker / multi-account support beyond the single configured terminal
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DATA-01 | Connect to local MT5 terminal and verify health at startup (initialize success, each symbol selectable via symbol_select) | Verified API: `initialize(path, login=, password=, server=, portable=)` → bool, auto-launches terminal; `last_error()` tuple codes (-6 auth failed, -8 auto-trading disabled, IPC -10000/-10001); `symbol_select(symbol, True)` → bool; `account_info()` → None when logged out; `terminal_info().connected`. Health-check sequence + actionable-error mapping in Code Examples 1 |
| DATA-02 | Collect closed-bar OHLC for EURUSD/GBPUSD/USDJPY on M15/H1/H4 via MetaTrader5 lib | Verified: `copy_rates_from_pos(symbol, tf, start_pos=1, count)` — start_pos=0 is the forming bar, so closed bars start at 1; returns numpy structured array (time, open, high, low, close, tick_volume, spread, real_volume); `mt5.TIMEFRAME_M15/H1/H4` enums; poll scheduling after M15 boundary |
| DATA-03 | All stored bar timestamps UTC-normalized, broker server offset held as validated configuration | Verified time semantics: bar open times are server-formed (TimeCurrent docs); Python docs state times stored "in UTC time zone (without the shift)" → `pd.to_datetime(unit='s')` yields server wall clock; true UTC = server − offset with offset in validated config (raw `time` column preserved per success criterion 2). Empirical offset-validation methods documented |
| DATA-04 | Incremental updates with gap backfill, idempotent across restarts | Verified: retry-until-count-stabilizes range fetching (official CopyRates notes); `copy_rates_range` inclusive [date_from, date_to]; -1/None + code -4 when out of range/cap; idempotent merge = concat + `drop_duplicates(subset=['time'], keep='last')` + sort + atomic rewrite |
| DATA-05 | Report available history depth per symbol/timeframe, persisted for backtest range validation | Verified: history bounded by "Max. bars in chart" (`terminal_info().maxbars`, default 5000); walk-backward-in-chunks discovery loop; SQLite `history_bounds` table design; report must include terminal maxbars provenance |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| MT5 connection lifecycle + health checks | Adapter/service (MT5 client wrapper) | — | Module-level MT5 API calls are process-local Windows IPC; wrapped in thin adapter for testability |
| Closed-bar polling & scheduling | Service (collector loop) | Adapter | Poll timing logic is app logic; data acquisition via adapter |
| UTC normalization (offset application) | Domain/transform (pure functions) | Config | Pure DataFrame math over validated config offset — must be unit-testable without MT5 |
| Bar persistence (Parquet) | Storage layer | — | Local file store; atomic-write discipline lives here |
| Collection state / checkpoints (SQLite) | Storage layer | — | Restart idempotency depends on checkpoint semantics |
| Gap backfill | Service | Storage | Uses checkpoints (storage) + adapter range fetch + transform merge |
| History-availability report (DATA-05) | Service | Storage | Discovery via adapter; persisted/queryable via SQLite; consumed by Phase 3 backtester |

No web/API/browser tiers exist in this phase — everything is a local Windows Python service.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| metatrader5 | 5.0.6147 (pin `==5.0.6147`) | Official MetaQuotes Python↔MT5-terminal bridge; only sanctioned data path | Publisher `metaquotes` on PyPI, MIT, docs at mql5.com [VERIFIED: pypi.org/project/MetaTrader5 + mql5.com docs] |
| pandas | 3.0.5 (pin `>=3.0,<4`) | DataFrame handling, dedup/merge, `to_datetime(unit='s')`, parquet IO | De-facto standard; 135M downloads/wk [VERIFIED: PyPI + pypistats] |
| pyarrow | 25.0.1 | Parquet engine (required dependency of pandas 3.x anyway) | Apache official, 82M downloads/wk [VERIFIED: PyPI + pypistats] |
| Python | 3.12 (managed by uv) | Runtime | cp312 win_amd64 wheel of metatrader5 5.0.6147 confirmed on PyPI [VERIFIED: PyPI files list] |
| uv | 0.11.28 (installed) | Project/env management, dependency locking | Modern standard for Python projects [VERIFIED: local install] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | latest (dev dep) | Test framework, markers `unit`/`mt5` | All plans |
| ruff | latest (dev dep) | Lint + format | All plans |
| sqlite3 | stdlib | Meta store, checkpoints, history bounds | Zero-dependency persistence |
| zoneinfo / datetime | stdlib | True-UTC wall clock for offset validation | pandas 3.x dropped pytz in favor of zoneinfo [CITED: pandas 3.0 whatsnew] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Whole-file Parquet rewrite per update | Partitioned pyarrow.dataset appends | Dataset appends add partition/compaction complexity for zero benefit at this scale (~25k bars/yr/TF); whole-file rewrite is atomic and trivially correct |
| TOML config via stdlib `tomllib` | pydantic-settings / dynaconf | Extra dependency; a 60-line dataclass validator covers symbols/timeframes/offset/path needs |
| Polling loop + APScheduler/cron | Stdlib `time` loop | Windows Task Scheduler or a simple loop with drift-corrected sleep is enough; a scheduler framework is overhead for one process |
| SQLite | DuckDB | DuckDB is a great analytical read layer but adds a dependency; SQLite is locked by project decision and sufficient for meta/checkpoints/report |

**Installation:**
```bash
uv init --python 3.12   # plan 01-01 scaffold (or manual pyproject.toml)
uv add "metatrader5==5.0.6147" "pandas>=3.0,<4" pyarrow
uv add --dev pytest ruff
```

**Version verification:** All versions above verified this session against PyPI JSON API and pypistats.org (metatrader5 5.0.6147 released 2026-08-27; pandas 3.0.5; pyarrow 25.0.1). No training-data versions used.

## Package Legitimacy Audit

> Protocol run: `gsd-tools query package-legitimacy check --ecosystem pypi metatrader5 pandas pyarrow ruff pytest`. The seam returned mechanical `SUS` verdicts for all five — reasons were exclusively `too-new` (recent release dates, i.e. active maintenance) and `unknown-downloads` (the seam could not read download stats: `weeklyDownloads: null`). I compensated with authoritative evidence: PyPI publisher/metadata + pypistats.org API (fetched this session).

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| metatrader5 | PyPI | pkg since ≥2021; current release 2026-08-27 | 37,478/wk; 200k/mo [VERIFIED: pypistats] | Official: metatrader5.com + mql5.com docs; publisher `metaquotes` [VERIFIED: PyPI] | seam=SUS (stats unavailable); audit=OK on evidence | Approved — vendor binary, official publisher confirmed; **planner adds `checkpoint:human-verify` before install** per SUS-kept protocol |
| pandas | PyPI | 17+ yrs; current release 2026-07-22 | 135.1M/wk [VERIFIED: pypistats] | github.com/pandas-dev/pandas | seam=SUS (mechanical); audit=OK | Approved |
| pyarrow | PyPI | current release 2026-08-10 | 82.2M/wk [VERIFIED: pypistats] | arrow.apache.org [VERIFIED: PyPI metadata] | seam=SUS (mechanical); audit=OK | Approved |
| ruff | PyPI | current release 2026-08-27 | 66.7M/wk [VERIFIED: pypistats] | docs.astral.sh/ruff [VERIFIED: PyPI metadata] | seam=SUS (mechanical); audit=OK | Approved |
| pytest | PyPI | current release 2026-06-19 | 200.6M/wk [VERIFIED: pypistats] | github.com/pytest-dev/pytest [VERIFIED: PyPI metadata] | seam=SUS (mechanical); audit=OK | Approved |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** metatrader5 (kept — evidence upgrades it to OK; insert `checkpoint:human-verify` before `uv add`). No postinstall scripts on any of the five (`scripts.postinstall`: none [VERIFIED: seam signals]). Name-squat check: `pypi.org/project/MetaTrader5` normalizes to `metatrader5` — the install name matches the official docs' `pip install MetaTrader5` case-insensitively [VERIFIED: PyPI redirect].

## Architecture Patterns

### System Architecture Diagram

```
                 [User starts MT5 terminal (human prerequisite)]
                                   │ logged in, connected
                                   ▼
   ┌───────────────────────────────────────────────────────────────┐
   │                    Collector process (CLI)                     │
   │                                                                │
   │  config.toml ──► Config loader (symbols, TFs, terminal_path,  │
   │                  broker_offset_hours + validated_at, paths)    │
   │                        │                                       │
   │                        ▼                                       │
   │  ┌─────────────── Startup health check (DATA-01) ───────────┐  │
   │  │ initialize(path) → last_error() → terminal_info().connected│ │
   │  │ account_info() not None → symbol_select(sym, True) ×3     │  │
   │  └────── fail: raise actionable error mapping code→message ──┘  │
   │                        │ pass                                   │
   │                        ▼                                        │
   │  ┌── Offset validation (DATA-03) ──┐    ┌── Backfill (DATA-04)─┐│
   │  │ compare live bar/tick server    │    │ checkpoint →          ││
   │  │ time vs true UTC wall clock     │    │ copy_rates_range(from ││
   │  │ → confirm/correct config offset │    │ =last_bar) retry-until││
   │  └──────────────┬──────────────────┘    │ -stable → merge dedup ││
   │                 │                        └──────────┬───────────┘│
   │                 ▼                                   │            │
   │  ┌── Poll loop (DATA-02) ──────────┐                │            │
   │  │ sleep to M15 boundary + delay   │                │            │
   │  │ copy_rates_from_pos(pos=1)      │◄── also feeds──┘            │
   │  │ → new bars (time > checkpoint)  │                             │
   │  └──────────────┬──────────────────┘                             │
   │                 ▼                                                │
   │  ┌── Transform (DATA-03) ─────────────────────────┐              │
   │  │ time_raw (server wall, preserved)              │              │
   │  │ time_utc = time_raw − offset   (pure function) │              │
   │  └──────────────┬─────────────────────────────────┘              │
   │                 ▼                                                │
   │  ┌── Storage ──────────────────────────────────────────────┐    │
   │  │ data/bars/{SYMBOL}_{TF}.parquet  (atomic rewrite)       │    │
   │  │ meta/meta.sqlite  (WAL: collection_state, history_bounds│    │
   │  └──────────────┬──────────────────────────────────────────┘    │
   └─────────────────┼───────────────────────────────────────────────┘
                     ▼
   ┌── History-availability report (DATA-05) ──────────────────────┐
   │ per symbol/TF: first_bar, last_bar, count, terminal_maxbars,  │
   │ gap list → SQLite table + queryable/CLI print                  │
   └────────────────────────────────────────────────────────────────┘
```

Primary use case trace: terminal running → collector start → health check → offset validation → initial backfill (checkpoint-driven) → per-M15 poll → transform → atomic Parquet write + SQLite checkpoint update → history report queryable.

### Recommended Project Structure
```
ai-trading/                    # repo root (D:\Git\AI-Trading)
├── pyproject.toml             # uv project: deps, [tool.pytest.ini_options] markers, [tool.ruff]
├── config.toml                # symbols, timeframes, terminal_path, data paths, broker_offset_hours
├── config.local.toml          # gitignored overrides (paths; optional MT5 login/password — see Security)
├── src/ai_trading/
│   ├── config.py              # tomllib load + dataclass validation (DATA-03 offset lives here)
│   ├── mt5_client.py          # thin adapter over MetaTrader5 module (importable fake for tests)
│   ├── normalize.py           # PURE time/UTC transform functions (unit-testable, no MT5 import)
│   ├── stores/
│   │   ├── bar_store.py       # Parquet read/merge/atomic-write per (symbol, timeframe)
│   │   └── meta_store.py      # SQLite WAL: collection_state, history_bounds
│   ├── collector.py           # health check + poll loop + backfill orchestration
│   └── history_report.py      # DATA-05 discovery + report persistence/query
├── tests/
│   ├── conftest.py            # fake MT5 client fixture, synthetic bar factories
│   ├── unit/                  # no MT5 required (default pytest run)
│   └── integration/           # marked `mt5`; requires running terminal
└── data/                      # gitignored runtime artifacts (bars/, meta/)
```

### Pattern 1: Thin MT5 Adapter (import-swap testability)
**What:** `mt5_client.py` wraps the module-level `MetaTrader5` functions behind plain Python functions. Tests inject a fake with the same surface.
**When to use:** always in this phase — MT5 is Windows-IPC-bound and terminal-state-dependent; unit tests must never require it.
**Example:**
```python
# Source: official API surface [VERIFIED: mql5.com/en/docs/integration/python_metatrader5]
# mt5_client.py
import MetaTrader5 as mt5

def initialize(path: str | None = None, timeout_ms: int = 30000) -> bool:
    return mt5.initialize(path=path, timeout=timeout_ms) if path else mt5.initialize(timeout=timeout_ms)
def last_error() -> tuple[int, str]: return mt5.last_error()
def terminal_info(): return mt5.terminal_info()
def account_info(): return mt5.account_info()
def symbol_select(symbol: str, enable: bool = True) -> bool: return mt5.symbol_select(symbol, enable)
def copy_rates_from_pos(symbol: str, timeframe: int, start_pos: int, count: int):
    return mt5.copy_rates_from_pos(symbol, timeframe, start_pos, count)
def copy_rates_range(symbol: str, timeframe: int, date_from, date_to):
    return mt5.copy_rates_range(symbol, timeframe, date_from, date_to)
def shutdown() -> None: mt5.shutdown()
```

### Pattern 2: Closed-bar polling on boundary + delay
**What:** sleep until the next M15 boundary plus a small fixed delay (2–5 s), then fetch from `start_pos=1`. Only bars with `time > last_stored_time` are new.
**Why pos=1:** official docs: bar numbering goes present→past and "the zero bar means the current one" — position 0 is still forming [VERIFIED: mql5.com copy_rates_from_pos].
**Example:**
```python
# closed bars only — the forming bar at start_pos=0 must never be stored
rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 1, lookback)
```

### Pattern 3: Idempotent merge + atomic file replace
**What:** new bars are concatenated with the stored frame, deduplicated on bar-open time (`keep="last"` so a refetched bar overwrites), sorted, and written to a temp file in the same directory, then `os.replace()`d over the target (atomic on the same NTFS volume).
**Why:** Parquet has no append; at ~25k bars/year/M15 a full rewrite of one (symbol, TF) file is milliseconds. Restart always converges to exactly-one-row-per-open-time.
**Example:**
```python
# Pattern verified against pandas 3.x semantics [CITED: pandas pydata docs]
import os
from pathlib import Path
import pandas as pd

def merge_and_write(new: pd.DataFrame, path: Path) -> int:
    old = pd.read_parquet(path) if path.exists() else None
    df = new if old is None else pd.concat([old, new], ignore_index=True)
    df = (df.drop_duplicates(subset=["time"], keep="last")
            .sort_values("time").reset_index(drop=True))
    tmp = path.with_suffix(".parquet.tmp")
    df.to_parquet(tmp, engine="pyarrow", compression="zstd", index=False)
    os.replace(tmp, path)          # atomic on same volume (Windows included)
    return len(df)
```

### Pattern 4: Retry-until-stable history fetch (officially sanctioned)
**What:** range requests may return partial data while the terminal downloads; loop the identical request until the row count stops growing; treat `None` + code `-4` (no history) as "not ready yet, retry", not fatal. Requests beyond available history or past `maxbars` return `None` (-1/`RES_E_NOT_FOUND`) — used as the walk-back stop signal for DATA-05 [VERIFIED: MQL5 CopyRates notes referenced by the Python docs].
**Example:** see Code Examples §3.

### Pattern 5: Checkpoint-driven restart (no silent gaps)
**What:** after every successful write, SQLite records `last_bar_time` per (symbol, TF) in one UPSERT transaction. On start, backfill range = `(last_bar_time, now]`. Because the merge is idempotent, overlapping refetch is harmless; a crash between write and checkpoint merely refetches.
**Why:** the checkpoint is the *only* restart state — no in-memory or file-naming tricks.

### Anti-Patterns to Avoid
- **Guessing an IANA timezone for broker time:** server time is *not* a true zone (offset changes on the broker's DST policy, commonly US-DST-aligned, which no single IANA zone captures reliably). Store a numeric offset + validation timestamp; re-validate at startup. [ASSUMED broker conventions; validation approach locked by project decision]
- **Storing the forming bar:** never persist `start_pos=0`; it rewrites values and breaks "closed bars" guarantees (Phase 2/3 correctness depends on this).
- **Treating `None` from copy_rates as a crash:** it is the documented not-ready/out-of-range signal; retry or stop-the-walk accordingly. [VERIFIED: MQL5 CopyRates notes]
- **Per-row Parquet appends / dataset partition sprawl:** unnecessary complexity at this scale; atomic whole-file rewrite instead.
- **Hard-failing on weekend/holiday gaps:** forex closes Fri ~21–22h UTC and reopens Sun ~21–22h UTC (broker-dependent); gap validation must be session-aware — report gaps, don't crash. [ASSUMED market-hours conventions; make thresholds config-driven]
- **Logging credentials:** initialize params must never appear in logs or error messages.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Parquet read/write | Custom binary format or CSV | pandas/pyarrow `to_parquet`/`read_parquet` (zstd) | Columnar, typed, fast; hand-rolled formats rot |
| Dedup/merge of bar frames | Manual row-by-row diffing | `pd.concat` + `drop_duplicates(subset=['time'], keep='last')` + sort | Vectorized, one line, provably idempotent |
| Time arithmetic | Manual epoch math scattered around | One pure `normalize.py` with `pd.to_datetime(unit='s')` + offset subtraction | Single source of truth for the trickiest correctness domain in the project |
| Atomic file replacement | "Delete then write" | temp file + `os.replace` | os.replace is atomic on Windows same-volume; delete-then-write loses data on crash |
| Config parsing/validation | Ad-hoc dict plumbing | `tomllib` (stdlib) + dataclass with explicit field validation | Type errors surface at startup, not mid-collection |
| Meta persistence | JSON sidecar files | SQLite WAL (stdlib) | Transactional UPSERT checkpointing; queryable for DATA-05 and later health strips |
| MT5 connectivity edge cases | Reimplemented IPC/polling of the terminal | The MetaTrader5 package's documented behaviors (auto-launch, last_error codes) | It is the only supported bridge; wrapping its documented semantics is the whole job |

**Key insight:** every hand-rolled substitute here either loses atomicity (crash-safety) or re-encodes timestamp semantics that this project explicitly decided to centralize and validate.

## Runtime State Inventory

**Omitted — greenfield phase.** The repository contains only `.planning/`; there is no prior runtime, store, or OS-registered state carrying this phase's names. Verified by `git log` (only planning commits) and directory inspection this session. Note for later phases: the collector *creates* runtime state (Parquet files, SQLite DB, config-validated offset) that future rename/migration phases must inventory.

## Common Pitfalls

### Pitfall 1: The "UTC without shift" time-semantics trap (THE pitfall of this phase)
**What goes wrong:** Treating MT5 `time` epoch seconds as true UTC. They encode **broker server wall-clock time**; decoding yields e.g. `2026-08-29 00:00` when true UTC was `2026-08-28 21:00` (UTC+3 broker). Everything downstream — MTF joins, session logic, backtests — silently shifts by the broker offset.
**Why it happens:** the official docs say "MetaTrader 5 stores tick and bar open time in UTC time zone (without the shift)... Data received from the MetaTrader 5 terminal has UTC time" — ambiguous phrasing that the community has long parsed as "server wall time, no shift applied". MQL5's own docs confirm times are "formed on a trade server and do not depend on the time settings on your computer". [VERIFIED: mql5.com mt5copyratesrange + TimeCurrent]
**How to avoid:** store BOTH columns: `time` (raw server wall time — required preserved by success criterion 2) and `time_utc = time − offset` where offset comes from validated config. Validate the offset empirically at startup (see Code Examples §6). Never `tz_localize` broker times to an IANA zone.
**Warning signs:** daily bars opening at 00:00 in `time_utc`; new H1 bars appearing 2–3h after the true UTC hour; DST-transition weeks where the same offset produces different bar-boundary alignments.

### Pitfall 2: "Max. bars in chart" silently caps history
**What goes wrong:** `copy_rates_from_pos(..., count=500000)` or a wide `copy_rates_range` returns fewer bars than requested, or `None` — history depth is bounded by the terminal setting (`terminal_info().maxbars`; official example shows default 5000). The collector "works" but DATA-05 reports ~2.5 months of M15 instead of years, and Phase 3 backtests starve.
**Why it happens:** official note: "MetaTrader 5 terminal provides bars only within a history available to a user on charts. The number of bars available to users is set in the 'Max. bars in chart' parameter." [VERIFIED: mql5.com]
**How to avoid:** read `terminal_info().maxbars` at startup; if it is a finite small number, log a loud WARNING with instructions (Tools → Options → Charts → Max. bars in chart → *Unlimited*). DATA-05 report must record `maxbars` and actual discovered bounds. Document the manual setting in plan 01-02/01-03 verification steps.
**Warning signs:** backfill rounds that always stop at the same bar count across symbols; first-bar dates clustered within days of `now − maxbars × TF`.

### Pitfall 3: First history request returns partial data
**What goes wrong:** accepting the first `copy_rates_range` result as complete → permanent silent gaps until the next restart backfill.
**Why it happens:** official behavior: when data are not local, the terminal starts downloading and the call "will return the amount of data that will be ready by the moment of timeout expiration... at the next similar request the function will return more data." [VERIFIED: MQL5 CopyRates notes]
**How to avoid:** retry-until-count-stabilizes loop (Pattern 4); only persist after two consecutive equal counts; treat code `-4` as retry.
**Warning signs:** backfilled bar counts that differ run-to-run; history report counts that grow without collection activity.

### Pitfall 4: Off-by-one on the forming bar
**What goes wrong:** storing `start_pos=0` → the forming bar is persisted with partial OHLCV, then re-persisted later; "closed bars only" guarantee broken; Phase 2 repaint tests will fail mysteriously later.
**Why it happens:** zero bar = current bar per official docs [VERIFIED: mql5.com].
**How to avoid:** always fetch from `start_pos=1`; additionally assert `max(time_utc) < now_utc_floor(tf)` in the store write path (cheap invariant).
**Warning signs:** last stored bar's close == live price mid-interval; duplicate-time rows with changing close values.

### Pitfall 5: Restart backfill that rewrites history instead of merging
**What goes wrong:** naive "fetch everything and replace file" strategies lose bars fetched moments before a crash, or duplicate rows on overlap.
**How to avoid:** checkpoint-driven range fetch (Pattern 5) + idempotent merge (Pattern 3). Overlap is expected and harmless by construction.
**Warning signs:** row-count regressions after restart; `drop_duplicates` not keyed on exact bar-open time.

### Pitfall 6: Weekend/holiday/session gaps misread as collection failure
**What goes wrong:** gap detector flags every weekend → alert fatigue; or worse, gaps are ignored entirely and a real outage hides among "expected" gaps.
**Why it happens:** forex trades ~24/5 with a Sunday-open/Friday-close boundary and daily maintenance minutes that vary per broker; holidays differ per broker. [ASSUMED conventions]
**How to avoid:** store a `gap` list (start, end) in the meta DB computed as aligned-TF holes inside `[first_bar, last_bar]`; classify only in reporting (weekend-window heuristic flagged as "review"), never crash. Human eyeballs the first report; thresholds become config.
**Warning signs:** gap report dominated by 47–49h weekend blocks; missing Monday bars after holidays (broker-specific).

### Pitfall 7: pandas 3.x behavior changes bite old habits
**What goes wrong:** code using `astype('datetime64[ns, UTC]')` for tz conversion (prohibited since pandas 2.0 — use `tz_localize`/`tz_convert`), assuming pytz, or Copy-on-Write surprises from chained assignment. [CITED: pandas 3.0 whatsnew + v2.0 whatsnew]
**How to avoid:** pin `pandas>=3.0,<4`; do tz work in `normalize.py` only; prefer explicit `.copy()` where frames cross function boundaries (CoW default makes accidental mutation visible rather than silent).
**Warning signs:** `FutureWarning`/`PerformanceWarning` storms; dtype of string columns showing `str` (new string dtype) instead of `object`.

### Pitfall 8: initialize() launches/connects to the WRONG terminal
**What goes wrong:** `initialize()` with no path connects to whichever terminal it finds (this machine has at least two MT5 installs plus several MT4 ones); or it launches a fresh unlogged terminal instance.
**Why it happens:** docs: without a path "the module attempts to find the executable file on its own"; it auto-launches if needed. [VERIFIED: mql5.com initialize]
**How to avoid:** `terminal_path` is required config; on this machine the candidates are `C:\Program Files\MetaTrader 5 IC Markets Global\terminal64.exe` (v5.0.0.5833) and `C:\Program Files\MetaTrader 5-01\terminal64.exe` (v5.0.0.4410) [VERIFIED: local filesystem probe]. Validate at startup that `account_info()` is non-None and its `server` matches config expectations.
**Warning signs:** health check passes but symbol history is empty (wrong broker feed); `account_info().login` differs from expected.

## Code Examples

### 1. Startup health check with actionable failures (DATA-01)
```python
# Source: API surface verified at mql5.com/en/docs/integration/python_metatrader5/*
import MetaTrader5 as mt5

AUTH_FAILED = -6          # RES_E_AUTH_FAILED: terminal up, account not authorized
NO_HISTORY = -4           # RES_E_NOT_FOUND: no history / not ready
AUTO_TRADING_DISABLED = -8

def connect_and_verify(cfg) -> None:
    if not mt5.initialize(path=cfg.terminal_path, timeout=cfg.init_timeout_ms):
        code, msg = mt5.last_error()
        raise MT5ConnectionError(
            f"MT5 initialize failed [{code}: {msg}]. "
            f"Is the terminal running at '{cfg.terminal_path}' and logged in? "
            "(code -6 means terminal is up but no account is authorized).")
    info = mt5.terminal_info()
    if info is None or not info.connected:
        raise MT5ConnectionError("Terminal not connected to the broker server "
                                 "(terminal_info().connected is False) — log in to the trade server.")
    if mt5.account_info() is None:
        code, msg = mt5.last_error()
        raise MT5ConnectionError(f"No trading account authorized [{code}: {msg}] — "
                                 "open the terminal and log in, or set login/password/server in config.")
    for sym in cfg.symbols:
        if not mt5.symbol_select(sym, True):
            code, msg = mt5.last_error()
            raise MT5ConnectionError(f"symbol_select('{sym}') failed [{code}: {msg}] — "
                                     f"symbol not available on this broker; check Market Watch / symbol name suffix.")
    if info.maxbars < cfg.min_maxbars:   # e.g. warn below 100_000
        log.warning("terminal maxbars=%d — history is capped; set Tools>Options>Charts>Max. bars in chart=Unlimited", info.maxbars)
```

### 2. Closed-bar fetch → DataFrame → UTC normalization (DATA-02/03)
```python
# Source: mql5.com copy_rates_from_pos + copy_rates_range docs; pandas whatsnew 3.0
import pandas as pd
from datetime import timedelta

COLUMNS = ["symbol", "time", "time_utc", "open", "high", "low", "close",
           "tick_volume", "spread", "real_volume"]

def fetch_closed_bars(cfg, symbol: str, timeframe: int, count: int) -> pd.DataFrame:
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 1, count)   # pos=1: skip forming bar
    if rates is None or len(rates) == 0:
        code, msg = mt5.last_error()
        raise MT5DataError(f"copy_rates_from_pos({symbol}) -> None [{code}: {msg}]")
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")              # server wall time (RAW, preserved)
    df["time_utc"] = df["time"] - timedelta(hours=cfg.broker_offset_hours)  # validated offset → true UTC
    df.insert(0, "symbol", symbol)
    return df[COLUMNS]
```

### 3. Retry-until-stable range fetch (DATA-04/05 backfill + discovery)
```python
# Source: MQL5 CopyRates notes ("at the next similar request the function will return more data")
import time
from datetime import datetime, timezone

def fetch_range_until_stable(symbol, timeframe, date_from, date_to, max_rounds=12, pause=0.7):
    prev = -1
    for _ in range(max_rounds):
        rates = mt5.copy_rates_range(symbol, timeframe, date_from, date_to)
        if rates is None:
            code, msg = mt5.last_error()
            if code == NO_HISTORY:          # not yet downloaded — keep polling
                time.sleep(pause); continue
            raise MT5DataError(f"copy_rates_range({symbol}) -> None [{code}: {msg}]")
        if len(rates) == prev:              # count stable → download complete
            return rates
        prev = len(rates)
        time.sleep(pause)
    raise MT5DataError(f"{symbol}: history did not stabilize in {max_rounds} rounds")
# DATA-05 walk-back: step date_from backward in 1-year chunks; a persistent None
# marks the true start of available history (or the maxbars cap) — record both.
```

### 4. SQLite checkpoint UPSERT (DATA-04 restart state)
```python
# Standard SQLite pattern [ASSUMED: stdlib semantics; WAL + upsert documented on sqlite.org]
import sqlite3

DDL = """
CREATE TABLE IF NOT EXISTS collection_state (
  symbol TEXT NOT NULL, timeframe TEXT NOT NULL,
  last_bar_time TEXT NOT NULL, last_success_at TEXT NOT NULL,
  PRIMARY KEY (symbol, timeframe));
CREATE TABLE IF NOT EXISTS history_bounds (
  symbol TEXT NOT NULL, timeframe TEXT NOT NULL,
  first_bar_utc TEXT, last_bar_utc TEXT, bar_count INTEGER,
  terminal_maxbars INTEGER, fetched_at TEXT NOT NULL,
  PRIMARY KEY (symbol, timeframe));
"""
def update_checkpoint(conn, symbol, timeframe, last_bar_iso, now_iso):
    conn.execute("""INSERT INTO collection_state (symbol, timeframe, last_bar_time, last_success_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(symbol, timeframe) DO UPDATE
                      SET last_bar_time=excluded.last_bar_time,
                          last_success_at=excluded.last_success_at""",
                 (symbol, timeframe, last_bar_iso, now_iso))
    conn.commit()
# open with: sqlite3.connect(path); conn.execute("PRAGMA journal_mode=WAL")
```

### 5. Empirical broker-offset validation sketch (DATA-03; refine in plan 01-02/01-03)
```python
# Locked project decision: offset validated empirically against the user's terminal.
def validate_offset(symbol: str, cfg) -> int:
    """During ACTIVE market hours only (Mon–Fri): the last tick's server time vs true UTC."""
    tick = mt5.symbol_info_tick(symbol)          # .time = last quote time (server pseudo-UTC epoch)
    tick_server = pd.to_datetime(tick.time, unit="s")
    age = datetime.now(timezone.utc).replace(tzinfo=None) - tick_server
    # live market: tick age is seconds → offset_hours = round((tick age) / 3600) adjusted:
    offset_hours = round((age.total_seconds() + 0) / 3600)
    # cross-check: newly closed M15 bars must land on :00/:15/:30/:45 server-wall boundaries,
    # and time_utc bar boundaries must align with expected session opens (report, don't hard-fail).
    return offset_hours   # persist to config/meta with validated_at timestamp
# Caveats (document in plan): run during active market (avoid weekend stale ticks);
# tick-based estimate has minute-level ambiguity — confirm with bar-boundary checks;
# re-validate at every startup; alert when configured offset != freshly validated offset.
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| pandas 2.x + pytz | pandas 3.x: pyarrow hard dep, zoneinfo default, CoW default, str dtype | 2026 (3.0 line; 3.0.5 current) | No pytz anywhere; tz ops via `tz_localize`/`tz_convert` only; pin `<4` |
| metatrader5 ~5.0.4x | 5.0.6147 (2026-08-27), cp314 wheels, win_amd64 only | Aug 2026 | Pin exact; Windows-only is a hard constraint (already satisfied) |
| datetime.utcnow() | `datetime.now(timezone.utc)` / zoneinfo | Python 3.12 era | utcnow() deprecated; use aware UTC then strip for naive comparisons |
| uv pip/virtualenv workflows | uv project mode (`uv init/add/run`) | ongoing (0.11.28 local) | Single lockfile; scripts run via `uv run` |
| CSV data stores | Parquet w/ zstd | long-standing | Locked decision already; compression trivial |

**Deprecated/outdated:**
- `pytz` in pandas context: replaced by zoneinfo as default representation [CITED: pandas 3.0 whatsnew]
- `datetime.utcnow()`: deprecated in favor of timezone-aware construction [ASSUMED: CPython 3.12 deprecation notes]
- `astype()` for tz conversion on datetime64: use `tz_localize`/`tz_convert` [CITED: pandas v2.0 whatsnew]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Most forex brokers run server time UTC+2 (winter)/UTC+3 (summer), aligned to 5pm New York daily close; DST policy may follow US or EU schedule | Pitfall 1, Code Example 5 | Medium — wrong offset shifts all UTC stamps; mitigated: empirical validation is a locked project decision and a Phase 1 task; raw `time` column preserved allows re-derivation |
| A2 | SQLite WAL + `ON CONFLICT DO UPDATE` semantics as written | Code Example 4 | Low — stdlib-documented behavior; covered by unit tests on the meta store |
| A3 | metatrader5 5.0.6147 numpy structured arrays convert cleanly to pandas 3.0.5 DataFrames on cp312 | Stack / Code Example 2 | Low — both packages verified current and cp312-compatible; a Wave-0 import/roundtrip smoke test de-risks before any collector work |
| A4 | IC Markets Global terminal is the intended feed (newest MT5 install, matching broker for forex majors); user must confirm | Pitfall 8, Open Questions | Medium — wrong terminal/account yields wrong or missing symbols; resolved by checkpoint:human-verify + symbol_select health gate |
| A5 | Broker symbol names are plain `EURUSD`/`GBPUSD`/`USDJPY` (no suffix) | Pitfall 8 | Low — symbol_select health check fails loudly with actionable message if wrong; fix is config edit |
| A6 | Forex week ≈ Sun 21–22h UTC open → Fri 21–22h UTC close; daily maintenance break varies | Pitfall 6 | Low — affects gap-report classification only (report, not crash); thresholds configurable |
| A7 | Closed MT5 bars are final (no retro revision of OHLCV after close) | Pattern 3 (keep="last" rationale) | Low — keep="last" overwrite is correct either way |
| A8 | `datetime.utcnow()` deprecation status as stated | State of the Art | Low — using `datetime.now(timezone.utc)` is correct regardless |

## Open Questions

1. **Which MT5 terminal + account is the intended data feed?**
   - What we know: two MT5 terminals installed — "MetaTrader 5 IC Markets Global" (v5.0.0.5833, `C:\Program Files\MetaTrader 5 IC Markets Global\terminal64.exe`) and "MetaTrader 5-01" (v5.0.0.4410, `C:\Program Files\MetaTrader 5-01\terminal64.exe`); neither running; several MT4 installs also present. [VERIFIED: local filesystem probe]
   - What's unclear: which terminal/account the user wants; whether saved credentials exist in that terminal (avoiding config-stored passwords).
   - Recommendation: `checkpoint:human-verify` — user starts and logs into the chosen terminal before plan 01-02 integration tasks; collector config records the exact path.
2. **What is the terminal's current "Max. bars in chart" setting, and what history depth does the broker actually serve?**
   - What we know: official default in docs' example is 5000; the setting caps everything [VERIFIED: mql5.com]. Actual user setting unknown (terminal offline).
   - Recommendation: startup health check reads `terminal_info().maxbars` and warns; DATA-05 report records it; user sets *Unlimited* if backtest depth is insufficient.
3. **Exact broker offset and its DST policy.**
   - What we know: cannot be determined offline; empirical validation is locked for Phase 1 (STATE.md).
   - Recommendation: implement validation (Code Example 5) during active market hours; persist offset + `validated_at`; re-validate each startup.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| uv | Project scaffold (01-01) | ✓ | 0.11.28 | — (none needed) |
| Python 3.12 | All plans | ✓ (via uv-managed toolchain; system py launcher 3.12.7 present) | 3.12.x | uv fetches managed CPython automatically |
| MT5 terminal (IC Markets Global or MT5-01) | Collector (01-02, 01-03), integration tests | ✗ running (✓ installed; v5.0.0.5833 / v5.0.4410) | — | None — human must start & log in (locked constraint) |
| MT5 terminal at default path | — | ✗ (both installs at non-default paths) | — | `terminal_path` config (required) |
| git | Commits | ✓ | repo present | — |
| ruff/pytest | Tests/lint | via `uv add --dev` (fetched at install time) | latest | — |
| Internet (PyPI) | Package install | ✓ (verified this session) | — | — |

**Missing dependencies with no fallback:**
- A *running, logged-in* MT5 terminal — human prerequisite, not installable by the agent. Plans 01-02/01-03 integration tasks must gate on it (checkpoint or skip-marked integration tests).

**Missing dependencies with fallback:**
- None identified. Unit-test layer is deliberately MT5-free so all non-integration work proceeds without the terminal.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (via uv dev dependency) |
| Config file | none yet — Wave 0 creates `[tool.pytest.ini_options]` in `pyproject.toml` with markers `unit`, `mt5` and default `-m "not mt5"` |
| Quick run command | `uv run pytest -q` (unit only, no MT5 needed, <30 s) |
| Full suite command | `uv run pytest -q -m "unit or mt5"` (mt5-marked tests skipped with actionable message if terminal unreachable) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DATA-01 | Health check fails loudly on: init False / `terminal_info().connected` False / `account_info()` None / `symbol_select` False; maps `last_error()` codes (-6, -4, -8) to actionable messages | unit (fake MT5) + integration smoke | `uv run pytest tests/unit/test_health_check.py -q` ; `uv run pytest -m mt5 -q` | ❌ Wave 0 |
| DATA-02 | Closed-bar fetch: `start_pos=1` excludes forming bar; numpy structured → DataFrame with expected columns/dtypes; poll boundary scheduling emits fetch after M15 close | unit (synthetic rates) | `uv run pytest tests/unit/test_fetch_and_schedule.py -q` | ❌ Wave 0 |
| DATA-03 | `time_utc = time − offset` for synthetic offsets; raw `time` preserved; offset bounds validated (±14 h); re-validation flags drift | unit (pure transform + config validation) | `uv run pytest tests/unit/test_normalize_and_config.py -q` | ❌ Wave 0 |
| DATA-04 | Idempotent merge: duplicate insert → single row; overlap refetch → no dup, later revision wins; checkpoint-driven backfill fills injected gap; atomic write (tmp+os.replace) leaves no `.tmp` on success/failure path | unit (Parquet on tmp_path) | `uv run pytest tests/unit/test_idempotent_store.py tests/unit/test_backfill.py -q` | ❌ Wave 0 |
| DATA-05 | Discovery loop stops at persistent None/-4; report rows (first/last/count/maxbars) persisted to SQLite and queryable; maxbars warning emitted when capped | unit (fake client) + integration | `uv run pytest tests/unit/test_history_report.py -q` ; `uv run pytest -m mt5 -q` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest -q` (unit suite — fast, MT5-free)
- **Per wave merge:** full `uv run pytest -q -m "unit or mt5"` (mt5 tests auto-skip when terminal down)
- **Phase gate:** full suite green + one live integration run with terminal up (human-assisted per locked constraint) before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `pyproject.toml` — project scaffold incl. `[tool.pytest.ini_options]` markers (`unit`, `mt5`), ruff config (plan 01-01)
- [ ] `tests/conftest.py` — fake MT5 client fixture + synthetic bar factory (OHLCV sanity, aligned TF boundaries)
- [ ] `tests/unit/` — five unit modules mapped above
- [ ] `src/ai_trading/mt5_client.py` importable with `MetaTrader5` absent-fake injection path (enables CI-less Windows runs)
- [ ] Wave-0 smoke: `uv run python -c "import MetaTrader5, pandas, pyarrow; print(MetaTrader5.__version__)"` on cp312 (de-risks assumption A3 before collector tasks)

## Security Domain

> `security_enforcement: true`, ASVS level 1, block-on high (config.json).

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | partial (no user auth surface; broker credentials only) | Prefer terminal-saved credentials (omit login/password/server → package uses saved terminal credentials per docs [VERIFIED: mql5.com initialize]); if config credentials needed, keep in gitignored `config.local.toml` or env vars |
| V3 Session Management | no | N/A — no user sessions in this phase |
| V4 Access Control | no | N/A — single-user local process |
| V5 Input Validation | yes | Config dataclass validation: symbol whitelist regex, timeframe enum, offset bounds (−14…+14 h), path existence, numeric ranges; fail fast at startup |
| V6 Cryptography | no | N/A — no crypto in this phase (never hand-roll any, ever) |
| V7 Errors & Logging | yes | Actionable error messages (requirement), but never log initialize parameters/credentials; log `last_error()` codes + config paths only |
| V14 Config | yes | `data/` and `config.local.toml` in `.gitignore`; committed `config.toml` contains no secrets |

### Known Threat Patterns for {local Python collector stack}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Credential leakage via logs/config/exceptions | Information Disclosure | Omit credentials (terminal-saved auth); scrub exception text; gitignore local config; no `print(cfg)` dumps |
| Bar-data corruption/tampering (partial writes, disk issues) | Tampering | Atomic temp+`os.replace` writes; monotonic-time + row-count invariants on write; SQLite transactions for checkpoints |
| Silent data gaps (availability of the *evidence*) | Denial of Service (data) | Gap list persisted + reported (not crash); restart backfill idempotent; health surface includes last-bar age |
| Wrong-feed substitution (connects to unexpected terminal) | Spoofing | Required `terminal_path` config + startup assertion on `account_info().server` |
| Path traversal / arbitrary paths from config | Elevation | Config paths validated to exist and resolve under expected roots; no user-supplied web input exists in this phase |

## Sources

### Primary (HIGH confidence — official docs fetched directly this session)
- mql5.com/en/docs/integration/python_metatrader5 — function index; `initialize`, `copy_rates_from_pos`, `copy_rates_range`, `terminal_info`, `symbol_select`, `last_error`, `account_info` pages (exact signatures, return formats, notes, error-code table) [VERIFIED: mql5.com]
- mql5.com/en/docs/series/copyrates — history synchronization, TERMINAL_MAXBARS/-1 semantics, interval inclusivity [VERIFIED: mql5.com]
- mql5.com/en/docs/dateandtime/timecurrent — server-formed time semantics [VERIFIED: mql5.com]
- pypi.org/project/MetaTrader5 (+ JSON API) — version 5.0.6147, publisher metaquotes, MIT, cp312 win_amd64 wheel, docs URL, release history [VERIFIED: PyPI]
- pandas.pydata.org/docs/whatsnew/v3.0.0.html — pyarrow dependency, zoneinfo, CoW, string dtype [VERIFIED: pandas docs]
- Local filesystem/registry probes — MT5 install paths, versions, running-state [VERIFIED: local]

### Secondary (MEDIUM confidence)
- pypistats.org API — download volumes for legitimacy audit [VERIFIED: pypistats]
- Context7 /websites/pandas_pydata — tz_localize semantics; pandas v2.0 whatsnew via Context7 (tz conversion rules) [CITED: pandas docs]
- Context7 /ariadng/metatrader-mcp-server — corroborating bar-column list (wrapper repo, not authoritative)

### Tertiary (LOW confidence — flagged for in-phase validation)
- Broker offset conventions (UTC+2/+3, DST alignment) — community consensus from training data; search engines unavailable this session; made safe by empirical-validation design [ASSUMED]
- SQLite WAL/UPSERT operational details — stdlib knowledge, unit-tested in-phase [ASSUMED]

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every package version verified against PyPI/pypistats this session; no training-data versions used
- MT5 API & time semantics: HIGH — verified against official MetaQuotes docs fetched directly (unusually good provenance given search-engine outage)
- Architecture/patterns: MEDIUM-HIGH — patterns derive from verified API constraints; storage-scale reasoning [ASSUMED] volume estimates
- Pitfalls: HIGH for time/maxbars/sync pitfalls (doc-verified); MEDIUM for offset/DST and session conventions (in-phase validation by design)
- Environment: HIGH — probed directly; the one gap (terminal not running) is a locked human prerequisite, not an unknown

**Research date:** 2026-08-30
**Valid until:** 2026-09-29 (stable local stack; metatrader5/pandas release cadence noted — re-verify pins if >30 days elapse)
