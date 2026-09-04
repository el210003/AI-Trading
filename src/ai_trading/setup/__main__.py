"""Module entry for ``python -m ai_trading.setup`` — the plan 06-01 CLI surface
(`--once` / `--monitor`). Keeps ``ai_trading.setup/__init__.py`` a public
re-export package marker."""

import sys

from ai_trading.setup.scheduler import main

if __name__ == "__main__":
    sys.exit(main())
