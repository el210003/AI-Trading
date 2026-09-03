"""Module entry for `python -m ai_trading.ml` — the Phase 4 retrain CLI
surface. Keeps ai_trading/ml/__init__.py a bare package marker (mirrors
backtest/__main__.py)."""

import sys

from ai_trading.ml.runner import main

if __name__ == "__main__":
    sys.exit(main())
