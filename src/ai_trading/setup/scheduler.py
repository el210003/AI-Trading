"""Setup scheduler (SETUP-01..04) — the M15-close-triggered engine entry point
(A5): read closed bars, assemble one setup per non-suppressed symbol, resolve
the lifecycle of all existing setups, and persist via the atomic store. MT5-free
by design — the engine reads stored Parquet bars only (never touches MT5).

CLI surface (mirrors ``backtest.runner`` / ``collector`` structure):
``python -m ai_trading.setup [--once | --monitor] [--config PATH]``.

Exit-code contract (pinned by tests):
- 2  config error (``load_config`` ValueError)
- 1  runtime refusal (engine cannot run — no bars, scorer load failure, ...)
- 0  success (including a zero-candidate run)
"""

from __future__ import annotations

import argparse
import logging
import sys
import time as _time
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from ai_trading.collector import seconds_until_next_close
from ai_trading.config import load_config
from ai_trading.llm.provider import OpenAICompatProvider
from ai_trading.ml.scorer import load_scorer
from ai_trading.setup.assembly import assemble_setup
from ai_trading.setup.lifecycle import ACTIVE_LIFECYCLE_STATUSES, apply_lifecycle
from ai_trading.setup.store import read_setups, upsert_setups
from ai_trading.stores.bar_store import bar_path, read_bars

log = logging.getLogger(__name__)

#: Terminal lifecycle statuses (never re-resolved; used for the summary).
_TERMINAL_STATUSES = frozenset({"tp_hit", "sl_hit", "expired", "invalidated"})


def models_dir(cfg) -> Path:
    """Path to the ML models root (``data/models``) derived from the data root."""
    return Path(cfg.bars_dir).parent / "models"


def should_run_on_m15_close(now_utc: datetime) -> bool:
    """True when ``now_utc`` falls exactly on an M15 close boundary (i.e. a
    fresh closed M15 bar has just become available). Uses the collector's
    ``seconds_until_next_close`` with a zero delay for boundary detection."""
    return seconds_until_next_close("M15", now_utc, 0) == 0.0


def _merge_records(stored: pd.DataFrame | None, new_records: list[dict]) -> pd.DataFrame:
    """Combine the stored setups frame with freshly assembled record dicts."""
    parts: list[pd.DataFrame] = []
    if stored is not None and not stored.empty:
        parts.append(stored)
    if new_records:
        parts.append(pd.DataFrame(new_records))
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts, ignore_index=True)


def run_engine_once(cfg, conn=None, *, scorer=None, llm_provider=None) -> dict:
    """One engine pass: assemble one setup per non-suppressed symbol, resolve
    the lifecycle of every stored setup against the latest bars, and persist via
    ``upsert_setups``. Returns ``{assembled, updated, total}``.

    ``conn`` is accepted for the meta-store seam but unused for v1 (the setup
    store is the only runtime state). ``scorer``/``llm_provider`` may be
    injected for tests; otherwise they are loaded once from ``cfg`` (Phase 4/5
    patterns). MT5-free.
    """
    del conn  # meta seam reserved; v1 setup store is the only state.
    stored = read_setups(cfg)

    bars_by_symbol: dict[str, dict] = {}
    for sym in cfg.engine_symbols:
        m15 = read_bars(bar_path(Path(cfg.bars_dir), sym, "M15"))
        if m15.empty:
            continue
        h1 = read_bars(bar_path(Path(cfg.bars_dir), sym, "H1"))
        h4 = read_bars(bar_path(Path(cfg.bars_dir), sym, "H4"))
        bars_by_symbol[sym] = {"m15": m15, "h1": h1, "h4": h4}

    # D-05 suppression: a symbol with an existing pending/active setup is not
    # re-assembled this pass (one live setup per symbol at a time).
    suppressed = set()
    if stored is not None and not stored.empty:
        live = stored[stored["status"].isin(ACTIVE_LIFECYCLE_STATUSES)]
        suppressed = set(live["symbol"].astype(str).unique())

    if scorer is None:
        scorer = load_scorer(models_dir(cfg))
    if llm_provider is None:
        llm_provider = OpenAICompatProvider(cfg)

    new_records: list[dict] = []
    for sym in cfg.engine_symbols:
        if sym in suppressed:
            continue
        bundle = bars_by_symbol.get(sym)
        if bundle is None:
            continue
        rec = assemble_setup(
            cfg, sym, bundle["m15"], bundle["h1"], bundle["h4"], scorer, llm_provider
        )
        if rec is not None:
            new_records.append(rec)

    combined = _merge_records(stored, new_records)
    lifecycle_bars = {sym: bundle["m15"] for sym, bundle in bars_by_symbol.items()}
    resolved = apply_lifecycle(combined, lifecycle_bars, cfg)

    if resolved is not None and not resolved.empty:
        upsert_setups(cfg, resolved)

    assembled = len(new_records)
    if resolved is not None and not resolved.empty:
        updated = int(resolved["status"].isin(_TERMINAL_STATUSES).sum())
        total = int(len(resolved))
    else:
        updated = 0
        total = int(len(stored)) if stored is not None else 0
    return {"assembled": assembled, "updated": updated, "total": total}


def main(argv: list[str] | None = None) -> int:
    """Setup engine CLI: ``uv run python -m ai_trading.setup [options]``.

    ``--once`` runs one engine pass and exits; ``--monitor`` (the default)
    loops: run the engine, then sleep ``seconds_until_next_close("M15", ...)``
    with the collector's drift-corrected recomputation each iteration. Exit
    codes: 2 config error, 1 runtime refusal, 0 success.
    """
    parser = argparse.ArgumentParser(
        prog="ai_trading.setup",
        description=(
            "MT5-free setup engine: assemble a fully-evidenced setup after each "
            "M15 close and run its lifecycle (pending -> active -> tp/sl/expired/invalidated)."
        ),
    )
    parser.add_argument(
        "--once", action="store_true", help="run one engine pass and exit"
    )
    parser.add_argument(
        "--monitor", action="store_true", help="loop, re-running after each M15 close (default)"
    )
    parser.add_argument(
        "--config", default="config.toml", help="path to config.toml (default: %(default)s)"
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    try:
        cfg = load_config(Path(args.config))
    except ValueError as exc:
        log.error("invalid configuration: %s", exc)
        return 2

    try:
        if args.once:
            summary = run_engine_once(cfg)
            log.info("engine pass complete: %s", summary)
            return 0
        log.info("setup engine monitor started (run after each M15 close)")
        while True:
            summary = run_engine_once(cfg)
            log.info("engine pass complete: %s", summary)
            sleep_seconds = seconds_until_next_close(
                "M15", datetime.now(UTC), int(cfg.poll_delay_seconds)
            )
            log.info(
                "sleeping %.1fs until next M15 close + %ss delay",
                sleep_seconds,
                int(cfg.poll_delay_seconds),
            )
            _time.sleep(sleep_seconds)
    except Exception as exc:  # noqa: BLE001 — runtime refusal lands on exit 1
        log.error("engine runtime refusal: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
