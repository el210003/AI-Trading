---
phase: 3
slug: backtesting-labeling
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-09-01
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x |
| **Config file** | pyproject.toml (`[tool.pytest.ini_options]`) |
| **Quick run command** | `uv run pytest -q -m "not mt5" tests/unit` |
| **Full suite command** | `uv run pytest -m "not mt5"` |
| **Estimated runtime** | ~60 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest -q -m "not mt5" tests/unit`
- **After every plan wave:** Run `uv run pytest -m "not mt5"`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 120 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 1 | BT-01 | — | Replay calls same detector chain, no future data | unit | `pytest tests/unit/test_replay.py` | ⬜ W0 | ⬜ pending |
| 03-01-02 | 01 | 1 | BT-02 | — | Cost = spread + slippage, refuses short history | unit | `pytest tests/unit/test_cost_model.py` | ⬜ W0 | ⬜ pending |
| 03-02-01 | 02 | 1 | BT-03 | — | Triple-barrier labels, SL-first tie rule | unit | `pytest tests/unit/test_labels.py` | ⬜ W0 | ⬜ pending |
| 03-02-02 | 02 | 1 | BT-04 | — | Canonical stats reports correct | unit | `pytest tests/unit/test_stats.py` | ⬜ W0 | ⬜ pending |
| 03-03-01 | 03 | 1 | BT-05 | — | Walk-forward windows chronological, no overlap | unit | `pytest tests/unit/test_walkforward.py` | ⬜ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/test_replay.py` — stubs for BT-01
- [ ] `tests/unit/test_cost_model.py` — stubs for BT-02
- [ ] `tests/unit/test_labels.py` — stubs for BT-03
- [ ] `tests/unit/test_stats.py` — stubs for BT-04
- [ ] `tests/unit/test_walkforward.py` — stubs for BT-05
- [ ] `tests/conftest.py` — shared fixtures (`make_bars`, `FakeMT5Client` already exist — extend)

*If none: "Existing infrastructure covers all phase requirements."*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Cost asymmetry convention (long spread at entry / short at exit) | BT-02 | Assumption A1 flagged in RESEARCH.md; needs human confirmation | Review A1 in RESEARCH.md, confirm or override convention |

*If none: "All phase behaviors have automated verification."*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 120s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
