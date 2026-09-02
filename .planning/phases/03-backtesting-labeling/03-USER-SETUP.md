# Phase 3: User Setup Required

**Generated:** 2026-09-02
**Phase:** 03-backtesting-labeling
**Status:** Incomplete

One human decision is carried by plan 03-01 for phase verification; plan 03-03 adds a second (the real-data demo depth decision). The agent automated everything possible; these items require human judgment only.

## Human Decision (non-blocking for implementation)

- [ ] **Confirm the A1 cost-asymmetry convention**
  - What: bar OHLC prices are BID-side, so the spread is crossed exactly once per round trip — a LONG crosses the spread at ENTRY (buys the ask), a SHORT crosses at EXIT (buys back the ask). Slippage (D-14) is charged adversely on BOTH fills for both directions.
  - Where it is pinned: `src/ai_trading/backtest/costs.py` (`entry_fill_price` / `exit_fill_price`) + `tests/unit/test_costs.py::test_long_short_cost_symmetry` (net round-trip cost = spread_px + 2×slip for BOTH directions on identical bar paths)
  - How to verify (10-second eyeball): read the two fill formulas and the symmetry test; confirm this matches your mental model of bid-side bars. If you model "spread = cost per side" instead, only `costs.py` and its tests change (per RESEARCH Open Question 2).
  - When: phase verification (`/gsd-verify-work` for phase 03). Non-blocking for plans 03-02/03-03.

- [ ] **Real-data demo run: decide history depth (Phase gate, Open Question 1 — plan 03-03)**
  - What: the engine is fully synthetic-tested, but the phase-gate demo (`python -m ai_trading.backtest --config config.toml --range last-ND --write`) needs a human call because stored M15 history is ~9 days — below D-21's 30-day gate. Decide ONE of:
    1. Deepen stored history via the Phase 1 purge+backfill mechanism (preferred for a meaningful demo), or
    2. Run the demo with `--min-history-days 5` (override) and/or a shorter `--range last-ND`, accepting a small-sample run, or
    3. Run on H4-range depth if M15 stays shallow (HTF-only demo; M15 gate still applies per symbol).
  - Where: `src/ai_trading/backtest/runner.py` (D-21 gate refusal carries the remedy text; exit 1 with no artifacts on refusal; exit 0 including zero-candidate runs).
  - When: phase verification (`/gsd-verify-work` for phase 03). Non-blocking for implementation — the unit suite proves the engine either way.

## Environment Variables

None — the backtest package is MT5-free by design and requires no credentials or terminal access.

## Account Setup

None.

## Dashboard Configuration

None.

## Verification Commands

```bash
uv run pytest tests/unit/test_costs.py -q        # cost model incl. symmetry pin
uv run pytest tests/unit -q                      # full unit suite
uv run python -m ai_trading.backtest --help      # runner CLI surface
# Phase-gate demo (after the history-depth decision above):
uv run python -m ai_trading.backtest --config config.toml --range last-ND --write
```
