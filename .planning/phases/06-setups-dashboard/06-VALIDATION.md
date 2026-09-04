---
phase: 6
slug: setups-dashboard
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-09-04
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x |
| **Config file** | pyproject.toml (`[tool.pytest.ini_options]`) |
| **Quick run command** | `uv run pytest -q -m "not mt5 and not llm and not streamlit" tests/unit` |
| **Full suite command** | `uv run pytest -m "not mt5 and not llm and not streamlit"` |
| **Estimated runtime** | ~90 seconds |

---

## Sampling Rate

- **After every task commit:** Run the quick command
- **After every plan wave:** Run the full suite
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 120 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 06-01-01 | 01 | 1 | SETUP-01/02 | — | Setup assembly reuses Phase 3/4/5 pure functions; MT5-free; point-in-time | unit | `pytest tests/unit/test_setup_assembly.py` | ⬜ W0 | ⬜ pending |
| 06-01-02 | 01 | 1 | SETUP-03/04 | — | Lifecycle monitor (pending→active/invalidated→tp_hit/sl_hit/expired), dedup-on-setup_id store | unit | `pytest tests/unit/test_setup_lifecycle.py tests/unit/test_setup_store.py` | ⬜ W0 | ⬜ pending |
| 06-01-03 | 01 | 1 | SETUP-01..04 | — | Scheduled M15-close engine wiring; human checkpoint on `uv add streamlit plotly` | unit | `pytest tests/unit/test_setup_engine.py` | ⬜ W0 | ⬜ pending |
| 06-02-01 | 02 | 1 | DASH-01 | — | Streamlit setup table: filters symbol/status/direction/min-prob/date + sort | streamlit (AppTest) | `pytest tests/ui/test_dashboard_table.py` | ⬜ W0 | ⬜ pending |
| 06-02-02 | 02 | 1 | DASH-02/03 | — | plotly candlestick + entry/SL/TP + sweep/PD-zone overlays; evidence detail trace | streamlit (AppTest) | `pytest tests/ui/test_dashboard_chart.py tests/ui/test_dashboard_evidence.py` | ⬜ W0 | ⬜ pending |
| 06-03-01 | 03 | 1 | DASH-04 | — | History view: lifecycle outcomes per emitted setup | streamlit (AppTest) | `pytest tests/ui/test_dashboard_history.py` | ⬜ W0 | ⬜ pending |
| 06-03-02 | 03 | 1 | DASH-05 | — | Performance: WR/PF/expectancy + R equity curve (aggregate + per symbol) | unit | `pytest tests/unit/test_dashboard_perf.py` | ⬜ W0 | ⬜ pending |
| 06-03-03 | 03 | 1 | DASH-06 | — | Health strip: last-bar time per feed, MT5 status, recent errors | unit | `pytest tests/unit/test_dashboard_health.py` | ⬜ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `uv add streamlit plotly` — the only Wave-0 install (behind a checkpoint:human-verify legitimacy gate per the openai/metatrader5 precedent)
- [ ] Add `streamlit` pytest marker; default suite stays offline (`-m "not mt5 and not llm and not streamlit"`)
- [ ] `tests/unit/test_setup_assembly.py`, `test_setup_lifecycle.py`, `test_setup_store.py`, `test_setup_engine.py` — stubs
- [ ] `tests/ui/test_dashboard_*.py` — Streamlit AppTest stubs
- [ ] Reuse existing `_backtest_fixtures.py` / `_llm_fixtures.py` / `_ml_fixtures.py` (no fork)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live MT5 connection status in the health strip | DASH-06 | Requires the running MT5 terminal | Run the engine once against the live terminal; confirm the health strip shows connected + last-bar times |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 120s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
