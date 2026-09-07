# Phase 1: Data Foundation - Pattern Map

**Mapped:** 2026-08-30
**Files classified:** 20 (19 classification rows; includes the two `__init__.py` package markers implied by the research structure)
**Analogs found:** 0 / 20 — **greenfield repository**

> **GREENFIELD NOTICE (read first):** The repository `D:\Git\AI-Trading` contains only `.git/` and `.planning/` — verified by directory listing this session. There is **no source code in this repo**, so **no in-repo analog exists for any file**. Nothing below is quoted from project source code.
>
> All concrete excerpts in this document are quoted **verbatim from `.planning/phases/01-data-foundation/01-RESEARCH.md`**, which verified each against official sources this session (mql5.com MT5 Python API docs, pandas 3.x whatsnew/docs, SQLite stdlib semantics, PyPI). Treat `01-RESEARCH.md <line range>` as the analog "file:lines" for every assignment. The planner should copy these excerpts into plan actions as the pattern-of-record.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `pyproject.toml` | config (project/tooling: deps, pytest markers, ruff) | n/a | none — greenfield | — |
| `config.toml` | config (runtime inputs: symbols, TFs, terminal_path, offset, paths) | n/a | none — greenfield | — |
| `config.local.toml` | config (gitignored overrides; optional MT5 credentials) | n/a | none — greenfield | — |
| `.gitignore` | config (VCS policy) | n/a | none — greenfield | — |
| `src/ai_trading/__init__.py`, `src/ai_trading/stores/__init__.py` | package markers | n/a | none — greenfield | — |
| `src/ai_trading/config.py` | config loader + validator (utility) | transform | none — greenfield | — |
| `src/ai_trading/mt5_client.py` | adapter (external-process IPC bridge, thin wrapper) | request-response | none — greenfield | — |
| `src/ai_trading/normalize.py` | pure transform utility (single tz source of truth) | transform | none — greenfield | — |
| `src/ai_trading/stores/bar_store.py` | storage (Parquet per symbol×TF) | file-I/O CRUD (read/merge/atomic-rewrite) | none — greenfield | — |
| `src/ai_trading/stores/meta_store.py` | storage (SQLite WAL: checkpoints, history bounds) | CRUD (upsert/query, transactional) | none — greenfield | — |
| `src/ai_trading/collector.py` | service (orchestration: health, offset check, backfill, poll loop) | event-driven (time-triggered poll) + batch (backfill) | none — greenfield | — |
| `src/ai_trading/history_report.py` | service + CLI reporter (DATA-05) | batch discovery → persistence/query | none — greenfield | — |
| `tests/conftest.py` | test fixtures (fake MT5 client, synthetic bar factory) | transform/factory | none — greenfield | — |
| `tests/unit/test_health_check.py` | test (unit) | request-response | none — greenfield | — |
| `tests/unit/test_fetch_and_schedule.py` | test (unit) | request-response + event-driven | none — greenfield | — |
| `tests/unit/test_normalize_and_config.py` | test (unit) | transform | none — greenfield | — |
| `tests/unit/test_idempotent_store.py` | test (unit) | file-I/O CRUD | none — greenfield | — |
| `tests/unit/test_backfill.py` | test (unit) | batch | none — greenfield | — |
| `tests/unit/test_history_report.py` | test (unit) | batch | none — greenfield | — |
| `tests/integration/*` (`mt5`-marked) | test (integration, requires running terminal) | request-response | none — greenfield | — |

**Provenance of the file list:** RESEARCH.md "Recommended Project Structure" (lines 170–190) defines the source layout; RESEARCH.md "Phase Requirements → Test Map" (lines 520–539) defines `tests/conftest.py`, the five unit modules, and the `mt5`-marked integration layer; ROADMAP.md plans 01-01/01-02/01-03 (lines 36–38) group the same files by plan. No CONTEXT.md exists for this phase; user constraints were taken from STATE.md/PROJECT.md as summarized in RESEARCH.md lines 17–38.

## Pattern Assignments

Since no in-repo analog exists, each assignment names the **verified external pattern** to copy and its exact location in `01-RESEARCH.md`. Excerpts are quoted verbatim.

### `src/ai_trading/mt5_client.py` (adapter, request-response)

**Analog:** none (greenfield).
**Copy from:** RESEARCH.md Architecture Pattern 1 "Thin MT5 Adapter (import-swap testability)", lines 192–212.

**Core adapter pattern** (RESEARCH.md lines 199–212):
```python
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

**Rules to carry over:** `import MetaTrader5 as mt5` must appear in exactly one place in the codebase; every other module goes through this wrapper. Tests inject a fake exposing the same function surface (this fake becomes the `tests/conftest.py` fixture). RESEARCH.md line 538 requires the fake-injection path to work with the real package importable — keep the wrapper importable even when the terminal is absent.

---

### `src/ai_trading/collector.py` (service, event-driven poll + batch backfill)

**Analog:** none (greenfield).
**Copy from:** RESEARCH.md Code Example 1 "Startup health check with actionable failures" (DATA-01), lines 328–359; Code Example 3 "Retry-until-stable range fetch", lines 382–404; Architecture Pattern 2 "Closed-bar polling on boundary + delay", lines 214–222; Pattern 5 "Checkpoint-driven restart", lines 248–250.

**Health-check pattern** (RESEARCH.md lines 337–359):
```python
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

**Closed-bar fetch call** (RESEARCH.md line 220 — the one-line rule that must never regress):
```python
# closed bars only — the forming bar at start_pos=0 must never be stored
rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 1, lookback)
```

**Retry-until-stable backfill loop** (RESEARCH.md lines 388–403):
```python
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
```

**Checkpoint-driven restart semantics** (RESEARCH.md lines 248–250, condensed): after every successful write, SQLite records `last_bar_time` per (symbol, TF) in one UPSERT transaction; on start, backfill range = `(last_bar_time, now]`; overlap is harmless because the merge is idempotent; the checkpoint is the *only* restart state.

---

### `src/ai_trading/normalize.py` (utility, pure transform)

**Analog:** none (greenfield).
**Copy from:** RESEARCH.md Code Example 2, lines 361–380 (transform core); Pitfall 1, lines 280–283 (time-semantics rules); Code Example 5, lines 433–449 (offset-validation helper).

**Transform core** (RESEARCH.md lines 370–379 — the normalize portion is decisive):
```python
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
(The fetch call itself belongs to `mt5_client`/`collector`; `normalize.py` owns the `pd.to_datetime(unit="s")` → `time_utc = time − offset` math as pure DataFrame functions.)

**Offset-validation helper** (RESEARCH.md lines 436–449):
```python
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
```

**Hard rules to copy** (RESEARCH.md Pitfall 1, lines 280–283 + Pitfall 7, lines 315–318): raw `time` column is preserved as server wall time (locked by success criterion 2); `time_utc = time − offset` only; **never** `tz_localize` broker times to an IANA zone; all tz work lives in this one module; pandas 3.x only — `tz_localize`/`tz_convert`, never `astype('datetime64[ns, UTC]')`, no pytz, `datetime.now(timezone.utc)` not deprecated `utcnow()`.

---

### `src/ai_trading/stores/bar_store.py` (storage, file-I/O CRUD)

**Analog:** none (greenfield).
**Copy from:** RESEARCH.md Architecture Pattern 3 "Idempotent merge + atomic file replace", lines 223–242; Pitfall 4 (closed-bar invariant), lines 298–302.

**Core merge + atomic-write pattern** (RESEARCH.md lines 228–241):
```python
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

**Invariants to copy:** dedup keyed on exact bar-open `time` with `keep="last"` (refetched bar overwrites); one Parquet file per (symbol, TF), whole-file atomic rewrite (temp file in same directory + `os.replace`) — never per-row appends or delete-then-write (RESEARCH.md "Don't Hand-Roll" line 267); on the write path, assert `max(time_utc) < now_utc_floor(timeframe)` so the forming bar can never be persisted (Pitfall 4 "How to avoid", line 301); file layout `data/bars/{SYMBOL}_{TF}.parquet` (line 157).

---

### `src/ai_trading/stores/meta_store.py` (storage, CRUD)

**Analog:** none (greenfield).
**Copy from:** RESEARCH.md Code Example 4 "SQLite checkpoint UPSERT", lines 406–431.

**DDL + UPSERT pattern** (RESEARCH.md lines 410–430):
```python
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

**Rules to copy:** WAL journal mode at connection open; parameterized SQL only; one UPSERT-per-write transaction (checkpoint commit happens *after* the Parquet write succeeds — Pattern 5, lines 248–250); schema keys are (symbol, timeframe) throughout.

---

### `src/ai_trading/config.py` (config loader + validator, transform)

**Analog:** none (greenfield).
**Copy from:** RESEARCH.md "Don't Hand-Roll" config row, line 268; Security V5 input-validation row, line 552; V14 row, line 555; offset bounds from test map line 525.

**Pattern to establish:** `tomllib` (stdlib) load of `config.toml` + `config.local.toml` overrides into a dataclass with explicit field validation, failing fast at startup. Required fields per research: `symbols` (EURUSD/GBPUSD/USDJPY whitelist), `timeframes` (M15/H1/H4 enum), `terminal_path` (required, must exist — Pitfall 8 mitigation, line 323: never let `initialize()` find its own terminal), `broker_offset_hours` + `validated_at` (bounds ±14 h per test map line 525), data paths (`data/bars/`, `data/meta/`), `min_maxbars`. Validate paths resolve under expected roots; never `print(cfg)` dumps (Security threat table, line 561).

---

### `src/ai_trading/history_report.py` (service + CLI, batch → persistence/query)

**Analog:** none (greenfield).
**Copy from:** RESEARCH.md Code Example 3 walk-back note, lines 402–403; Code Example 4 `history_bounds` DDL, lines 418–420; Pitfall 2, lines 285–290 (maxbars provenance); Pitfall 6, lines 309–313 (gap handling).

**Pattern to establish:** per (symbol, TF), walk `date_from` backward in chunks using the retry-until-stable fetcher; a persistent `None` + code `-4` marks the true start of available history or the `maxbars` cap — record both:
```python
# DATA-05 walk-back: step date_from backward in 1-year chunks; a persistent None
# marks the true start of available history (or the maxbars cap) — record both.
```
(RESEARCH.md lines 402–403)
Persist rows `(first_bar_utc, last_bar_utc, bar_count, terminal_maxbars, fetched_at)` into the SQLite `history_bounds` table (DDL quoted under `meta_store.py` above); compute a `gap` list as aligned-TF holes inside `[first_bar, last_bar]` and **report, never crash** on weekend/holiday gaps (Pitfall 6); the report must always include `terminal_maxbars` provenance (Pitfall 2).

---

### `pyproject.toml`, `config.toml`, `config.local.toml`, `.gitignore` (config files)

**Analog:** none (greenfield).
**Copy from:** RESEARCH.md Installation block, lines 93–98; structure comments, lines 173–175, 189; pytest config, line 516; Security V14, line 555; STATE/PROJECT locked stack, lines 23–27.

**Established inputs:**
```bash
uv init --python 3.12   # plan 01-01 scaffold (or manual pyproject.toml)
uv add "metatrader5==5.0.6147" "pandas>=3.0,<4" pyarrow
uv add --dev pytest ruff
```
(RESEARCH.md lines 94–98)
- `pyproject.toml` must include `[tool.pytest.ini_options]` with markers `unit`, `mt5` and default `-m "not mt5"` (RESEARCH.md lines 516–518), plus `[tool.ruff]` config (line 535).
- `config.toml` (committed) contains **no secrets**; `config.local.toml` (gitignored) holds path overrides and optional MT5 login/password; `data/` (runtime Parquet/SQLite artifacts) is gitignored (RESEARCH.md lines 174–175, 189; Security V14 line 555).
- Pinned stack is user-locked: Python 3.12, `metatrader5==5.0.6147`, `pandas>=3.0,<4`, pyarrow, uv, ruff, pytest (RESEARCH.md lines 23, 69–75).

---

### Test files: `tests/conftest.py`, `tests/unit/*`, `tests/integration/*` (test role)

**Analog:** none (greenfield).
**Copy from:** RESEARCH.md Validation Architecture, lines 510–539; test map lines 522–527.

**Structure to copy:** `tests/conftest.py` provides the fake MT5 client fixture (same surface as `mt5_client.py`) plus a synthetic bar factory with OHLCV sanity and TF-boundary alignment (lines 536, 525). Unit tests run with zero MT5 dependency — default `uv run pytest -q` is MT5-free and <30 s (lines 516–518, 530). Integration tests carry the `mt5` marker and are skipped with an actionable message when the terminal is unreachable (lines 518, 505). Per-requirement mapping: DATA-01→`test_health_check.py`, DATA-02→`test_fetch_and_schedule.py`, DATA-03→`test_normalize_and_config.py`, DATA-04→`test_idempotent_store.py` + `test_backfill.py`, DATA-05→`test_history_report.py` (lines 523–527).

---

## Shared Patterns

These cross-cutting patterns apply to multiple files above; each is established fresh in this phase (no existing implementation to extend).

### 1. Error taxonomy + actionable messages
**Source:** RESEARCH.md Code Example 1 (lines 329–359), Code Example 2 (line 374), Code Example 3 (lines 394–401); error-code constants lines 333–335.
**Apply to:** `mt5_client.py`, `collector.py`, `history_report.py`, and the tests that exercise them.
```python
AUTH_FAILED = -6          # RES_E_AUTH_FAILED: terminal up, account not authorized
NO_HISTORY = -4           # RES_E_NOT_FOUND: no history / not ready
AUTO_TRADING_DISABLED = -8
```
Two exception types (`MT5ConnectionError`, `MT5DataError`); every failure message embeds `[code: msg]` **and** tells the user what to do next (which setting, which login, which symbol suffix). `None` from copy-rates with code `-4` is a retry/stop-walk signal, never a crash (Anti-Pattern, line 255).

### 2. Closed-bars-only invariant
**Source:** RESEARCH.md Pattern 2 (lines 217–221), Pitfall 4 (lines 298–302).
**Apply to:** `mt5_client.py` (fetch), `collector.py` (poll), `bar_store.py` (write-path assertion), `tests/conftest.py` (factory must emit closed bars).
```python
rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 1, lookback)   # pos=1, never 0
```

### 3. UTC normalization discipline (single source of truth)
**Source:** RESEARCH.md Pitfall 1 (lines 280–283), Code Example 2 (lines 376–377), Pitfall 7 (lines 315–318).
**Apply to:** `normalize.py` owns all of it; `config.py` supplies the validated offset; every consumer reads the two columns (`time` raw preserved, `time_utc` derived). The offset is empirically validated config, never an IANA zone guess (Anti-Pattern, line 253).

### 4. Atomic write + idempotent merge
**Source:** RESEARCH.md Pattern 3 (lines 227–242), "Don't Hand-Roll" rows (lines 265–267).
**Apply to:** `bar_store.py`; any future file persistence in later phases reuses the same temp + `os.replace` discipline.

### 5. Checkpoint UPSERT as the only restart state
**Source:** RESEARCH.md Pattern 5 (lines 248–250), Code Example 4 (lines 410–430).
**Apply to:** `meta_store.py` (schema + UPSERT), `collector.py` (write-then-checkpoint ordering), `history_report.py` (reads/writes `history_bounds`).

### 6. Credential & config hygiene (ASVS V7/V14)
**Source:** RESEARCH.md Anti-Pattern line 258 ("Logging credentials"); Security table lines 549, 554–555; Pitfall 8 mitigation (lines 322–323); threat table line 561.
**Apply to:** `config.py`, `mt5_client.py`, `collector.py`.
Prefer terminal-saved credentials (omit login/password/server); if credentials are needed they live only in gitignored `config.local.toml` or env vars; `initialize()` parameters must never appear in logs, exceptions, or `print` output; assert `account_info().server` matches config to prevent connecting to the wrong terminal (two MT5 installs exist on this machine).

### 7. Test layering & markers
**Source:** RESEARCH.md lines 516–518, 530–532, 536–538.
**Apply to:** `pyproject.toml`, `tests/conftest.py`, all test modules.
Default run (`uv run pytest -q`) is unit-only and MT5-free; `mt5`-marked integration tests auto-skip with an actionable message when the terminal is down; sampling = unit suite per task commit, full suite (`-m "unit or mt5"`) per wave merge.

## No Analog Found

**All 20 files are greenfield** — the repository contains no source code (verified: `D:\Git\AI-Trading` holds only `.git/` and `.planning/`; no `*.py`, `*.toml`, or config files exist anywhere outside `.planning/`).

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| *(every file in the File Classification table above)* | — | — | Greenfield repository — zero existing source files; no in-repo analog can exist |

**Planner instruction:** for each file, use the RESEARCH.md pattern/code-example cited in its Pattern Assignment above as the copy-from source. Do not look for existing code to imitate — there is none; the risk to guard against is *inconsistency between the new files*, which the Shared Patterns section (§1–§7) exists to prevent.

## Metadata

**Analog search scope:** entire repository `D:\Git\AI-Trading` (all files and directories)
**Files scanned:** 21 planning/repo entries inspected (`.planning/` docs + phase artifacts); **0 source files exist** in the repo
**Pattern extraction date:** 2026-08-30
**External pattern provenance:** 100% of excerpts originate from `01-RESEARCH.md`, which verified them this session against: mql5.com official MT5 Python integration docs (`initialize`, `copy_rates_from_pos`, `copy_rates_range`, `terminal_info`, `symbol_select`, `last_error`, `account_info`, CopyRates notes, TimeCurrent), pandas 3.x whatsnew/docs, SQLite stdlib semantics, and PyPI/pypistats-verified package versions.
