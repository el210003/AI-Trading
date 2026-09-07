---
phase: 01-data-foundation
plan: 01
subsystem: infra
tags: [mt5, parquet, sqlite, timezone, uv, pytest, greenfield]

requires: []
provides:
  - "uv-managed Python 3.12 project (pyproject + uv.lock, pinned metatrader5==5.0.6147/pandas>=3,<4/pyarrow, pytest+ruff dev deps)"
  - "ai_trading.config.load_config → frozen 15-field Config with fail-fast validation (symbols regex, TF subset, ±14h broker_offset_hours, terminal_path must exist)"
  - "ai_trading.normalize: COLUMNS, TIMEFRAME_MINUTES, rates_to_dataframe (raw server time preserved + time_utc), floor_to_timeframe, assert_closed_bars — zero MetaTrader5 import"
  - "ai_trading.stores.bar_store: bar_path/read_bars/merge_and_write (atomic tmp+os.replace, dedup on raw bar-open time keep='last', forming-bar guard) — the single Parquet write path"
  - "ai_trading.stores.meta_store: WAL SQLite, collection_state/history_bounds/bar_gaps DDL + parameterized UPSERT/query helpers — the only restart/report state"
  - "tests/conftest.py make_bars synthetic bar factory + 3 green unit modules (MT5-free)"
affects: [01-02-collector, 01-03-backfill-report, phase-2-smc, phase-3-backtester]

tech-stack:
  added: [uv, metatrader5 5.0.6147, pandas 3.0.5, pyarrow 25.0.1, pytest 9.1.1, ruff 0.16.5, numpy 2.5.2]
  patterns:
    - "tomllib + shallow local-override merge + frozen dataclass validation"
    - "pure-function tz normalization (no IANA localization of broker time)"
    - "atomic whole-file Parquet rewrite (temp + os.replace)"
    - "SQLite WAL + UPSERT as sole restart state"
    - "unit/mt5 pytest markers with default '-m \"not mt5\"'"

key-files:
  created:
    - pyproject.toml
    - .python-version
    - uv.lock
    - .gitignore
    - config.toml
    - config.local.toml
    - src/ai_trading/__init__.py
    - src/ai_trading/stores/__init__.py
    - src/ai_trading/config.py
    - src/ai_trading/normalize.py
    - src/ai_trading/stores/bar_store.py
    - src/ai_trading/stores/meta_store.py
    - tests/conftest.py
    - tests/unit/test_scaffold.py
    - tests/unit/test_normalize_and_config.py
    - tests/unit/test_idempotent_store.py
  modified: []

key-decisions:
  - "normalize.py stub (COLUMNS + TIMEFRAME_MINUTES) created during Task 2 as the plan's sanctioned fallback so conftest imports resolve before Task 3 fills the module"
  - "symbol regex ^[A-Z]{6}(\\.[A-Za-z0-9]+)?$ deliberately widens research assumption A5 to accept broker-suffixed names (plan 01-02 writes human-confirmed suffixed config)"
  - "assert_closed_bars strips tz from an aware now_utc before comparing against naive time_utc (aware-UTC-then-strip rule)"
  - "merge_and_write cleans up its .tmp file on write failure, not only on success (research test map: no .tmp on success OR failure path)"

requirements-completed: [DATA-03, DATA-04]

coverage:
  - id: D1
    description: "uv project scaffold: pinned deps, pytest markers (unit/mt5) with default mt5 exclusion, ruff config, gitignore rules protecting data/ and config.local.toml, uv.lock committed"
    requirement: "DATA-03"
    verification:
      - kind: unit
        ref: tests/unit/test_scaffold.py#test_pytest_markers_declared_and_mt5_excluded_by_default
        status: pass
      - kind: unit
        ref: tests/unit/test_scaffold.py#test_core_libraries_import_and_report_versions
        status: pass
      - kind: other
        ref: "uv run pytest -q (35 passed, MT5-free)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Wave-0 smoke: MetaTrader5/pandas/pyarrow import cleanly on the uv-managed cp312 (de-risks research assumption A3)"
    verification:
      - kind: other
        ref: "uv run python -c 'import MetaTrader5, pandas, pyarrow' -> smoke-ok, MetaTrader5.__version__ == 5.0.6147"
        status: pass
    human_judgment: false
  - id: D3
    description: "Config loader/validator: offset bounds ±14, plain+suffixed symbol acceptance, malformed symbol rejection, terminal_path must exist, empty validated_at warns without failing (DATA-03)"
    requirement: "DATA-03"
    verification:
      - kind: unit
        ref: tests/unit/test_normalize_and_config.py#(22 tests, offset/symbol/terminal/validation matrix)
        status: pass
    human_judgment: false
  - id: D4
    description: "UTC normalization: rates_to_dataframe maps server 2026-08-29 00:00 (offset 3) -> time_utc 2026-08-28 21:00, preserves raw time, exact COLUMNS order, naive dtypes (DATA-03)"
    requirement: "DATA-03"
    verification:
      - kind: unit
        ref: tests/unit/test_normalize_and_config.py#test_offset_three_maps_server_wall_to_true_utc
        status: pass
      - kind: unit
        ref: tests/unit/test_normalize_and_config.py#test_output_columns_are_exactly_c_columns_and_naive
        status: pass
    human_judgment: false
  - id: D5
    description: "Bar store: idempotent under duplicate writes, overlap refetch revision wins (keep='last'), sorted, atomic tmp+os.replace with no .tmp residue, forming-bar guard raises ValueError (DATA-04)"
    requirement: "DATA-04"
    verification:
      - kind: unit
        ref: tests/unit/test_idempotent_store.py#(bar-store tests incl. overlap-revision and forming-bar guard)
        status: pass
    human_judgment: false
  - id: D6
    description: "Meta store: WAL journal mode, checkpoint UPSERT roundtrip with exactly one row per (symbol, timeframe), history_bounds incl. terminal_maxbars provenance, gap insert-or-replace without duplicates (DATA-04)"
    requirement: "DATA-04"
    verification:
      - kind: unit
        ref: tests/unit/test_idempotent_store.py#(meta-store tests)
        status: pass
    human_judgment: false
  - id: D7
    description: "metatrader5 vendor-binary install gated by human legitimacy approval (T-1-SC)"
    verification: []
    human_judgment: true
    rationale: "Package legitimacy of a vendor binary is a human trust decision; the blocking-human checkpoint was resolved explicitly by the user's 'approved' response via the orchestrator before any install command ran."

duration: 11min
completed: 2026-08-29
status: complete
---

# Phase 1 Plan 01: Data Foundation Scaffold Summary

**uv-managed Python 3.12 project with fail-fast validated config (±14h broker offset), pure UTC normalization preserving raw server-wall time, and idempotent crash-safe storage — atomic Parquet bars + SQLite WAL checkpoints/bounds/gaps — all 35 unit tests green with zero MT5 dependency.**

## Performance

- **Duration:** 11 min (continuation agent; Task 1 gate resolved in prior session)
- **Started:** 2026-08-29T23:45:10Z
- **Completed:** 2026-08-29T23:56:11Z
- **Tasks:** 4 (Task 1 = legitimacy checkpoint approved in prior session; Tasks 2–4 executed here)
- **Files modified:** 16 (15 committed + gitignored config.local.toml)

## Accomplishments

- **Legitimacy gate (Task 1):** Human explicitly approved installing `metatrader5==5.0.6147` (MetaQuotes vendor binary) via the orchestrator's blocking-human checkpoint before any `uv add` referencing it ran — satisfying the T-1-SC mitigation verbatim.
- **Wave-0 scaffold (Task 2):** `uv init --bare --python 3.12` + exact pyproject state (hatchling src-layout, pytest `unit`/`mt5` markers with default `-m "not mt5"`, ruff E/F/I/UP/B); pinned installs (pandas 3.0.5, pyarrow 25.0.1, pytest 9.1.1, ruff 0.16.5); `.gitignore` protects `data/` + `config.local.toml` while uv.lock is committed; Wave-0 smoke confirmed `import MetaTrader5, pandas, pyarrow` on cp312 with `MetaTrader5.__version__ == 5.0.6147` (assumption A3 de-risked).
- **DATA-03 foundation (Task 3):** `load_config()` (tomllib + shallow local-override merge) into a frozen 15-field `Config`; every validation violation raises `ValueError` naming the field (offset −14..14, symbol regex accepting `EURUSD` and `EURUSD.a`, terminal_path must exist per Pitfall 8, numeric bounds); empty `validated_at` logs "broker offset not yet validated" without failing. `normalize.py` owns all time math as pure functions — raw `time` preserved, `time_utc = time − offset`, no IANA localization, no MetaTrader5 import.
- **DATA-04 foundation (Task 4):** `bar_store.merge_and_write` — the single Parquet write path — implements concat + `drop_duplicates(subset=["time"], keep="last")` + sort + same-directory `.tmp` + `os.replace` atomic swap (with `.tmp` cleanup even on failure), guarded by the forming-bar invariant. `meta_store` provides WAL-mode connection and parameterized UPSERT/query helpers over `collection_state`, `history_bounds`, and `bar_gaps`.
- **Verification:** `uv run pytest -q` → 35 passed in 0.37 s (MT5-free); `uv run pytest -q -m "unit or mt5"` → 35 passed; `uv run ruff check .` → clean; root `load_config()` loads the real config.toml/config.local.toml pair (IC Markets Global terminal path verified on disk).

## Task Commits

Each task was committed atomically:

1. **Task 1: Confirm metatrader5 package legitimacy** — gate task, no commit (resolved in prior session; human "approved" recorded in STATE.md session continuity and this summary)
2. **Task 2: uv scaffold + Wave-0 test infra** — `d6d4e7c` (feat)
3. **Task 3: Config loader/validator + UTC normalization** — `d4299be` (feat)
4. **Task 4: Parquet bar store + SQLite WAL meta store** — `fb12970` (feat)

**Plan metadata:** (this docs commit)

## Files Created/Modified

- `pyproject.toml`, `.python-version`, `uv.lock` — uv project, pinned stack, pytest markers, ruff config (lockfile committed per plan)
- `.gitignore` — env/build caches + `data/` + `config.local.toml`
- `config.toml` — committed defaults, no secrets (terminal_path empty → must be overridden)
- `config.local.toml` — gitignored; active `terminal_path` = verified IC Markets Global install, commented alternative, no credentials
- `src/ai_trading/__init__.py`, `src/ai_trading/stores/__init__.py` — package markers
- `src/ai_trading/config.py` — `Config` dataclass + `load_config()` fail-fast validation
- `src/ai_trading/normalize.py` — COLUMNS, TIMEFRAME_MINUTES, `rates_to_dataframe`, `floor_to_timeframe`, `assert_closed_bars`
- `src/ai_trading/stores/bar_store.py` — `bar_path`, `read_bars`, `merge_and_write` (atomic + idempotent + forming-bar guard)
- `src/ai_trading/stores/meta_store.py` — WAL connect, DDL (3 tables), checkpoint/bounds/gap helpers
- `tests/conftest.py` — `make_bars` factory (TF-aligned, OHLC-sane, offset-aware)
- `tests/unit/test_scaffold.py`, `tests/unit/test_normalize_and_config.py`, `tests/unit/test_idempotent_store.py` — 35 unit tests

## Decisions Made

- Created the minimal `normalize.py` stub (COLUMNS + TIMEFRAME_MINUTES) during Task 2 exactly as the plan's sanctioned fallback, so conftest's import resolves and the Wave-0 suite is self-contained; Task 3 replaced it with the full pure implementation.
- Symbol validation accepts optional `.broker` suffixes (deliberate widening of assumption A5; plan 01-02 Task 1 writes human-confirmed suffixed names, `symbol_select` remains the loud downstream check).
- `assert_closed_bars` converts an aware `now_utc` to UTC and strips tz before comparing against naive `time_utc` — broker columns stay naive; tz arithmetic only ever touches non-broker clocks.
- `merge_and_write` deletes its `.tmp` if the Parquet write raises, keeping the "no `.tmp` on failure path" promise from the research test map (plan text only demanded the success path).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] B905 `zip()` without `strict=` in make_bars**
- **Found during:** Task 2 (scaffold lint gate)
- **Issue:** `uv run ruff check .` failed with two B905 violations in the new conftest factory
- **Fix:** Added `strict=True` to both `zip()` calls
- **Files modified:** tests/conftest.py
- **Verification:** `uv run ruff check .` exits 0
- **Committed in:** d6d4e7c (part of Task 2 commit)

**2. [Rule 2 - Missing Critical] `.tmp` cleanup on failed Parquet writes**
- **Found during:** Task 4 (bar_store implementation)
- **Issue:** Plan required "no .tmp remains on the success path"; RESEARCH/VALIDATION test map (DATA-04) additionally requires no `.tmp` on the *failure* path for crash-safety
- **Fix:** Wrapped `to_parquet`/`os.replace` in try/except that unlinks the `.tmp` and re-raises
- **Files modified:** src/ai_trading/stores/bar_store.py
- **Verification:** No `*.tmp` files on disk after runs; forming-bar failure test leaves no residue
- **Committed in:** fb12970 (part of Task 4 commit)

**3. [Rule 1 - Lint] Line-length / modernization wraps (E501, UP017, UP045)**
- **Found during:** Tasks 3–4 (lint gate is part of plan `<verification>`)
- **Issue:** 8 lint findings in new source (long f-string/messages, `timezone.utc` → `UTC` alias, `Optional[X]` → `X | None`)
- **Fix:** Wrapped messages, applied safe auto-fixes
- **Files modified:** src/ai_trading/config.py, src/ai_trading/normalize.py, src/ai_trading/stores/meta_store.py, src/ai_trading/stores/bar_store.py, tests/unit/test_normalize_and_config.py
- **Verification:** `uv run ruff check .` exits 0 with all 35 tests still green
- **Committed in:** d4299be, fb12970

---

**Total deviations:** 3 auto-fixed (2 lint-correctness, 1 missing-critical robustness). **Impact on plan:** None behavioral — all fixes were required by the plan's own ruff verification gate or by the research validation contract; no scope creep.

## Authentication Gates

None encountered. The package-legitimacy gate (Task 1, `gate="blocking-human"`) was resolved by explicit human approval ("approved") via the orchestrator checkpoint flow **before** this continuation agent ran any install command — no `uv add` referencing metatrader5 appears in the transcript prior to that approval.

## Issues Encountered

- `uv init --bare --python 3.12 .` did not write `.python-version` in this uv version — created it manually (plan step 1 permits manual scaffolding adjustments).
- Plan-level `ruff format --check` is not part of the plan's verification (`ruff check` is); 8 files would be reformatted stylistically. Left as-is deliberately — running `ruff format` would churn committed files beyond the plan's stated gate. Consider adding a format pass in a later housekeeping plan if desired.

## Security Compliance (threat register)

- **T-1-SC (mitigate):** ✅ blocking-human legitimacy checkpoint resolved before install; exact version pins; `uv add` only.
- **T-1-01 (mitigate):** ✅ config.toml has no credential fields; config.local.toml gitignored from Task 2 onward; Config never printed/repr'd (warning messages carry no config dump).
- **T-1-02 (mitigate):** ✅ temp+os.replace atomic swap, dedup+sort before write, forming-bar guard on the write path.
- **T-1-03 (mitigate):** ✅ terminal_path validated non-empty and existing at load; no web/user input in this phase.

## User Setup Required

None — no external service configuration required. (Terminal path/selection UAT arrives at plan 01-02's own checkpoint.)

## Next Phase Readiness

- **01-02 (collector) is unblocked** for all pure work: it can import `load_config`, `normalize.rates_to_dataframe`, `bar_store.merge_and_write`, and `meta_store` helpers without the terminal; its integration checkpoint still requires the human to start + log into the chosen MT5 terminal and set "Max. bars in chart".
- `config.local.toml` pre-fills the IC Markets Global path with the 5-01 alternative commented; plan 01-02 Task 1 makes the final choice. `validated_at` is intentionally empty and warns on load until plan 01-02 validates the offset empirically.
- `wave_0_complete` in 01-VALIDATION.md can now flip to true (pytest config + conftest factory + scaffold test module all landed).

## Self-Check: PASSED

- All 15 committed key-files verified present on disk; `config.local.toml` verified present + gitignored.
- Task commits verified in `git log`: `d6d4e7c`, `d4299be`, `fb12970`.
- Verification commands re-confirmed: `uv run pytest -q` → 35 passed; `uv run pytest -q -m "unit or mt5"` → 35 passed; `uv run ruff check .` → clean; Wave-0 smoke → `smoke-ok`, MetaTrader5 5.0.6147.
