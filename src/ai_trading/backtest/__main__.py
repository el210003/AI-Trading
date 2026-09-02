"""Module entry for `python -m ai_trading.backtest` — the plan 03-03 CLI
surface. Keeps ai_trading.backtest/__init__.py a bare package marker."""

import sys

from ai_trading.backtest.runner import main

if __name__ == "__main__":
    sys.exit(main())
