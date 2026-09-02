# Phase 3: User Setup Required

**Generated:** 2026-09-02
**Phase:** 03-backtesting-labeling
**Status:** Incomplete

One human decision is carried by plan 03-01 for phase verification. The agent automated everything possible; this item requires human judgment only.

## Human Decision (non-blocking for implementation)

- [ ] **Confirm the A1 cost-asymmetry convention**
  - What: bar OHLC prices are BID-side, so the spread is crossed exactly once per round trip — a LONG crosses the spread at ENTRY (buys the ask), a SHORT crosses at EXIT (buys back the ask). Slippage (D-14) is charged adversely on BOTH fills for both directions.
  - Where it is pinned: `src/ai_trading/backtest/costs.py` (`entry_fill_price` / `exit_fill_price`) + `tests/unit/test_costs.py::test_long_short_cost_symmetry` (net round-trip cost = spread_px + 2×slip for BOTH directions on identical bar paths)
  - How to verify (10-second eyeball): read the two fill formulas and the symmetry test; confirm this matches your mental model of bid-side bars. If you model "spread = cost per side" instead, only `costs.py` and its tests change (per RESEARCH Open Question 2).
  - When: phase verification (`/gsd-verify-work` for phase 03). Non-blocking for plans 03-02/03-03.

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
```
