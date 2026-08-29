---
phase: 1
slug: data-foundation
status: ready
nyquist_compliant: true
wave_0_complete: false
created: 2026-08-30
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (latest, via uv dev dependency) |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` — Wave 0 creates it (plan 01-01 Task 2): markers `unit`/`mt5`, addopts `-m "not mt5"`, testpaths `tests` |
| **Quick run command** | `uv run pytest -q` (unit only, MT5-free) |
| **Full suite command** | `uv run pytest -q -m "unit or mt5"` (mt5 tests auto-skip with actionable message when terminal unreachable) |
| **Estimated runtime** | ~15–30 seconds (unit); live mt5 tests add seconds when terminal is up |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest -q`
- **After every plan wave:** Run `uv run pytest -q -m "unit or mt5"`
- **Before `/gsd-verify-work`:** Full suite must be green (with terminal up, live mt5 tests executed)
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-01-T1 | 01-01 | 1 | — | T-1-SC | metatrader5 install gated by blocking-human legitimacy checkpoint | human-verify | (gate — no command; blocks Task 2 install) | — | ⬜ pending |
| 01-01-T2 | 01-01 | 1 | DATA-03, DATA-04 (infra) | T-1-SC | Pinned deps; default test run is MT5-free; local config + data/ gitignored | unit | `uv run pytest tests/unit/test_scaffold.py -q` | ❌ W0 | ⬜ pending |
| 01-01-T3 | 01-01 | 1 | DATA-03 | T-1-01 | Offset bounds ±14 enforced fail-fast; raw server time preserved; no secrets in committed config | unit | `uv run pytest tests/unit/test_normalize_and_config.py -q` | ❌ W0 | ⬜ pending |
| 01-01-T4 | 01-01 | 1 | DATA-04 | T-1-02 | Idempotent merge keyed on bar-open time; atomic tmp+os.replace; forming-bar guard; WAL checkpoint upserts | unit | `uv run pytest tests/unit/test_idempotent_store.py -q` | ❌ W0 | ⬜ pending |
| 01-02-T1 | 01-02 | 2 | DATA-01 | T-1-04 | Terminal/account selection confirmed by human; explicit terminal_path recorded | human-verify | (gate — blocks MT5-dependent work) | — | ⬜ pending |
| 01-02-T2 | 01-02 | 2 | DATA-01 | T-1-04, T-1-05 | Health check fails loudly with actionable messages; wrong-feed server assertion; credentials never in errors | unit | `uv run pytest tests/unit/test_health_check.py -q` | ❌ W0 | ⬜ pending |
| 01-02-T3 | 01-02 | 2 | DATA-02, DATA-03 | T-1-06 | Closed bars only (start_pos=1); checkpoint-filtered incremental store; write-then-checkpoint ordering | unit | `uv run pytest tests/unit/test_fetch_and_schedule.py -q` | ❌ W0 | ⬜ pending |
| 01-02-T4 | 01-02 | 2 | DATA-03 | T-1-04, T-1-11 | Live empirical offset validation persisted with validated_at; restart idempotency observable live | human-verify | (agent pre-work: `uv run python -m ai_trading.collector --once`) | — | ⬜ pending |
| 01-03-T1 | 01-03 | 3 | DATA-04 | T-1-08 | Retry-until-stable (None + -4 retried, not crashed); checkpoint-driven gap fill converges to one row per open time | unit | `uv run pytest tests/unit/test_backfill.py -q` | ❌ W0 | ⬜ pending |
| 01-03-T2 | 01-03 | 3 | DATA-05 | T-1-09 | Bounds + gaps persisted/queryable without MT5; terminal_maxbars provenance; session-aware gap classification | unit | `uv run pytest tests/unit/test_history_report.py -q` | ❌ W0 | ⬜ pending |
| 01-03-T3 | 01-03 | 3 | DATA-03, DATA-04 | T-1-11 | Timezone/DST re-derivation safety; boundary alignment; weekend gaps reported not raised; mt5 tests auto-skip | unit + mt5 | `uv run pytest tests/unit/test_timezone_dst.py -q`; `uv run pytest -m mt5 -q` | ❌ W0 | ⬜ pending |
| 01-03-T4 | 01-03 | 3 | ALL | — | Phase gate: full suite green with terminal up; live run ×2 idempotent; report reviewed; fail-loud demo | human-verify | `uv run pytest -q -m "unit or mt5"` | — | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `pyproject.toml` — project scaffold with `[tool.pytest.ini_options]` markers `unit`/`mt5` and default addopts `-m "not mt5"`; deps pinned (`metatrader5==5.0.6147`, `pandas>=3.0,<4`, `pyarrow`); ruff config (plan 01-01 Task 2)
- [ ] `tests/conftest.py` — shared fixtures: synthetic bar factory `make_bars` (plan 01-01 Task 2); `FakeMT5Client` + `fake_mt5` fixture (plan 01-02 Task 2)
- [ ] `tests/unit/` — seven unit modules mapped to requirements: `test_normalize_and_config.py` (DATA-03), `test_idempotent_store.py` (DATA-04), `test_health_check.py` (DATA-01), `test_fetch_and_schedule.py` (DATA-02/03), plus `test_backfill.py` (DATA-04), `test_history_report.py` (DATA-05), `test_timezone_dst.py` (DATA-03)
- [ ] `tests/integration/test_live_collect.py` — mt5-marked live tests, auto-skipped by default addopts (plan 01-03 Task 3)
- [ ] Wave-0 smoke: `uv run python -c "import MetaTrader5, pandas, pyarrow"` on cp312 (plan 01-01 Task 2, de-risks research assumption A3)

*Framework install rides the same task: `uv add --dev pytest ruff`.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Terminal running + logged in; "Max. bars in chart" = Unlimited; symbol names confirmed | DATA-01 | MT5 terminal is a GUI app outside agent control (locked project constraint) | Plan 01-02 Task 1 checkpoint steps 1–4 |
| Broker offset plausible + time_utc bar-boundary alignment eyeballed on live data | DATA-03 | Requires live ticks during active market hours + human judgment on plausibility | Plan 01-02 Task 4 checkpoint steps 5–6 |
| History report reviewed: 9 combos, maxbars provenance, weekend gaps flagged for review | DATA-05 | Final human acceptance per phase gate (VALIDATION sampling) | Plan 01-03 Task 4 checkpoint steps 5–8 |

*All other phase behaviors have automated verification.*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30 s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-08-30 (planner — verification map complete; wave_0_complete flips to true when plan 01-01 Task 2 lands)
