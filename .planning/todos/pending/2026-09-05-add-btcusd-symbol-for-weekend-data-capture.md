---
created: 2026-09-05T01:22:50.256Z
title: Add BTCUSD symbol for weekend data capture
area: config
files:
  - config.toml:4-5
  - config.toml:47
  - config.local.toml
  - src/ai_trading/collector.py
  - src/ai_trading/normalize.py
---

## Problem

Forex closes over the weekend (Friday ~21:00 UTC → Sunday ~21:00 UTC), so the collector gets no fresh closed bars and the live engine/dashboard cannot be exercised end-to-end from Friday evening to Monday morning. Crypto trades 7x24, so adding **BTCUSD** to the MT5 collector would keep fresh M15 bars flowing over weekends for live testing.

**Conflict to resolve first:** PROJECT.md Out of Scope says "Non-forex instruments (indices, crypto, metals) — forex majors only for v1". Adding BTCUSD contradicts the v1 constraint — decide whether to (a) amend the constraint, (b) add BTCUSD as a test-only symbol excluded from setups/scoring, or (c) drop the idea.

## Solution

TBD pending the scope decision. Hints if we proceed:
- Add `BTCUSD` to `symbols` in config (and consider a `setup_symbols`/`test_symbols` split if test-only).
- Add `pip_size.BTCUSD` (config.toml pip_size map currently has only the 3 majors) and check spread/slippage defaults (default_spread_points=20 is calibrated for 5-digit forex).
- Verify the MT5 terminal's demo server actually lists BTCUSD symbol name (e.g. `BTCUSD` vs broker-suffixed variant per the Phase-01 symbol regex).
- Confirm detector chain (M15/H1/H4), zone economics, and min_rr make sense for crypto volatility before letting the engine assemble BTCUSD setups.
